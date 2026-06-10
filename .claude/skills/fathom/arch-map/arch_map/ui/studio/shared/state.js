/* arch-map studio — shared state (backend-backed)
 *
 * This is the production data layer for the unified studio. It exposes the SAME
 * window.Arch API surface the design prototype used (Store / subscribe / tierOf /
 * isOrphan / openSuggestions / STRENGTHS / Prefs), but instead of localStorage it
 * talks to the real FastMCP HTTP backend:
 *
 *   GET  /api/model           -> the full ArchModel (single source of truth)
 *   POST /api/act {action,..}  -> mutate arch_state.json under a lock, returns model
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
 *                      studio expects a separate decisions[moduleId] map
 *
 * A module is a "candidate" when it carries a suggestion; it is "open" when that
 * suggestion has no decision yet. Accept/Defer/Reject record a decision (the
 * suggestion stays, with a verdict badge); Dismiss resolves it (removes it).
 *
 * Cross-surface sync (the agent via MCP tools, the desktop app, another browser
 * tab) is handled by polling /api/model every 2.5s — the same cadence the
 * prototype simulated. A change anywhere shows up everywhere without a reload.
 */
(function () {
  "use strict";

  const PREF_KEY = "archmap.prefs.v1";
  const POLL_MS = 2500;
  const API_MODEL = "api/model";
  const API_ACT = "api/act";
  const API_MAPS = "api/maps";
  const API_DOCS = "api/docs";

  // ---- transport: HTTP (browser at /) vs MCP-App host (Claude desktop, etc.) -
  // The server inlines this studio as an MCP-App resource and sets __ARCH_APP__,
  // because a sandboxed iframe can't reach the HTTP server. In host mode we talk
  // to the host via @modelcontextprotocol/ext-apps: the model arrives from the
  // show_map/get_full_model tools and edits route through app.callServerTool to the
  // action-dispatch tools — mirroring network.html's proven bridge. Everything
  // host-specific is gated on HOST so the browser path is untouched.
  const HOST = typeof window !== "undefined" && !!window.__ARCH_APP__;

  // ---- which named map this browser is viewing -----------------------------
  // Maps are shared (no access control); the studio just picks one. The choice
  // lives in the URL (?map=<id>) so it's bookmarkable and survives reload. Every
  // request to the server carries this id; switching reloads the whole model.
  let currentMap = new URLSearchParams(location.search).get("map") || null;
  let mapList = [];               // [{id, repo, modules, openSuggestions, orphans}]
  let defaultMap = null;
  let lastMapsJson = "";          // change-detect the map list across polls
  const mapListeners = new Set();

  // ---- in-memory cache: the synchronous view the studio renders from --------
  // The studio code calls Store.get() / Store.decide(...) synchronously and
  // expects an immediate model back, so we keep a live normalized cache here.
  // Reads return it; writes update it optimistically, then a background POST
  // reconciles against the authoritative server response.
  let cur = { repo: "", modules: [], plans: [], docs: [], docMembership: {}, decisions: {}, seq: 0 };
  let lastServerJson = "";       // raw JSON of the last authoritative model
  let pendingWrites = 0;         // in-flight POSTs (gates poll-reconcile)
  let writeGen = 0;              // bumps per optimistic write; gates stale server snapshots
  let readyResolved = false;
  const readyCbs = [];

  function apiUrl(path) {
    // index.html is served at "/", so relative paths resolve against the host root.
    return new URL(path, document.baseURI).toString();
  }

  // ---- normalize: backend ArchModel -> studio model ------------------------
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
      })),
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
  function normalize(raw) {
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
    return { repo: raw.repo || "", modules, plans, docs,
             docMembership: raw.docMembership || {}, decisions, seq: (cur.seq || 0) + 1 };
  }

  // ---- find the backend suggestion id for a module (for decide/resolve) -----
  function sidFor(id) {
    const m = cur.modules.find((x) => x.id === id);
    return m && m.suggestion ? m.suggestion.sid : null;
  }

  // ---- server I/O -----------------------------------------------------------
  // The cache is reconciled by exactly two sources — the response to a write
  // (act) and the background poll (refetch). Both can arrive out of order, so a
  // monotonic `writeGen` gates them: a server snapshot is only adopted if no
  // newer optimistic write has happened since it was requested. Without this, a
  // stale in-flight GET (or an older POST response) could clobber a newer
  // optimistic value and the UI would visibly revert until the next poll.
  function applyServerModel(rawText) {
    if (rawText === lastServerJson) return false;  // byte-identical: nothing changed
    lastServerJson = rawText;
    Store.prevModel = cur;                          // expose the pre-swap model for diffing (item 10)
    cur = normalize(JSON.parse(rawText));
    return true;
  }

  function adoptServer(rawText) {
    // force the cache to server truth, bypassing the byte short-circuit — used to
    // roll back a rejected optimistic write even when server state is unchanged.
    lastServerJson = rawText;
    Store.prevModel = cur;                          // expose the pre-swap model for diffing (item 10)
    cur = normalize(JSON.parse(rawText));
    broadcast(cur);
  }

  // ---- MCP-App host bridge (only used when HOST) ----------------------------
  let _appPromise = null;
  function resultModel(r) {                 // pull a model object out of a tool result
    let m = r && r.structuredContent;
    if (!m && r && Array.isArray(r.content)) {
      const t = r.content.find((c) => c && c.type === "text");
      if (t && t.text) { try { m = JSON.parse(t.text); } catch (e) {} }
    }
    return m && typeof m === "object" ? m : null;
  }
  function hostConnect() {
    if (_appPromise) return _appPromise;
    _appPromise = (async () => {
      const { App } = await import("https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@1.7.2/+esm");
      const app = new App({ name: "arch-map", version: "1.0.0" });
      app.ontoolresult = (r) => {            // the host pushes the agent's show_map/get_model result
        const m = resultModel(r);
        const mid = m && m.map ? m.map : null;
        if (mid && mid !== currentMap) { currentMap = mid; }
        if (m && Array.isArray(m.modules) && m.modules.some((x) => "iface" in x || "files" in x)) {
          if (adoptModelObject(m)) broadcast(cur);     // a full model — render it directly
        } else if (mid) { hostRefresh(); }             // lightweight (show_map) — hydrate via get_model
      };
      // a real host completes the handshake fast; race a timeout so we never hang
      const ok = await Promise.race([
        app.connect().then(() => true),
        new Promise((res) => setTimeout(() => res(false), 2500)),
      ]);
      if (!ok) throw new Error("no MCP-App host responded");
      return app;
    })();
    return _appPromise;
  }
  async function hostCall(name, args) {
    const app = await hostConnect();
    return resultModel(await app.callServerTool({ name, arguments: args || {} }));
  }
  function adoptModelObject(obj) {
    const txt = JSON.stringify(obj);
    if (txt === lastServerJson) return false;
    lastServerJson = txt; Store.prevModel = cur; cur = normalize(obj); return true;
  }
  async function hostRefresh() {
    if (!currentMap) return false;
    const full = await hostCall("get_full_model", { map: currentMap });
    if (full && adoptModelObject(full)) { broadcast(cur); return true; }
    return false;
  }

  async function fetchModel() {
    if (HOST) {
      if (!currentMap) return lastServerJson || JSON.stringify({ repo: "", modules: [], plans: [], orphans: [], openSuggestions: [] });
      const full = await hostCall("get_full_model", { map: currentMap });
      return JSON.stringify(full || { repo: "", modules: [], plans: [], orphans: [], openSuggestions: [] });
    }
    const u = new URL(apiUrl(API_MODEL));
    if (currentMap) u.searchParams.set("map", currentMap);
    const res = await fetch(u.toString(), { headers: { "accept": "application/json" } });
    if (!res.ok) throw new Error("GET /api/model -> " + res.status);
    return res.text();
  }

  // ---- maps: the named maps this server holds (one per project) ------------
  function syncMapUrl() {
    const u = new URL(location.href);
    if (currentMap) u.searchParams.set("map", currentMap); else u.searchParams.delete("map");
    history.replaceState(null, "", u.toString());
  }
  function notifyMaps() { mapListeners.forEach((fn) => { try { fn(mapList, currentMap); } catch (e) {} }); }

  async function fetchMaps() {
    if (HOST) {
      try {
        const r = await hostCall("list_maps", {});
        if (r && r.maps) {
          mapList = r.maps;
          defaultMap = r.default || (mapList[0] && mapList[0].id) || null;
          // currentMap is set by the host (ontoolresult), not the default — leave it
          const j = JSON.stringify(mapList) + "|" + currentMap;
          if (j !== lastMapsJson) { lastMapsJson = j; notifyMaps(); }
        }
      } catch (e) { /* keep last known map list */ }
      return;
    }
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
    if (!id || id === currentMap) return cur;
    currentMap = id;
    ++writeGen;             // invalidate any in-flight poll for the previous map
    if (!HOST) syncMapUrl();
    lastServerJson = "";    // force-adopt the new map's model
    try { applyServerModel(await fetchModel()); } catch (e) {}
    broadcast(cur);
    notifyMaps();
    return cur;
  }

  async function createMap(name) {
    if (HOST) {
      try {
        const r = await hostCall("create_project", { name });
        const mid = r && r.map ? r.map : null;
        lastMapsJson = ""; await fetchMaps();
        if (mid) await switchMap(mid); else notifyMaps();
        return mid;
      } catch (e) { reportErr(e); return null; }
    }
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

  // background poll / focus reconcile — must never clobber an optimistic write
  async function refetch(broadcastIfChanged) {
    const gen = writeGen;
    try {
      const txt = await fetchModel();
      // a write started or is still in flight since we asked: its own reconcile wins
      if (pendingWrites > 0 || writeGen !== gen) return false;
      const changed = applyServerModel(txt);
      if (changed && broadcastIfChanged) broadcast(cur);
      return changed;
    } catch (e) { /* server momentarily unreachable; keep last good cache */ return false; }
  }

  // translate a Store action into the equivalent MCP tool call (host mode)
  function _toolFor(map, a) {
    // a.action is the studio's internal action key; the FIRST array element is the
    // real MCP tool name — the action-dispatch tools (modules / suggestions / plans),
    // with the studio's action mapped to the dispatcher's `action` + flat args.
    switch (a.action) {
      case "set_depth": return ["modules", { map, action: "update", id: a.module, depth: a.score }];
      case "set_coverage": return ["modules", { map, action: "update", id: a.module, coverage: a.fraction }];
      case "decide": return ["suggestions", { map, action: "decide", suggestion_id: a.suggestion_id, decision: a.decision, note: a.note || "" }];
      case "resolve": return ["suggestions", { map, action: "dismiss", suggestion_id: a.suggestion_id }];
      case "delete": return ["modules", { map, action: "delete", id: a.module }];
      case "update": return ["modules", Object.assign({ map, action: "update", id: a.module }, denormFields(a.fields || {}))];
      case "add": return ["modules", Object.assign({ map, action: "add" }, a.module)];
      case "set_step_status": return ["plans", { map, action: "set_step_status", plan_id: a.plan_id, step_id: a.step_id, step_status: a.status }];
      default: throw new Error("unsupported action: " + a.action);
    }
  }
  async function hostAct(body) {
    const myGen = ++writeGen;
    pendingWrites++;
    const map = currentMap;
    try {
      const [name, args] = _toolFor(map, body);
      await hostCall(name, args);                       // tools return a compact ack...
      const full = await hostCall("get_full_model", { map }); // ...so re-pull the full model
      if (myGen === writeGen && full && adoptModelObject(full)) broadcast(cur);
    } catch (e) {
      if (myGen === writeGen) { try { const f = await hostCall("get_full_model", { map }); if (f && adoptModelObject(f)) broadcast(cur); } catch (_) {} }
      throw e;
    } finally {
      pendingWrites--;
    }
  }

  // ---- grill hand-off: UI -> agent turn (MCP-App) or copy-paste (browser) ---
  // "Grill this candidate" routes here. callServerTool persists the request and
  // returns the canonical prompt but the result stays in the iframe; only
  // app.sendMessage (ui/message) posts a message AND triggers an agent turn, and
  // app.updateModelContext stages the candidate body for that turn — both
  // feature-gated on the host's advertised capabilities, role hardcoded "user"
  // (the only value ext-apps@1.7.2 accepts). A plain browser can't trigger a turn,
  // so it POSTs /api/grill and surfaces the prompt + a "resume <map>" line.
  function grillBody(m) {
    if (!m) return "";
    const s = m.suggestion;
    return [
      "Candidate to grill: " + ((s && s.title) || m.label) + " (module '" + m.id + "', domain '" + m.domain + "').",
      "Depth " + m.depth + "/100, coverage " + m.coverage + "%.",
      s && s.problem ? "Problem: " + s.problem : "",
      s && s.solution ? "Solution: " + s.solution : "",
      s && s.wins && s.wins.length ? "Wins: " + s.wins.join("; ") : "",
      m.interface ? "Interface: " + m.interface : "",
    ].filter(Boolean).join("\n");
  }
  function grillText(r, module) {                  // start_grilling returns a TEXT prompt
    if (r && Array.isArray(r.content)) {
      const t = r.content.find((c) => c && c.type === "text");
      if (t && t.text) return t.text;
    }
    if (r && typeof r.structuredContent === "string") return r.structuredContent;
    return "Enter the /deepen grilling loop for module '" + module + "'.";
  }
  function showGrillFallback(prompt, resume) {
    if (window.Studio && typeof window.Studio.grillFallback === "function") return window.Studio.grillFallback(prompt, resume);
    const msg = "Grilling requested — paste into your agent: " + (resume || prompt);
    if (window.Studio && typeof window.Studio.toast === "function") window.Studio.toast(msg, "var(--accent, #6aa)");
    else console.info("[arch-map grill]", prompt, resume || "");
  }
  async function hostGrill(map, module, body) {
    const app = await hostConnect();
    const caps = (app.getHostCapabilities && app.getHostCapabilities()) || {};
    let prompt;
    try {                                          // (1) persist 'requested' + get the prompt (iframe-only)
      prompt = grillText(await app.callServerTool({ name: "grilling", arguments: { map, action: "start", module } }), module);
    } catch (e) { prompt = grillText(null, module); }
    if (!caps.message) return { triggered: false, prompt, reason: "no-message-capability" };
    try {                                          // (2) stage the candidate body for the next turn (no trigger)
      if (caps.updateModelContext && body) await app.updateModelContext({ content: [{ type: "text", text: body }] });
    } catch (e) { /* best-effort */ }
    const sent = await app.sendMessage({ role: "user", content: [{ type: "text", text: prompt }] });  // (3) the trigger
    return { triggered: !(sent && sent.isError), prompt };
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

  // ---- generalized dispatch: "ask the agent to X" (item 11) -----------------
  // grill() proved the pattern (persist a request, stage a body, trigger an agent
  // turn via sendMessage; browser falls back to a copy-paste prompt). dispatch
  // reuses that exact plumbing for the other actionable asks — fix / rescan /
  // realize / triage — so every "Ask agent to …" button rides one code path.
  //
  // Host mode maps `kind` to the live MCP tool(s); a successful sendMessage IS the
  // agent turn. Browser mode has no generic /api/dispatch endpoint (only
  // /api/grill exists, see assumption below), so non-grill kinds surface the
  // prompt for copy-paste — satisfying item 11's "browser fallback surfaces a
  // prompt". `kind:"grill"` keeps using the proven hostGrill/browserGrill paths
  // verbatim, so Store.grill stays a thin alias and its behavior is unchanged.

  // build the per-kind agent prompt (also the browser copy-paste fallback body)
  function dispatchPrompt(req) {
    const id = req.module || "";
    const m = id ? find(id) : null;
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
      case "grill": return grillBody(m);
      default: return "Agent request (" + req.kind + ")" + (id ? " for module '" + id + "'" : "") + ".";
    }
  }

  // host: which MCP tool(s) carry out each kind (1.6). Each entry is a [name, args]
  // invoked best-effort before staging the body + sendMessage. Only tools whose
  // full arg shape we can supply here are pre-called; the rest are left to the
  // agent turn the prompt triggers (flag_deepening needs title/strength/problem/…
  // the agent authors, scan_signals takes no module, so we don't pre-call those —
  // we re-scan via modules(action="update", updated=false) to clear the stale halo and let the agent
  // re-evaluate). This keeps strict (additionalProperties:false) hosts from
  // rejecting a malformed pre-call.
  function dispatchTools(map, req) {
    switch (req.kind) {
      case "rescan":  return [["modules", { map, action: "update", id: req.module, updated: false }]];
      case "realize": return [["modules", { map, action: "realize", id: req.module }]];
      default:        return [];   // fix / triage: the sendMessage turn does the work
    }
  }

  async function hostDispatch(map, req) {
    if (req.kind === "grill") return hostGrill(map, req.module, dispatchPrompt(req));
    const app = await hostConnect();
    const caps = (app.getHostCapabilities && app.getHostCapabilities()) || {};
    const body = dispatchPrompt(req);
    // (1) carry out the underlying tool(s) — best-effort, mirrors start_grilling's persist step
    for (const [name, args] of dispatchTools(map, req)) {
      try { await app.callServerTool({ name, arguments: args }); } catch (e) { /* best-effort */ }
    }
    if (!caps.message) return { triggered: false, prompt: body, reason: "no-message-capability" };
    try {                                          // (2) stage the request body for the next turn (no trigger)
      if (caps.updateModelContext && body) await app.updateModelContext({ content: [{ type: "text", text: body }] });
    } catch (e) { /* best-effort */ }
    const sent = await app.sendMessage({ role: "user", content: [{ type: "text", text: body }] });  // (3) the trigger
    return { triggered: !(sent && sent.isError), prompt: body };
  }

  async function browserDispatch(map, req) {
    if (req.kind === "grill") {
      const d = await browserGrill(map, req.module);   // proven /api/grill path
      showGrillFallback(d.prompt, d.resume);
      return d;
    }
    // No generic /api/dispatch backend (assumption 1): surface the prompt to paste.
    const prompt = dispatchPrompt(req);
    showGrillFallback(prompt, null);
    return { prompt };
  }

  // POST an action; reconcile the cache from the authoritative response.
  async function act(body) {
    if (body && body.action === "update" && body.fields) {
      body = Object.assign({}, body, { fields: denormFields(body.fields) });
    }
    if (HOST) return hostAct(body);
    const myGen = ++writeGen;   // this is now the newest write
    pendingWrites++;
    try {
      const res = await fetch(apiUrl(API_ACT), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(currentMap ? Object.assign({ map: currentMap }, body) : body),
      });
      if (!res.ok) {
        let msg = "action failed";
        try { msg = (await res.json()).error || msg; } catch (e) {}
        // roll back this rejected optimistic write to server truth, unless a newer
        // write has superseded it (then the newer write's reconcile is authoritative)
        if (myGen === writeGen) { try { adoptServer(await fetchModel()); } catch (e) {} }
        throw new Error(msg);
      }
      const txt = await res.text();
      // only the latest write reconciles; an older response would revert a newer optimistic value
      if (myGen === writeGen && applyServerModel(txt)) broadcast(cur);
    } finally {
      pendingWrites--;
    }
  }

  // ---- docs: mutate via /api/docs (browser) or the doc tools (host) ---------
  // Separate endpoint from /api/act — docs route through the server's single
  // _apply_doc dispatch. Non-optimistic: the POST returns the full model (with the
  // doc's scope freshly resolved), which reconciles the cache. Mirrors act()'s
  // writeGen/pendingWrites discipline so polls never clobber an in-flight write.
  function _docToolFor(map, body) {
    switch (body.op) {
      case "add": {
        const { id, ...rest } = body.doc;   // docs dispatcher takes doc_id, not id
        return ["docs", Object.assign({ map, action: "add", doc_id: id }, rest)];
      }
      case "update": return ["docs", Object.assign({ map, action: "update", doc_id: body.doc_id }, body.fields || {})];
      case "delete": return ["docs", { map, action: "delete", doc_id: body.doc_id }];
      default: throw new Error("unsupported doc op: " + body.op);
    }
  }
  async function docAct(body) {
    if (HOST) {
      const myGen = ++writeGen; pendingWrites++; const map = currentMap;
      try {
        const [name, args] = _docToolFor(map, body);
        await hostCall(name, args);
        const full = await hostCall("get_full_model", { map });
        if (myGen === writeGen && full && adoptModelObject(full)) broadcast(cur);
      } catch (e) {
        if (myGen === writeGen) { try { const f = await hostCall("get_full_model", { map }); if (f && adoptModelObject(f)) broadcast(cur); } catch (_) {} }
        throw e;
      } finally { pendingWrites--; }
      return;
    }
    const myGen = ++writeGen; pendingWrites++;
    try {
      const res = await fetch(apiUrl(API_DOCS), {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify(currentMap ? Object.assign({ map: currentMap }, body) : body),
      });
      if (!res.ok) {
        let msg = "doc action failed";
        try { msg = (await res.json()).error || msg; } catch (e) {}
        if (myGen === writeGen) { try { adoptServer(await fetchModel()); } catch (e) {} }
        throw new Error(msg);
      }
      const txt = await res.text();
      if (myGen === writeGen && applyServerModel(txt)) broadcast(cur);
    } finally { pendingWrites--; }
  }

  // ---- optimistic local mutation helpers -----------------------------------
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

  // ---- model API (mirrors the prototype's synchronous Store) ---------------
  const Store = {
    get() { return cur; },

    // the model as it was before the most recent server swap, so onExternal
    // consumers can diff old→new for narration (item 10). null until first swap.
    prevModel: null,
    // snapshot of the last module removed via deleteModule, for undo (item 16).
    // { module, edges:[{from,field,to}], decision } | null
    lastDeleted: null,

    reset() { refetch(true); return cur; },   // no client seed: re-sync from server

    setDepth(id, delta) {
      const m = find(id);
      if (m) { m.depth = clamp(m.depth + delta); m.updated = true; bump(); }
      act({ action: "set_depth", module: id, score: (m ? m.depth : 0) / 100 }).catch(reportErr);
      return cur;
    },
    setCoverage(id, delta) {
      const m = find(id);
      if (m) { m.coverage = clamp(m.coverage + delta); m.updated = true; bump(); }
      act({ action: "set_coverage", module: id, fraction: (m ? m.coverage : 0) / 100 }).catch(reportErr);
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
      act({ action: "add", module: { id, label: label || id, domain: domain || "uncategorized" } }).catch(reportErr);
      return cur;
    },
    deleteModule(id) {
      // snapshot before mutating so undoDelete can re-create the module and every
      // inbound edge it strips off other modules (item 16).
      const gone = cur.modules.find((x) => x.id === id);
      const inbound = [];
      cur.modules.forEach((m) => {
        if ((m.dependsOn || []).includes(id)) inbound.push({ from: m.id, field: "dependsOn", to: id });
        if ((m.leaks || []).includes(id))     inbound.push({ from: m.id, field: "leaksTo",   to: id });
      });
      Store.lastDeleted = gone
        ? { module: JSON.parse(JSON.stringify(gone)), edges: inbound, decision: cur.decisions[id] }
        : null;

      cur.modules = cur.modules.filter((x) => x.id !== id);
      cur.modules.forEach((m) => {
        m.dependsOn = m.dependsOn.filter((d) => d !== id);
        m.leaks = (m.leaks || []).filter((d) => d !== id);
      });
      delete cur.decisions[id];
      bump();
      act({ action: "delete", module: id }).catch(reportErr);
      return cur;
    },
    undoDelete() {
      // re-add the last-deleted module and its inbound edges. Optimistic locally,
      // then re-create on the server (no native "undelete" — assumption 2): add the
      // module, restore its captured fields via update_module, and re-point each
      // referrer's dependsOn/leaksTo back at it.
      const snap = Store.lastDeleted;
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
      Store.lastDeleted = null;

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
        .catch(reportErr);
      return cur;
    },
    decide(sid, verdict, reason) {
      // the proposal must still exist on the server to record a decision against it
      if (!findSug(sid)) { reportErr(new Error("proposal " + sid + " no longer exists")); refetch(true); return cur; }
      cur.decisions[sid] = { verdict, reason: reason || "", adr: "", at: null };
      bump();
      act({ action: "decide", suggestion_id: sid, decision: VERDICT_TO_DECISION[verdict] || verdict, note: reason || "" }).catch(reportErr);
      return cur;
    },
    reopen(sid) {
      // undo a decision: re-open the proposal (decision back to "")
      delete cur.decisions[sid];
      bump();
      act({ action: "decide", suggestion_id: sid, decision: "", note: "" }).catch(reportErr);
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
      act({ action: "resolve", suggestion_id: sid }).catch(reportErr);
      return cur;
    },
    setStepStatus(planId, stepId, status) {
      const plan = (cur.plans || []).find((p) => p.id === planId);
      if (plan) {
        const step = (plan.steps || []).find((s) => s.id === stepId);
        if (step) { step.status = status; bump(); }
      }
      act({ action: "set_step_status", plan_id: planId, step_id: stepId, status }).catch(reportErr);
      return cur;
    },
    dispatch(req) {
      // Generalized "ask the agent to X" router (item 11). Routes fix / rescan /
      // realize / triage / grill through the same host grill bridge (MCP-App
      // sendMessage) with a browser fallback that surfaces the prompt. Fire-and-
      // forget like the other mutators; the rail wrapper toasts + re-syncs.
      if (!req || !req.kind) return cur;
      const map = currentMap;
      if (HOST) {
        hostDispatch(map, req).then((r) => { if (r && !r.triggered) showGrillFallback(r.prompt, null); }).catch(reportErr);
      } else {
        browserDispatch(map, req).catch(reportErr);
      }
      return cur;
    },
    grill(id) {
      // Hand a candidate off to the /deepen grilling loop. Thin alias over the
      // generalized dispatch router (item 11) — the kind:"grill" branch keeps the
      // proven hostGrill/browserGrill paths verbatim, so behavior is unchanged. In
      // an MCP-App host this triggers an agent turn (sendMessage); in a browser it
      // surfaces the prompt + a resume line to paste. Either way the candidate is
      // persisted 'requested'.
      return Store.dispatch({ kind: "grill", module: id });
    },

    // ---- docs (scoped architecture documents) ----
    // doc is {id,type,title,scope,summary,body,status,tags,supersedes,adrRef,author}.
    addDoc(doc) { docAct({ op: "add", doc }).catch(reportErr); return cur; },
    updateDoc(docId, fields) { docAct({ op: "update", doc_id: docId, fields }).catch(reportErr); return cur; },
    deleteDoc(docId) { docAct({ op: "delete", doc_id: docId }).catch(reportErr); return cur; },
  };

  function reportErr(e) {
    // surface backend rejections (e.g. duplicate id) without crashing the UI
    if (window.Studio && typeof window.Studio.toast === "function") {
      window.Studio.toast(String(e.message || e), "var(--leak)");
    } else { console.error("arch-map action error:", e); }
  }

  // ---- broadcast / subscribe -----------------------------------------------
  const listeners = new Set();
  function broadcast(s) {
    // feed the doc lens seam first (it self-guards on no-op), so its subscribers
    // (graph highlight, doc browser) see the fresh model before the general listeners.
    if (window.Arch && window.Arch.DocLens) { try { window.Arch.DocLens.setModel(s); } catch (e) {} }
    listeners.forEach((fn) => { try { fn(s); } catch (e) {} });
  }
  function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }

  // poll the server — picks up model + map-list changes from the agent / desktop / other tabs
  setInterval(() => { if (pendingWrites === 0) { refetch(true); fetchMaps(); } }, POLL_MS);
  // also refresh when the tab regains focus, for snappier cross-surface sync
  window.addEventListener("focus", () => { if (pendingWrites === 0) { refetch(true); fetchMaps(); } });

  // ---- boot: load the map list + the current map's model before rendering --
  function whenReady(cb) { readyResolved ? cb() : readyCbs.push(cb); }
  (async function boot() {
    if (HOST) {
      // Host mode: connect to the MCP-App host; the agent's show_map(map=…) result
      // arrives via ontoolresult and drives currentMap + the first render. We don't
      // pull a model up front (the map isn't known yet), so the studio renders empty
      // for an instant, then fills the moment the host pushes.
      try { await hostConnect(); await fetchMaps(); }
      catch (e) { console.error("arch-map: MCP-App connect failed", e); }
      readyResolved = true;
      readyCbs.splice(0).forEach((cb) => { try { cb(); } catch (e) {} });
      return;
    }
    try { await fetchMaps(); } catch (e) { /* fall back to the default map */ }
    try { applyServerModel(await fetchModel()); }
    catch (e) { console.error("arch-map: could not load /api/model", e); }
    readyResolved = true;
    readyCbs.splice(0).forEach((cb) => { try { cb(); } catch (e) {} });
  })();

  // ---- prefs (theme + aesthetic direction): client-side, localStorage ------
  const Prefs = {
    get() {
      try { return Object.assign({ theme: "light", dir: "a" }, JSON.parse(localStorage.getItem(PREF_KEY) || "{}")); }
      catch (e) { return { theme: "light", dir: "a" }; }
    },
    set(patch) {
      const p = Object.assign(this.get(), patch);
      try { localStorage.setItem(PREF_KEY, JSON.stringify(p)); } catch (e) {}
      prefListeners.forEach((fn) => fn(p));
      return p;
    },
  };
  const prefListeners = new Set();
  function subscribePrefs(fn) { prefListeners.add(fn); return () => prefListeners.delete(fn); }
  window.addEventListener("storage", (e) => {
    if (e.key === PREF_KEY) { const p = Prefs.get(); prefListeners.forEach((fn) => fn(p)); }
  });

  // ---- derived helpers (unchanged from the prototype) ----------------------
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

  // ---- model diff: narrate agent edits (item 10) ---------------------------
  // Pure helper. Given two NORMALIZED models (prev, next — the studio shapes, not
  // the raw backend payloads), return a flat list of field-level changes for the
  // activity feed to format into human verbs. Synthetic +module / -module rows are
  // emitted for added / removed modules. No I/O — safe to call on every poll diff.
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

  // named maps (one per project); shared, addressed by id
  const Maps = {
    list: () => mapList.slice(),
    current: () => currentMap,
    switchTo: switchMap,
    create: createMap,
    refresh: fetchMaps,
    subscribe(fn) { mapListeners.add(fn); return () => mapListeners.delete(fn); },
  };

  window.Arch = {
    Store, subscribe, subscribePrefs, Prefs, whenReady, Maps,
    tierOf, isOrphan, isOpen, openSuggestions, diffModels,
    STRENGTHS: {
      strong: { label: "Strong", short: "strong" },
      worth: { label: "Worth exploring", short: "worth" },
      speculative: { label: "Speculative", short: "speculative" },
    },
  };
})();
