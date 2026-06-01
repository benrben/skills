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

  // ---- transport: HTTP (browser at /) vs MCP-App host (Claude desktop, etc.) -
  // The server inlines this studio as an MCP-App resource and sets __ARCH_APP__,
  // because a sandboxed iframe can't reach the HTTP server. In host mode we talk
  // to the host via @modelcontextprotocol/ext-apps: the model arrives from the
  // show_map/get_model tools and edits route through app.callServerTool to the
  // real tools — mirroring network.html's proven bridge. Everything host-specific
  // is gated on HOST so the browser path is untouched.
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
  let cur = { repo: "", modules: [], decisions: {}, seq: 0 };
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

  function normalize(raw) {
    const decisions = {};
    const modules = (raw.modules || []).map((m) => {
      const s = m.suggestion;
      let suggestion = null;
      if (s) {
        const key = STRENGTH_TO_KEY[s.strength] || strengthKey(s.strength);
        suggestion = {
          sid: s.id,
          strength: key,
          title: s.title || "",
          problem: s.problem || "",
          solution: s.solution || "",
          wins: Array.isArray(s.wins) ? s.wins : [],
        };
        if (s.decision) {
          decisions[m.id] = {
            verdict: DECISION_TO_VERDICT[s.decision] || s.decision,
            reason: s.note || "",
            at: null,
          };
        }
      }
      return {
        id: m.id,
        label: m.label,
        domain: m.domain,
        depth: Math.round((m.depth || 0) * 100),
        coverage: Math.round((m.coverage || 0) * 100),
        updated: !!m.updated,
        interface: m.iface || "",
        files: Array.isArray(m.files) ? m.files : [],
        tests: testsToArray(m.tests),
        dependsOn: Array.isArray(m.dependsOn) ? m.dependsOn : [],
        leaks: Array.isArray(m.leaksTo) ? m.leaksTo : [],
        suggestion,
      };
    });
    return { repo: raw.repo || "", modules, decisions, seq: (cur.seq || 0) + 1 };
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
    cur = normalize(JSON.parse(rawText));
    return true;
  }

  function adoptServer(rawText) {
    // force the cache to server truth, bypassing the byte short-circuit — used to
    // roll back a rejected optimistic write even when server state is unchanged.
    lastServerJson = rawText;
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
    lastServerJson = txt; cur = normalize(obj); return true;
  }
  async function hostRefresh() {
    if (!currentMap) return false;
    const full = await hostCall("get_model", { map: currentMap });
    if (full && adoptModelObject(full)) { broadcast(cur); return true; }
    return false;
  }

  async function fetchModel() {
    if (HOST) {
      if (!currentMap) return lastServerJson || JSON.stringify({ repo: "", modules: [], orphans: [], openSuggestions: [] });
      const full = await hostCall("get_model", { map: currentMap });
      return JSON.stringify(full || { repo: "", modules: [], orphans: [], openSuggestions: [] });
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
    switch (a.action) {
      case "set_depth": return ["set_depth", { map, module: a.module, score: a.score }];
      case "set_coverage": return ["set_coverage", { map, module: a.module, fraction: a.fraction }];
      case "decide": return ["decide", { map, suggestion_id: a.suggestion_id, decision: a.decision, note: a.note || "" }];
      case "resolve": return ["resolve", { map, suggestion_id: a.suggestion_id }];
      case "delete": return ["delete_module", { map, module: a.module }];
      case "update": return ["update_module", { map, module: a.module, fields: a.fields || {} }];
      case "add": return ["add_module", Object.assign({ map }, a.module)];
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
      const full = await hostCall("get_model", { map }); // ...so re-pull the full model
      if (myGen === writeGen && full && adoptModelObject(full)) broadcast(cur);
    } catch (e) {
      if (myGen === writeGen) { try { const f = await hostCall("get_model", { map }); if (f && adoptModelObject(f)) broadcast(cur); } catch (_) {} }
      throw e;
    } finally {
      pendingWrites--;
    }
  }

  // POST an action; reconcile the cache from the authoritative response.
  async function act(body) {
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

  // ---- optimistic local mutation helpers -----------------------------------
  function bump() { cur.seq = (cur.seq || 0) + 1; }
  function clamp(n) { return Math.max(0, Math.min(100, Math.round(n))); }
  function find(id) { return cur.modules.find((x) => x.id === id); }

  // ---- model API (mirrors the prototype's synchronous Store) ---------------
  const Store = {
    get() { return cur; },

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
        depth: 50, coverage: 0, updated: true, interface: "",
        files: [], tests: [], dependsOn: [], leaks: [], suggestion: null,
      });
      bump();
      act({ action: "add", module: { id, label: label || id, domain: domain || "uncategorized" } }).catch(reportErr);
      return cur;
    },
    deleteModule(id) {
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
    decide(id, verdict, reason) {
      // the proposal must still exist on the server to record a decision against it
      const sid = sidFor(id);
      if (!sid) { reportErr(new Error("proposal for " + id + " no longer exists")); refetch(true); return cur; }
      cur.decisions[id] = { verdict, reason: reason || "", at: null };
      bump();
      act({ action: "decide", suggestion_id: sid, decision: VERDICT_TO_DECISION[verdict] || verdict, note: reason || "" }).catch(reportErr);
      return cur;
    },
    reopen(id) {
      // undo a decision: re-open the proposal (decision back to "")
      const sid = sidFor(id);
      if (!sid) { reportErr(new Error("proposal for " + id + " no longer exists")); refetch(true); return cur; }
      delete cur.decisions[id];
      bump();
      act({ action: "decide", suggestion_id: sid, decision: "", note: "" }).catch(reportErr);
      return cur;
    },
    dismiss(id) {
      const sid = sidFor(id);
      if (!sid) { reportErr(new Error("proposal for " + id + " no longer exists")); refetch(true); return cur; }
      const m = find(id);
      if (m) m.suggestion = null;
      delete cur.decisions[id];
      bump();
      act({ action: "resolve", suggestion_id: sid }).catch(reportErr);
      return cur;
    },
  };

  function reportErr(e) {
    // surface backend rejections (e.g. duplicate id) without crashing the UI
    if (window.Studio && typeof window.Studio.toast === "function") {
      window.Studio.toast(String(e.message || e), "var(--leak)");
    } else { console.error("arch-map action error:", e); }
  }

  // ---- broadcast / subscribe -----------------------------------------------
  const listeners = new Set();
  function broadcast(s) { listeners.forEach((fn) => { try { fn(s); } catch (e) {} }); }
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
    const hasOut = (m.dependsOn || []).length > 0 || (m.leaks || []).length > 0;
    const hasIn = s.modules.some((x) => (x.dependsOn || []).includes(m.id) || (x.leaks || []).includes(m.id));
    return !hasOut && !hasIn;
  }
  function openSuggestions(s) {
    return s.modules.filter((m) => m.suggestion && !s.decisions[m.id]);
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
    tierOf, isOrphan, openSuggestions,
    STRENGTHS: {
      strong: { label: "Strong", short: "strong" },
      worth: { label: "Worth exploring", short: "worth" },
      speculative: { label: "Speculative", short: "speculative" },
    },
  };
})();
