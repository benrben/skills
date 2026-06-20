/* arch-map studio — shared state (backend-backed)
 *
 * The production data layer for the unified studio. It exposes the SAME
 * window.Arch API surface the design prototype used (Store / subscribe / tierOf /
 * isOrphan / openSuggestions / STRENGTHS / Prefs / Maps), backed by the FastMCP
 * HTTP server:
 *
 *   GET  /api/model            -> the full ArchModel (single source of truth)
 *   POST /api/act {action,..}   -> mutate the map under a lock, returns the model
 *
 * The backend model differs from the prototype's seed shape, so this layer
 * normalizes on the way in and de-normalizes on the way out:
 *
 *   depth / coverage   backend 0..1 (float)      <-> studio 0..100 (int)
 *   iface              backend field name        ->  studio `interface`
 *   leaksTo            backend field name        ->  studio `leaks`
 *   tests              backend free-text string  ->  studio array (single entry)
 *   suggestion.strength "Strong"/"Worth exploring"/"Speculative" <-> strong/worth/speculative
 *   decision           backend lives ON the suggestion (decision + note),
 *                      studio expects a separate decisions[sid] map
 *
 * --- shape (what makes this testable) -------------------------------------
 * This module is split into three layers behind one small seam so the deep,
 * stateful protocol can be tested with plain Node (mirrors focus.js/doclens.js):
 *
 *   1. PURE TRANSFORMS — normalize(raw, prevSeq) + denorm + the derived helpers
 *      (tierOf / isOrphan / isOpen / openSuggestions / diffModels). No I/O, no
 *      browser globals. Exported for direct unit tests (state.normalize.test.js).
 *
 *   2. createStore({ transport, onError, onBroadcast }) — the data-layer CORE:
 *      the synchronous cache (`cur`), the optimistic-write protocol (the monotonic
 *      `writeGen` + `pendingWrites` guards that stop a stale server snapshot from
 *      clobbering a newer optimistic write), focus/poll reconcile, and the Store
 *      mutators. It reaches the server ONLY through the injected transport PORT
 *      (getModel / act / docAct / wtAct), so tests drive it against an in-memory
 *      stub adapter (state.protocol.test.js). No browser globals.
 *
 *   3. BROWSER BOOTSTRAP (runs only when `window` exists) — builds the browser
 *      HTTP transport adapter, the named-maps layer (URL ?map=), Prefs, polling +
 *      focus reconcile, the agent-bridge dispatch/grill/whatif, and assembles
 *      window.Arch. The studio is browser-only: there is no MCP-App host transport
 *      (see adr-retire-mcp-app-host) — host mode was removed because its read path
 *      called tools deleted by the read->resource migration.
 *
 * Cross-surface sync (the agent via MCP tools, another browser tab) is handled by
 * polling /api/model every 2.5s and on focus regain — a change anywhere shows up
 * everywhere without a reload.
 */
(function (root) {
  "use strict";

  // ===========================================================================
  // 1. PURE TRANSFORMS  (the test surface for normalization — no I/O, no globals)
  // ===========================================================================
  const STRENGTH_TO_KEY = { "Strong": "strong", "Worth exploring": "worth", "Speculative": "speculative" };
  const VERDICT_TO_DECISION = { accept: "accepted", defer: "deferred", reject: "rejected" };
  const DECISION_TO_VERDICT = { accepted: "accept", deferred: "defer", rejected: "reject" };

  function strengthKey(s) {
    if (!s) return "speculative";
    if (STRENGTH_TO_KEY[s]) return STRENGTH_TO_KEY[s];
    const t = String(s).toLowerCase();
    if (t.indexOf("strong") >= 0) return "strong";
    if (t.indexOf("worth") >= 0) return "worth";
    return "speculative";
  }

  function testsToArray(t) {
    if (Array.isArray(t)) return t.filter(Boolean);
    if (typeof t === "string" && t.trim()) return [t.trim()];
    return [];
  }
  // de-normalize on the way OUT: the backend stores `tests` as a free-text string,
  // so if a write ever carries the studio's array form, join it before it crosses
  // the wire (server.py's render_view does `(tests or "").strip()` — a list throws).
  function testsToString(t) {
    if (Array.isArray(t)) return t.filter(Boolean).join("\n");
    return t == null ? "" : String(t);
  }
  function denormFields(fields) {
    if (fields && "tests" in fields) {
      return Object.assign({}, fields, { tests: testsToString(fields.tests) });
    }
    return fields;
  }

  function normSug(s, moduleId) {
    return {
      sid: s.id,
      module: moduleId,
      strength: STRENGTH_TO_KEY[s.strength] || strengthKey(s.strength),
      category: s.category || "",
      title: s.title || "", problem: s.problem || "", solution: s.solution || "",
      wins: Array.isArray(s.wins) ? s.wins : [],
      status: s.status || "open", decision: s.decision || "", note: s.note || "",
      adrRef: s.adrRef || "", planId: s.planId || "",
    };
  }
  function normPlan(p) {
    return {
      id: p.id,
      title: p.title || "",
      domain: p.domain || "",
      intent: p.intent || "",
      status: p.status || "draft",
      moduleIds: Array.isArray(p.moduleIds) ? p.moduleIds : [],
      adrRefs: Array.isArray(p.adrRefs) ? p.adrRefs : [],
      steps: (p.steps || []).map((st) => ({
        id: st.id, title: st.title || "", status: st.status || "todo",
        targets: st.targets || [], interface: st.interface || "",
        dependsOnSteps: st.dependsOnSteps || [], adapters: st.adapters || [],
        note: st.note || "",
        // board fields: priority (ordering), agent (swimlane), worktree (isolation), blocked (flag)
        priority: st.priority || "normal", agent: st.agent || "",
        worktree: st.worktree || "", blocked: !!st.blocked,
      })),
    };
  }
  // worktrees: per-task isolated branches, passed through with array-safe defaults.
  function normWorktree(w) {
    return {
      id: w.id, branch: w.branch || "", path: w.path || "", base: w.base || "",
      status: w.status || "active", planId: w.planId || "", stepId: w.stepId || "",
      agent: w.agent || "", head: w.head || "", created: w.created || "", note: w.note || "",
    };
  }
  // docs are projected (resolvedModuleIds / drift / scopeLabel baked by the server);
  // pass them through with array-safe defaults so the DocLens + browser can read them.
  function normDoc(d) {
    return {
      id: d.id, type: d.type || "note", title: d.title || "", summary: d.summary || "",
      body: d.body || "", status: d.status || "",
      scope: d.scope || { kind: "system" },
      tags: Array.isArray(d.tags) ? d.tags : [],
      author: d.author || "", created: d.created || "", updated: d.updated || "",
      supersedes: Array.isArray(d.supersedes) ? d.supersedes : [],
      adrRef: d.adrRef || "",
      resolvedModuleIds: Array.isArray(d.resolvedModuleIds) ? d.resolvedModuleIds : [],
      drift: Array.isArray(d.drift) ? d.drift : [],
      scopeLabel: d.scopeLabel || "",
    };
  }
  // PURE: backend ArchModel -> studio model. `prevSeq` is the prior cache seq (the
  // caller threads it so the result carries a monotonically-increasing seq); pass
  // nothing in a unit test and seq starts at 1.
  function normalize(raw, prevSeq) {
    raw = raw || {};
    const decisions = {};
    const modules = (raw.modules || []).map((m) => {
      // The backend keeps a QUEUE of candidates per module (m.suggestions); fall
      // back to the back-compat single m.suggestion for older payloads.
      const raws = (Array.isArray(m.suggestions) && m.suggestions.length)
        ? m.suggestions : (m.suggestion ? [m.suggestion] : []);
      const suggestions = raws.map((s) => normSug(s, m.id));
      // primary = first still-open candidate (drives the ⚠ ring + the inspector card)
      const suggestion = suggestions.find((x) => !x.decision && x.status !== "done") || null;
      // every decided candidate records a verdict, keyed by its SUGGESTION id
      suggestions.forEach((s) => {
        if (s.decision) {
          decisions[s.sid] = {
            verdict: DECISION_TO_VERDICT[s.decision] || s.decision,
            reason: s.note || "",
            adr: s.adrRef || "",
            at: null,
          };
        }
      });
      return {
        id: m.id,
        label: m.label,
        domain: m.domain,
        depth: Math.round((m.depth || 0) * 100),
        coverage: Math.round((m.coverage || 0) * 100),
        size: m.size || 1,                 // relative impl mass (ratio, NOT 0..100) — feeds bulky-impl
        updated: !!m.updated,
        plane: m.plane || "actual",
        lifecycle: m.lifecycle || "built",
        interface: m.iface || "",
        files: Array.isArray(m.files) ? m.files : [],
        tests: testsToArray(m.tests),
        dependsOn: Array.isArray(m.dependsOn) ? m.dependsOn : [],
        leaks: Array.isArray(m.leaksTo) ? m.leaksTo : [],
        intendsToDependOn: Array.isArray(m.intendsToDependOn) ? m.intendsToDependOn : [],
        supersedes: Array.isArray(m.supersedes) ? m.supersedes : [],
        supersededBy: Array.isArray(m.supersededBy) ? m.supersededBy : [],
        suggestion,
        suggestions,
        metrics: m.metrics ? {
          fanIn:       m.metrics.fanIn       || 0,
          fanOut:      m.metrics.fanOut      || 0,
          instability: m.metrics.instability ?? 0.5,
          blastRadius: m.metrics.blastRadius || 0,
          coupling:    m.metrics.coupling    || 0,
          inCycle:     !!m.metrics.inCycle,
          health:      m.metrics.health      ?? 50,
          churn:       Math.round((m.metrics.churn || 0) * 100),
        } : { fanIn:0, fanOut:0, instability:0.5, blastRadius:0, coupling:0, inCycle:false, health:50, churn:0 },
      };
    });
    const plans = (raw.plans || []).map(normPlan);
    const docs = Array.isArray(raw.docs) ? raw.docs.map(normDoc) : [];
    const worktrees = Array.isArray(raw.worktrees) ? raw.worktrees.map(normWorktree) : [];
    // `board` is the server-computed skill-cycle projection (single source of truth —
    // the board UI renders it rather than recomputing lanes/columns client-side).
    return { repo: raw.repo || "", modules, plans, docs, worktrees, board: raw.board || null,
             docMembership: raw.docMembership || {}, decisions, seq: (prevSeq || 0) + 1 };
  }

  // ---- derived helpers (pure) ----------------------------------------------
  function tierOf(depth) {
    if (depth >= 67) return "deep";
    if (depth >= 34) return "mid";
    return "shallow";
  }
  function isOrphan(s, m) {
    const hasOut = (m.dependsOn || []).length > 0 || (m.leaks || []).length > 0
      || (m.intendsToDependOn || []).length > 0 || (m.supersedes || []).length > 0;
    const hasIn = s.modules.some((x) =>
      (x.dependsOn || []).includes(m.id) || (x.leaks || []).includes(m.id)
      || (x.intendsToDependOn || []).includes(m.id) || (x.supersedes || []).includes(m.id));
    return !hasOut && !hasIn;
  }
  function isOpen(model, sug) {
    return !model.decisions[sug.sid] && sug.status !== "done";
  }
  function openSuggestions(s) {
    return s.modules.flatMap((m) => (m.suggestions || []).filter((x) => isOpen(s, x)));
  }
  // Pure helper. Given two NORMALIZED models (prev, next — the studio shapes), return
  // a flat list of field-level changes for the activity feed to format into human
  // verbs. Synthetic +module / -module rows are emitted for added / removed modules.
  function diffModels(prev, next) {
    const out = [];
    const prevMods = (prev && prev.modules) || [];
    const nextMods = (next && next.modules) || [];
    const prevById = {};
    prevMods.forEach((m) => { prevById[m.id] = m; });
    const nextById = {};
    nextMods.forEach((m) => { nextById[m.id] = m; });

    // removed modules (present before, gone now)
    prevMods.forEach((m) => {
      if (!(m.id in nextById)) out.push({ id: m.id, field: "-module", from: m.label || m.id, to: null });
    });

    const openCount = (m) =>
      (m.suggestions || []).filter((x) => !x.decision && x.status !== "done").length;

    nextMods.forEach((m) => {
      const p = prevById[m.id];
      if (!p) {                                   // added module (new this diff)
        out.push({ id: m.id, field: "+module", from: null, to: m.label || m.id });
        return;
      }
      const cmp = (field, a, b) => { if (a !== b) out.push({ id: m.id, field, from: a, to: b }); };
      cmp("depth", p.depth, m.depth);
      cmp("coverage", p.coverage, m.coverage);
      cmp("updated", p.updated, m.updated);
      cmp("lifecycle", p.lifecycle, m.lifecycle);
      cmp("plane", p.plane, m.plane);
      cmp("health", (p.metrics && p.metrics.health), (m.metrics && m.metrics.health));
      cmp("leaks", (p.leaks || []).length, (m.leaks || []).length);
      cmp("dependsOn", (p.dependsOn || []).length, (m.dependsOn || []).length);
      cmp("suggestions", openCount(p), openCount(m));
    });
    return out;
  }

  // ===========================================================================
  // 2. createStore — the data-layer CORE (no browser globals; transport injected)
  // ===========================================================================
  // transport PORT (two adapters: browser HTTP in prod, in-memory stub in tests):
  //   getModel()        -> Promise<string>  the full model as JSON text
  //   act(body)         -> Promise<string>  POST a studio action, returns the model
  //   docAct(body)      -> Promise<string>  POST a doc op, returns the model
  //   wtAct(body)       -> Promise<string>  POST a worktree op, returns the model
  // each write rejects (throws) on a server error; the core rolls the optimistic
  // value back to server truth and rethrows so onError can surface it.
  function createStore(opts) {
    opts = opts || {};
    const transport = opts.transport || {};
    const onError = typeof opts.onError === "function" ? opts.onError : function () {};
    const onBroadcast = typeof opts.onBroadcast === "function" ? opts.onBroadcast : function () {};

    // in-memory cache: the synchronous view the studio renders from. Reads return
    // it; writes update it optimistically, then a background POST reconciles
    // against the authoritative server response.
    let cur = { repo: "", modules: [], plans: [], docs: [], worktrees: [], board: null, docMembership: {}, decisions: {}, seq: 0 };
    let lastServerJson = "";       // raw JSON of the last authoritative model
    let pendingWrites = 0;         // in-flight POSTs (gates poll-reconcile)
    let writeGen = 0;              // bumps per optimistic write; gates stale server snapshots

    // ---- broadcast / subscribe ---------------------------------------------
    const listeners = new Set();
    function broadcast(s) {
      // the DocLens seam (and any host-provided hook) sees the fresh model first,
      // before the general subscribers (graph highlight, doc browser).
      try { onBroadcast(s); } catch (e) { /* a bad hook must not break delivery */ }
      listeners.forEach((fn) => { try { fn(s); } catch (e) {} });
    }
    function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }

    // ---- optimistic local mutation helpers ---------------------------------
    function bump() { cur.seq = (cur.seq || 0) + 1; }
    function clamp(n) { return Math.max(0, Math.min(100, Math.round(n))); }
    function find(id) { return cur.modules.find((x) => x.id === id); }
    // locate a suggestion (and its owning module) anywhere in the queue, by sid
    function findSug(sid) {
      for (const m of cur.modules) {
        const s = (m.suggestions || []).find((x) => x.sid === sid);
        if (s) return { module: m, sug: s };
      }
      return null;
    }

    // ---- server reconcile ---------------------------------------------------
    // The cache is reconciled by exactly two sources — the response to a write and
    // the background poll/focus refetch. Both can arrive out of order, so the
    // monotonic `writeGen` gates them: a server snapshot is only adopted if no
    // newer optimistic write has happened since it was requested. Without this, a
    // stale in-flight GET (or an older POST response) could clobber a newer
    // optimistic value and the UI would visibly revert until the next poll.
    function applyServerModel(rawText) {
      if (rawText === lastServerJson) return false;  // byte-identical: nothing changed
      lastServerJson = rawText;
      store.prevModel = cur;                          // expose the pre-swap model for diffing
      cur = normalize(JSON.parse(rawText), cur.seq);
      return true;
    }
    function adoptServer(rawText) {
      // force the cache to server truth, bypassing the byte short-circuit — used to
      // roll back a rejected optimistic write even when server state is unchanged.
      lastServerJson = rawText;
      store.prevModel = cur;
      cur = normalize(JSON.parse(rawText), cur.seq);
      broadcast(cur);
    }

    // background poll / focus reconcile — must never clobber an optimistic write
    async function refetch(broadcastIfChanged) {
      const gen = writeGen;
      try {
        const txt = await transport.getModel();
        // a write started or is still in flight since we asked: its own reconcile wins
        if (pendingWrites > 0 || writeGen !== gen) return false;
        const changed = applyServerModel(txt);
        if (changed && broadcastIfChanged) broadcast(cur);
        return changed;
      } catch (e) { /* server momentarily unreachable; keep last good cache */ return false; }
    }

    // force-reload the current map's model (e.g. after switching maps): a new write
    // generation invalidates any in-flight poll, the byte cache is cleared so the
    // fresh model always adopts.
    async function reload() {
      ++writeGen;
      lastServerJson = "";
      try { applyServerModel(await transport.getModel()); } catch (e) { /* keep cache */ }
      broadcast(cur);
      return cur;
    }

    // one write discipline, shared by act/docAct/wtAct: bump the generation, run the
    // transport call, reconcile only if still the newest write; on failure roll back
    // to server truth (best-effort — a dead server leaves the optimistic value) and
    // rethrow so the caller's onError surfaces it.
    async function runWrite(fn, body) {
      const myGen = ++writeGen;
      pendingWrites++;
      try {
        let txt;
        try {
          txt = await fn(body);
        } catch (e) {
          if (myGen === writeGen) { try { adoptServer(await transport.getModel()); } catch (_) {} }
          throw e;
        }
        if (myGen === writeGen && applyServerModel(txt)) broadcast(cur);
      } finally {
        pendingWrites--;
      }
    }

    function act(body) {
      if (body && body.action === "update" && body.fields) {
        body = Object.assign({}, body, { fields: denormFields(body.fields) });
      }
      return runWrite(transport.act, body);
    }
    function docAct(body) { return runWrite(transport.docAct, body); }
    function wtAct(body) { return runWrite(transport.wtAct, body); }

    function sidFor(id) {
      const m = find(id);
      return m && m.suggestion ? m.suggestion.sid : null;
    }

    // ---- model API (mirrors the prototype's synchronous Store) -------------
    const store = {
      get() { return cur; },

      // the model as it was before the most recent server swap, so consumers can
      // diff old->new for narration. null until the first swap.
      prevModel: null,
      // snapshot of the last module removed via deleteModule, for undo.
      // { module, edges:[{from,field,to}], decision } | null
      lastDeleted: null,

      reset() { refetch(true); return cur; },   // no client seed: re-sync from server

      subscribe,
      refetch,
      reload,
      pending() { return pendingWrites > 0; },
      sidFor,

      setDepth(id, delta) {
        const m = find(id);
        if (m) { m.depth = clamp(m.depth + delta); m.updated = true; bump(); }
        act({ action: "set_depth", module: id, score: (m ? m.depth : 0) / 100 }).catch(onError);
        return cur;
      },
      setCoverage(id, delta) {
        const m = find(id);
        if (m) { m.coverage = clamp(m.coverage + delta); m.updated = true; bump(); }
        act({ action: "set_coverage", module: id, fraction: (m ? m.coverage : 0) / 100 }).catch(onError);
        return cur;
      },
      addModule({ id, label, domain }) {
        if (!id || find(id)) return cur;
        cur.modules.push({
          id, label: label || id, domain: domain || "uncategorized",
          depth: 50, coverage: 0, updated: true, plane: "actual", lifecycle: "built", interface: "",
          files: [], tests: [], dependsOn: [], leaks: [],
          intendsToDependOn: [], supersedes: [], supersededBy: [],
          suggestion: null, suggestions: [],
        });
        bump();
        act({ action: "add", module: { id, label: label || id, domain: domain || "uncategorized" } }).catch(onError);
        return cur;
      },
      deleteModule(id) {
        // snapshot before mutating so undoDelete can re-create the module and every
        // inbound edge it strips off other modules.
        const gone = cur.modules.find((x) => x.id === id);
        const inbound = [];
        cur.modules.forEach((m) => {
          if ((m.dependsOn || []).includes(id)) inbound.push({ from: m.id, field: "dependsOn", to: id });
          if ((m.leaks || []).includes(id))     inbound.push({ from: m.id, field: "leaksTo",   to: id });
        });
        store.lastDeleted = gone
          ? { module: JSON.parse(JSON.stringify(gone)), edges: inbound, decision: cur.decisions[id] }
          : null;

        cur.modules = cur.modules.filter((x) => x.id !== id);
        cur.modules.forEach((m) => {
          m.dependsOn = m.dependsOn.filter((d) => d !== id);
          m.leaks = (m.leaks || []).filter((d) => d !== id);
        });
        delete cur.decisions[id];
        bump();
        act({ action: "delete", module: id }).catch(onError);
        return cur;
      },
      undoDelete() {
        // re-add the last-deleted module and its inbound edges. Optimistic locally,
        // then re-create on the server (no native "undelete"): add the module,
        // restore its captured fields via update, and re-point each referrer's
        // dependsOn/leaksTo back at it.
        const snap = store.lastDeleted;
        if (!snap) return cur;
        const m = snap.module;
        if (!find(m.id)) cur.modules.push(JSON.parse(JSON.stringify(m)));
        snap.edges.forEach((e) => {
          const src = find(e.from);
          if (!src) return;
          const arr = e.field === "leaksTo" ? "leaks" : "dependsOn";
          src[arr] = src[arr] || [];
          if (!src[arr].includes(e.to)) src[arr].push(e.to);
        });
        bump();
        store.lastDeleted = null;

        act({ action: "add", module: { id: m.id, label: m.label, domain: m.domain } })
          .then(() => act({ action: "update", module: m.id, fields: {
            iface: m.interface, depth: m.depth / 100, coverage: m.coverage / 100,
            dependsOn: m.dependsOn, leaksTo: m.leaks,
          } }))
          .then(() => Promise.all(snap.edges.map((e) => {
            const src = find(e.from);
            if (!src) return null;
            return act({ action: "update", module: e.from,
              fields: e.field === "leaksTo" ? { leaksTo: src.leaks } : { dependsOn: src.dependsOn } });
          })))
          .catch(onError);
        return cur;
      },
      decide(sid, verdict, reason) {
        // the proposal must still exist on the server to record a decision against it
        if (!findSug(sid)) { onError(new Error("proposal " + sid + " no longer exists")); refetch(true); return cur; }
        cur.decisions[sid] = { verdict, reason: reason || "", adr: "", at: null };
        bump();
        act({ action: "decide", suggestion_id: sid, decision: VERDICT_TO_DECISION[verdict] || verdict, note: reason || "" }).catch(onError);
        return cur;
      },
      reopen(sid) {
        delete cur.decisions[sid];
        bump();
        act({ action: "decide", suggestion_id: sid, decision: "", note: "" }).catch(onError);
        return cur;
      },
      dismiss(sid) {
        const hit = findSug(sid);
        if (hit) {
          const m = hit.module;
          m.suggestions = (m.suggestions || []).filter((x) => x.sid !== sid);
          m.suggestion = m.suggestions.find((x) => !x.decision && x.status !== "done") || null;
        }
        delete cur.decisions[sid];
        bump();
        act({ action: "resolve", suggestion_id: sid }).catch(onError);
        return cur;
      },
      setStepStatus(planId, stepId, status) {
        const plan = (cur.plans || []).find((p) => p.id === planId);
        if (plan) {
          const step = (plan.steps || []).find((s) => s.id === stepId);
          if (step) { step.status = status; bump(); }
        }
        act({ action: "set_step_status", plan_id: planId, step_id: stepId, status }).catch(onError);
        return cur;
      },
      // patch a board card's fields (priority/agent/worktree/blocked/status) in one write
      setStepFields(planId, stepId, fields) {
        const plan = (cur.plans || []).find((p) => p.id === planId);
        if (plan) {
          const step = (plan.steps || []).find((s) => s.id === stepId);
          if (step) { Object.assign(step, fields); bump(); }
        }
        act({ action: "set_step_fields", plan_id: planId, step_id: stepId, fields }).catch(onError);
        return cur;
      },
      assignStep(planId, stepId, agent) { return store.setStepFields(planId, stepId, { agent }); },

      // ---- worktrees: per-task isolated branches (real git, server-side + guarded) ----
      // Non-optimistic: the op returns the full refreshed model (the worktree's git
      // state baked in), so the cache reconciles from server truth. Mirrors docAct.
      createWorktree(opts2) { wtAct(Object.assign({ op: "create" }, opts2 || {})).catch(onError); return cur; },
      attachWorktree(opts2) { wtAct(Object.assign({ op: "attach" }, opts2 || {})).catch(onError); return cur; },
      removeWorktree(id, force) { wtAct({ op: "remove", id, force: !!force }).catch(onError); return cur; },
      syncWorktrees() { wtAct({ op: "sync" }).catch(onError); return cur; },

      // flag ONE candidate (e.g. from a what-if preview) through the suggestion FSM
      // (grilling/deciding stay with fathom:design). sug: {title, strength, category,
      // problem, solution, wins[]} in backend strength spelling.
      flagCandidate(id, sug) {
        act({ action: "flag", module: id, suggestion: sug }).catch(onError);
        return cur;
      },

      // ---- docs (scoped architecture documents) ----
      // doc is {id,type,title,scope,summary,body,status,tags,supersedes,adrRef,author}.
      addDoc(doc) { docAct({ op: "add", doc }).catch(onError); return cur; },
      updateDoc(docId, fields) { docAct({ op: "update", doc_id: docId, fields }).catch(onError); return cur; },
      deleteDoc(docId) { docAct({ op: "delete", doc_id: docId }).catch(onError); return cur; },
    };

    return store;
  }

  // ===========================================================================
  // 3. BROWSER BOOTSTRAP  (runs only in the browser; assembles window.Arch)
  // ===========================================================================
  function boot(win) {
    const doc = win.document;
    const loc = win.location;

    const PREF_KEY = "archmap.prefs.v1";
    const POLL_MS = 2500;
    const API_MODEL = "api/model";
    const API_ACT = "api/act";
    const API_MAPS = "api/maps";
    const API_DOCS = "api/docs";

    // ---- which named map this browser is viewing -------------------------
    // Maps are shared (no access control); the studio just picks one. The choice
    // lives in the URL (?map=<id>) so it's bookmarkable and survives reload.
    let currentMap = new URLSearchParams(loc.search).get("map") || null;
    let mapList = [];               // [{id, repo, modules, openSuggestions, orphans}]
    let defaultMap = null;
    let lastMapsJson = "";          // change-detect the map list across polls
    const mapListeners = new Set();

    function apiUrl(path) {
      // index.html is served at "/", so relative paths resolve against the host root.
      return new URL(path, doc.baseURI).toString();
    }

    function reportErr(e) {
      // surface backend rejections (e.g. duplicate id) without crashing the UI
      if (win.Studio && typeof win.Studio.toast === "function") {
        win.Studio.toast(String(e.message || e), "var(--leak)");
      } else { console.error("arch-map action error:", e); }
    }

    function _showWtFallback(result) {
      if (result && result.fallback && result.command && win.Studio && win.Studio.toast) {
        win.Studio.toast("Worktree not auto-created — run: " + result.command, "var(--accent)");
      }
    }

    // ---- the browser HTTP transport adapter (the production port) ----------
    // getModel/act/docAct/wtAct each inject the current map and return the
    // authoritative model as JSON text; a non-OK response throws Error(message).
    const transport = {
      async getModel() {
        const u = new URL(apiUrl(API_MODEL));
        if (currentMap) u.searchParams.set("map", currentMap);
        const res = await fetch(u.toString(), { headers: { "accept": "application/json" } });
        if (!res.ok) throw new Error("GET /api/model -> " + res.status);
        return res.text();
      },
      async act(body) {
        const res = await fetch(apiUrl(API_ACT), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(currentMap ? Object.assign({ map: currentMap }, body) : body),
        });
        if (!res.ok) {
          let msg = "action failed";
          try { msg = (await res.json()).error || msg; } catch (e) {}
          throw new Error(msg);
        }
        return res.text();
      },
      async docAct(body) {
        const res = await fetch(apiUrl(API_DOCS), {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify(currentMap ? Object.assign({ map: currentMap }, body) : body),
        });
        if (!res.ok) {
          let msg = "doc action failed";
          try { msg = (await res.json()).error || msg; } catch (e) {}
          throw new Error(msg);
        }
        return res.text();
      },
      async wtAct(body) {
        const res = await fetch(apiUrl("api/worktrees"), {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify(currentMap ? Object.assign({ map: currentMap }, body) : body),
        });
        if (!res.ok) {
          let msg = "worktree action failed";
          try { msg = (await res.json()).error || msg; } catch (e) {}
          throw new Error(msg);
        }
        const txt = await res.text();
        try { _showWtFallback(JSON.parse(txt)._worktreeResult); } catch (e) {}
        return txt;
      },
    };

    // ---- the core data layer, wired to the browser transport --------------
    const store = createStore({
      transport,
      onError: reportErr,
      // feed the doc-lens seam first so its subscribers see the fresh model before
      // the general listeners (it self-guards on a no-op).
      onBroadcast(s) { if (win.Arch && win.Arch.DocLens) { try { win.Arch.DocLens.setModel(s); } catch (e) {} } },
    });

    // ---- maps: the named maps this server holds (one per project) ---------
    function syncMapUrl() {
      const u = new URL(loc.href);
      if (currentMap) u.searchParams.set("map", currentMap); else u.searchParams.delete("map");
      win.history.replaceState(null, "", u.toString());
    }
    function notifyMaps() { mapListeners.forEach((fn) => { try { fn(mapList, currentMap); } catch (e) {} }); }

    async function fetchMaps() {
      try {
        const res = await fetch(apiUrl(API_MAPS), { headers: { "accept": "application/json" } });
        if (!res.ok) return;
        const data = await res.json();
        mapList = data.maps || [];
        defaultMap = data.default || (mapList[0] && mapList[0].id) || null;
        if (!currentMap || !mapList.some((m) => m.id === currentMap)) { currentMap = defaultMap; syncMapUrl(); }
        const j = JSON.stringify(mapList) + "|" + currentMap;
        if (j !== lastMapsJson) { lastMapsJson = j; notifyMaps(); }
      } catch (e) { /* keep last known map list */ }
    }

    async function switchMap(id) {
      if (!id || id === currentMap) return store.get();
      currentMap = id;
      syncMapUrl();
      await store.reload();   // bumps the write generation + force-adopts the new map's model
      notifyMaps();
      return store.get();
    }

    async function createMap(name) {
      try {
        const res = await fetch(apiUrl(API_MAPS), {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ op: "create", map: name, repo: name }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) { reportErr(new Error(data.error || "could not create map")); return null; }
        mapList = data.maps || mapList; lastMapsJson = "";
        if (data.created) { await switchMap(data.created); } else { notifyMaps(); }
        return data.created || null;
      } catch (e) { reportErr(e); return null; }
    }

    // ---- agent-bridge dispatch: "ask the agent to X" ----------------------
    // build the per-kind agent prompt (also the browser copy-paste fallback body)
    function dispatchPrompt(req) {
      const id = req.module || "";
      const model = store.get();
      const m = id ? model.modules.find((x) => x.id === id) : null;
      switch (req.kind) {
        case "fix": {
          const s = m && (m.suggestion || (req.suggestion_id
            ? (m.suggestions || []).find((x) => x.sid === req.suggestion_id) : null));
          return [
            "Fix module '" + id + "'" + (m ? " (" + (m.label || id) + ", domain '" + m.domain + "')" : "") + ".",
            s && s.problem ? "Why: " + s.problem : "",
            s && s.solution ? "How: " + s.solution : "",
          ].filter(Boolean).join("\n");
        }
        case "rescan": return "Re-scan module '" + id + "' for fresh signals.";
        case "realize": return "Realize planned module '" + id + "'.";
        case "triage": {
          const ids = (req.modules || []).join(", ");
          return "Triage the top critical modules: " + (ids || "(none)") + ".";
        }
        case "task": {
          const plan = (model.plans || []).find((p) => p.id === req.plan);
          const st = plan && (plan.steps || []).find((s) => s.id === req.step);
          const wt = st && st.worktree ? (model.worktrees || []).find((w) => w.id === st.worktree) : null;
          return [
            "Build task '" + (req.step || "") + "'" + (st ? " — " + st.title : "")
              + " (plan '" + (req.plan || "") + "'). This is a fathom:code build step.",
            st && st.interface ? "Interface (the test surface): " + st.interface : "",
            st && st.targets && st.targets.length ? "Target module(s): " + st.targets.join(", ") : "",
            wt && wt.path ? "Work INSIDE this task's worktree at " + wt.path + " (branch '" + wt.branch + "') — make all edits there." : "",
            "When the interface tests pass, move the card to 'review' and reconcile the modules you touched on the spine.",
          ].filter(Boolean).join("\n");
        }
        default: return "Agent request (" + req.kind + ")" + (id ? " for module '" + id + "'" : "") + ".";
      }
    }

    function showGrillFallback(prompt, resume) {
      if (win.Studio && typeof win.Studio.grillFallback === "function") return win.Studio.grillFallback(prompt, resume);
      const msg = "Grilling requested — paste into your agent: " + (resume || prompt);
      if (win.Studio && typeof win.Studio.toast === "function") win.Studio.toast(msg, "var(--accent, #6aa)");
      else console.info("[arch-map grill]", prompt, resume || "");
    }

    async function browserGrill(map, module) {
      const res = await fetch(apiUrl("api/grill"), {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ map, module }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok || d.error) throw new Error(d.error || "could not request grilling");
      return d;   // { prompt, resume }
    }

    // Stream an /api/dispatch SSE run, forwarding each frame to Studio.dispatchProgress
    // (the rail renders it as a live activity feed). On stream end, re-sync the model.
    async function consumeDispatchStream(res, req) {
      const progress = (win.Studio && win.Studio.dispatchProgress) || null;
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      try {
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf("\n\n")) >= 0) {
            const frame = buf.slice(0, i); buf = buf.slice(i + 2);
            const ev = frame.match(/^event: (.*)$/m);
            const da = frame.match(/^data: (.*)$/m);
            if (!da) continue;
            let data; try { data = JSON.parse(da[1]); } catch (e) { continue; }
            if (progress) progress({ phase: ev ? ev[1] : "progress", data, req });
          }
        }
      } finally {
        if (progress) progress({ phase: "end", req });
        if (req.module && win.Studio && win.Studio.onModelMutated) win.Studio.onModelMutated(req.module);
        store.refetch(true);                              // pull the agent's map/source changes now
      }
    }

    async function browserDispatch(map, req) {
      if (req.kind === "grill") {
        const d = await browserGrill(map, req.module);   // proven /api/grill path
        showGrillFallback(d.prompt, d.resume);
        return d;
      }
      // Try the live agent bridge (/api/dispatch streams SSE). If it's disabled (503),
      // unreachable, or errors, fall back to surfacing the prompt for copy-paste.
      const prompt = dispatchPrompt(req);
      let res;
      try {
        res = await fetch(apiUrl("api/dispatch"), {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ map, kind: req.kind, module: req.module,
                                 modules: req.modules, suggestion_id: req.suggestion_id,
                                 plan: req.plan, step: req.step }),
        });
      } catch (e) { showGrillFallback(prompt, null); return { prompt }; }
      if (!res.ok || !res.body) { showGrillFallback(prompt, null); return { prompt }; }
      await consumeDispatchStream(res, req);
      return { prompt, streamed: true };
    }

    // ---- Store: the core data layer + the browser-only agent bridges ------
    store.dispatch = function (req) {
      // Generalized "ask the agent to X" router. Routes fix / rescan / realize /
      // triage / grill through /api/dispatch (SSE) or /api/grill, with a copy-paste
      // fallback. Fire-and-forget; the rail wrapper toasts + re-syncs.
      if (!req || !req.kind) return store.get();
      browserDispatch(currentMap, req).catch(reportErr);
      return store.get();
    };
    store.grill = function (id) {
      // Hand a candidate off to the /deepen grilling loop. Thin alias over dispatch;
      // surfaces the prompt + a resume line to paste, and persists the request.
      return store.dispatch({ kind: "grill", module: id });
    };
    store.whatif = function (ids) {
      // what-if merge preview (pure READ: GET /api/whatif). Never mutates the map.
      const u = new URL(apiUrl("api/whatif"));
      if (currentMap) u.searchParams.set("map", currentMap);
      u.searchParams.set("ids", (ids || []).join(","));
      return fetch(u.toString(), { headers: { "accept": "application/json" } })
        .then(async (res) => {
          const d = await res.json().catch(() => ({}));
          if (!res.ok || d.error) throw new Error(d.error || "what-if preview failed");
          return d;
        });
    };

    // ---- poll + focus reconcile -------------------------------------------
    // refetch self-guards on pendingWrites/writeGen, so a poll can never clobber an
    // in-flight optimistic write.
    win.setInterval(() => { if (!store.pending()) { store.refetch(true); fetchMaps(); } }, POLL_MS);
    win.addEventListener("focus", () => { if (!store.pending()) { store.refetch(true); fetchMaps(); } });

    // ---- boot: load the map list + the current map's model before render --
    let readyResolved = false;
    const readyCbs = [];
    function whenReady(cb) { readyResolved ? cb() : readyCbs.push(cb); }
    (async function () {
      try { await fetchMaps(); } catch (e) { /* fall back to the default map */ }
      try { if (!(await store.refetch(false))) { /* unchanged or unreachable; poll will retry */ } }
      catch (e) { console.error("arch-map: could not load /api/model", e); }
      readyResolved = true;
      readyCbs.splice(0).forEach((cb) => { try { cb(); } catch (e) {} });
    })();

    // ---- prefs (theme + aesthetic direction): client-side, localStorage ---
    const prefListeners = new Set();
    const Prefs = {
      get() {
        try { return Object.assign({ theme: "light", dir: "a" }, JSON.parse(win.localStorage.getItem(PREF_KEY) || "{}")); }
        catch (e) { return { theme: "light", dir: "a" }; }
      },
      set(patch) {
        const p = Object.assign(this.get(), patch);
        try { win.localStorage.setItem(PREF_KEY, JSON.stringify(p)); } catch (e) {}
        prefListeners.forEach((fn) => fn(p));
        return p;
      },
    };
    function subscribePrefs(fn) { prefListeners.add(fn); return () => prefListeners.delete(fn); }
    win.addEventListener("storage", (e) => {
      if (e.key === PREF_KEY) { const p = Prefs.get(); prefListeners.forEach((fn) => fn(p)); }
    });

    // named maps (one per project); shared, addressed by id
    const Maps = {
      list: () => mapList.slice(),
      current: () => currentMap,
      switchTo: switchMap,
      create: createMap,
      refresh: fetchMaps,
      subscribe(fn) { mapListeners.add(fn); return () => mapListeners.delete(fn); },
    };

    win.Arch = Object.assign(win.Arch || {}, {
      Store: store, subscribe: store.subscribe, subscribePrefs, Prefs, whenReady, Maps,
      tierOf, isOrphan, isOpen, openSuggestions, diffModels,
      STRENGTHS: {
        strong: { label: "Strong", short: "strong" },
        worth: { label: "Worth exploring", short: "worth" },
        speculative: { label: "Speculative", short: "speculative" },
      },
    });
  }

  if (root && typeof root.document !== "undefined") boot(root);

  // Node (tests): export the pure transforms + the store factory. No browser code runs.
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      createStore, normalize,
      strengthKey, testsToArray, testsToString, denormFields,
      tierOf, isOrphan, isOpen, openSuggestions, diffModels,
    };
  }
})(typeof window !== "undefined" ? window : null);
