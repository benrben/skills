/* arch-map studio — shared namespace + graph canvas */
window.Studio = window.Studio || {};
(function (S) {
  "use strict";
  const { Store, subscribe, tierOf, isOrphan, openSuggestions, STRENGTHS } = window.Arch;

  const NW = 150, NH = 82;
  const els = {};
  let view = { x: 80, y: 40, k: 0.9 };
  let layout = null, structSig = "", nodeEl = {};

  // shared studio state
  S.model = Store.get();
  S.selectedId = null;
  S.hoverId = null;       // from graph hover
  S.railHotId = null;     // from rail hover (proposal/module)
  S.filter = "all";
  S.search = "";
  S.allEdges = false;

  /* ---------- structure signature ---------- */
  function sigOf(s) {
    return s.modules.map((m) => m.id + ":" + (m.dependsOn || []).join(",") + "|" + (m.leaks || []).join(",")).sort().join(";");
  }

  /* ---------- dagre layout ---------- */
  function computeLayout(s) {
    const g = new dagre.graphlib.Graph({ multigraph: true });
    g.setGraph({ rankdir: "TB", ranksep: 58, nodesep: 18, edgesep: 12, marginx: 36, marginy: 40 });
    g.setDefaultEdgeLabel(() => ({}));
    const placed = s.modules.filter((m) => !isOrphan(s, m));
    const placedIds = new Set(placed.map((m) => m.id));
    placed.forEach((m) => g.setNode(m.id, { width: NW, height: NH }));
    placed.forEach((m) => (m.dependsOn || []).forEach((d) => { if (placedIds.has(d)) g.setEdge(m.id, d, {}, "dep:" + m.id + "->" + d); }));
    dagre.layout(g);
    return { g, placedIds };
  }

  /* ---------- build ---------- */
  function buildGraph() {
    layout = computeLayout(S.model);
    const g = layout.g, gw = g.graph().width || 800, gh = g.graph().height || 600;
    els.viewport.style.width = gw + "px"; els.viewport.style.height = gh + "px";
    els.edges.setAttribute("width", gw); els.edges.setAttribute("height", gh);
    els.edges.setAttribute("viewBox", `0 0 ${gw} ${gh}`);

    let edgeHTML = "";
    g.edges().forEach((e) => { edgeHTML += `<path class="edge-dep" data-from="${e.v}" data-to="${e.w}" d="${poly(g.edge(e).points)}"/>`; });
    S.model.modules.forEach((m) => (m.leaks || []).forEach((to) => {
      const a = g.hasNode(m.id) && g.node(m.id), b = g.hasNode(to) && g.node(to);
      if (a && b) edgeHTML += `<path class="edge-leak" data-from="${m.id}" data-to="${to}" d="${ortho(a, b)}"/>`;
    }));
    els.edges.innerHTML = edgeHTML;

    els.nodeLayer.innerHTML = ""; nodeEl = {};
    layout.placedIds.forEach((id) => {
      const m = S.model.modules.find((x) => x.id === id), n = g.node(id);
      const el = makeNode(m);
      el.style.left = (n.x - NW / 2) + "px"; el.style.top = (n.y - NH / 2) + "px";
      el.style.width = NW + "px"; el.style.height = NH + "px";
      els.nodeLayer.appendChild(el); nodeEl[id] = el;
    });
    applyTransform(); refreshVisualState();
  }

  function poly(pts) {
    if (!pts || !pts.length) return "";
    let d = `M ${pts[0].x} ${pts[0].y}`;
    for (let i = 1; i < pts.length - 1; i++) { const mx = (pts[i].x + pts[i + 1].x) / 2, my = (pts[i].y + pts[i + 1].y) / 2; d += ` Q ${pts[i].x} ${pts[i].y} ${mx} ${my}`; }
    const last = pts[pts.length - 1]; return d + ` L ${last.x} ${last.y}`;
  }
  function ortho(a, b) {
    const sx = a.x, sy = a.y + a.height / 2, tx = b.x, ty = b.y - b.height / 2, my = sy + (ty - sy) * 0.5;
    return `M ${sx} ${sy} L ${sx} ${my} L ${tx} ${my} L ${tx} ${ty}`;
  }

  function makeNode(m) {
    const tier = tierOf(m.depth);
    const el = document.createElement("div");
    el.className = `node tier-${tier}${m.updated ? " updated" : ""}`;
    el.dataset.id = m.id;
    el.innerHTML = nodeInner(m);
    el.title = `${m.label} — ${m.domain}`;
    el.addEventListener("mouseenter", () => { S.hoverId = m.id; refreshVisualState(); });
    el.addEventListener("mouseleave", () => { S.hoverId = null; refreshVisualState(); });
    el.addEventListener("click", (e) => { e.stopPropagation(); S.selectNode(m.id); });
    return el;
  }
  function nodeInner(m) {
    const open = m.suggestion && !S.model.decisions[m.id];
    const flags = [];
    if (open) flags.push(`<span class="sug-ring ${m.suggestion.strength}" title="${STRENGTHS[m.suggestion.strength].label}">!</span>`);
    if ((m.leaks || []).length) flags.push(`<span class="leak-flag" title="${m.leaks.length} leak(s)">—</span>`);
    return `<div class="node-top"><div style="min-width:0">
        <div class="node-id">${m.id}</div><div class="node-label">${m.label}</div><div class="node-dom">${m.domain}</div>
      </div><div class="node-flags">${flags.join("")}</div></div>
      <div class="cov-bar" title="coverage ${m.coverage}%"><i style="width:${m.coverage}%"></i></div>`;
  }

  function softUpdate() {
    layout.placedIds.forEach((id) => {
      const m = S.model.modules.find((x) => x.id === id), el = nodeEl[id];
      if (!m || !el) return;
      el.className = `node tier-${tierOf(m.depth)}${m.updated ? " updated" : ""}`;
      el.innerHTML = nodeInner(m);
    });
    refreshVisualState();
  }

  /* ---------- transform / pan / zoom ---------- */
  const MIN_K = 0.16, MAX_K = 2.4;
  // level-of-detail thresholds: < FAR show pins only, FAR..NEAR medium, > NEAR full
  const LOD_FAR = 0.46, LOD_NEAR = 0.72;
  let lastLod = "";
  function applyLOD() {
    const lod = view.k < LOD_FAR ? "far" : view.k < LOD_NEAR ? "mid" : "near";
    if (lod !== lastLod) { els.stage.classList.remove("lod-far", "lod-mid", "lod-near"); els.stage.classList.add("lod-" + lod); lastLod = lod; }
  }
  function applyTransform() {
    els.viewport.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.k})`;
    els.zoomInd.textContent = Math.round(view.k * 100) + "%";
    applyLOD();
  }
  function setSmooth(on) { els.viewport.style.transition = on ? "transform .32s cubic-bezier(.4,0,.2,1)" : "none"; }

  function initPanZoom() {
    let drag = null;
    els.stage.addEventListener("mousedown", (e) => {
      if (e.target.closest(".node")) return;
      setSmooth(false);
      drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false }; els.stage.classList.add("panning");
    });
    window.addEventListener("mousemove", (e) => { if (!drag) return; drag.moved = true; view.x = drag.vx + (e.clientX - drag.x); view.y = drag.vy + (e.clientY - drag.y); applyTransform(); });
    window.addEventListener("mouseup", () => { drag = null; els.stage.classList.remove("panning"); });
    els.stage.addEventListener("wheel", (e) => {
      e.preventDefault();
      setSmooth(false);
      const r = els.stage.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
      if (e.shiftKey && !e.ctrlKey) { view.x -= e.deltaY; applyTransform(); return; }
      const k2 = Math.max(MIN_K, Math.min(MAX_K, view.k * Math.exp(-e.deltaY * 0.0014)));
      view.x = mx - (mx - view.x) * (k2 / view.k); view.y = my - (my - view.y) * (k2 / view.k); view.k = k2; applyTransform();
    }, { passive: false });
  }

  // robust fit: retries until the stage actually has a measurable size
  let fitTries = 0;
  S.fit = function (smooth) {
    if (!layout) return;
    const r = els.stage.getBoundingClientRect();
    if ((r.width < 40 || r.height < 40) && fitTries < 30) { fitTries++; requestAnimationFrame(() => S.fit(smooth)); return; }
    fitTries = 0;
    const gw = layout.g.graph().width || 1, gh = layout.g.graph().height || 1, pad = 90;
    const k = Math.min((r.width - pad) / gw, (r.height - pad) / gh, 1.3);
    if (smooth) setSmooth(true);
    view.k = Math.max(MIN_K, Math.min(MAX_K, k));
    view.x = (r.width - gw * view.k) / 2;
    view.y = (r.height - gh * view.k) / 2;
    applyTransform();
    if (smooth) setTimeout(() => setSmooth(false), 340);
  };
  S.zoomBy = function (f) {
    setSmooth(true);
    const r = els.stage.getBoundingClientRect(), mx = r.width / 2, my = r.height / 2;
    const k2 = Math.max(MIN_K, Math.min(MAX_K, view.k * f));
    view.x = mx - (mx - view.x) * (k2 / view.k); view.y = my - (my - view.y) * (k2 / view.k); view.k = k2; applyTransform();
    setTimeout(() => setSmooth(false), 340);
  };
  S.centerOn = function (id, flash) {
    const n = layout.g.node(id); if (!n) return;
    const r = els.stage.getBoundingClientRect();
    // if we're zoomed way out, bring up to a readable level when flying to a node
    const targetK = flash ? Math.max(view.k, LOD_NEAR) : view.k;
    setSmooth(true);
    view.k = Math.min(MAX_K, targetK);
    view.x = r.width / 2 - n.x * view.k; view.y = r.height / 2 - n.y * view.k; applyTransform();
    setTimeout(() => setSmooth(false), 340);
    if (flash && nodeEl[id]) { nodeEl[id].classList.remove("flash"); void nodeEl[id].offsetWidth; nodeEl[id].classList.add("flash"); }
  };

  /* ---------- neighbourhood ---------- */
  function neighbourhood(id) {
    const set = new Set([id]), m = S.model.modules.find((x) => x.id === id);
    if (m) { (m.dependsOn || []).forEach((d) => set.add(d)); (m.leaks || []).forEach((d) => set.add(d)); }
    S.model.modules.forEach((x) => { if ((x.dependsOn || []).includes(id) || (x.leaks || []).includes(id)) set.add(x.id); });
    return set;
  }

  /* ---------- filter / search ---------- */
  function matchFilter(m) {
    switch (S.filter) {
      case "suggestions": return !!(m.suggestion && !S.model.decisions[m.id]);
      case "updated": return !!m.updated;
      case "leaks": return (m.leaks || []).length > 0;
      case "low": return m.coverage < 40;
      case "orphan": return isOrphan(S.model, m);
      default: return true;
    }
  }
  function matchSearch(m) {
    if (!S.search) return true;
    const t = S.search.toLowerCase();
    return m.id.toLowerCase().includes(t) || m.label.toLowerCase().includes(t) || m.domain.toLowerCase().includes(t);
  }

  /* ---------- visual state ---------- */
  function refreshVisualState() {
    const focusId = S.hoverId || S.railHotId;
    const hot = focusId ? neighbourhood(focusId) : null;
    layout.placedIds.forEach((id) => {
      const m = S.model.modules.find((x) => x.id === id), el = nodeEl[id]; if (!el) return;
      let dim = !matchFilter(m) || !matchSearch(m);
      if (hot && !hot.has(id)) dim = true;
      el.classList.toggle("dim", dim);
      el.classList.toggle("sel", id === S.selectedId);
      el.classList.toggle("spot", id === focusId && focusId !== S.selectedId);
      el.classList.toggle("match-hit", !!S.search && matchSearch(m));
    });
    els.edges.querySelectorAll(".edge-dep").forEach((p) => {
      const f = p.dataset.from, t = p.dataset.to;
      const inHot = hot && hot.has(f) && hot.has(t) && (f === focusId || t === focusId);
      p.classList.toggle("show", S.allEdges && !hot);
      p.classList.toggle("hot", !!inHot);
      if (hot && !inHot) p.classList.remove("show");
    });
    els.edges.querySelectorAll(".edge-leak").forEach((p) => {
      const f = p.dataset.from, t = p.dataset.to, inHot = hot && (f === focusId || t === focusId);
      p.classList.toggle("hot", !!inHot); p.style.opacity = (hot && !inHot) ? ".18" : "";
    });
  }
  S.refreshVisualState = refreshVisualState;
  S.setRailHot = function (id) { S.railHotId = id; refreshVisualState(); };

  /* ---------- orphan tray ---------- */
  function renderOrphans() {
    const orphans = S.model.modules.filter((m) => isOrphan(S.model, m));
    els.orphanItems.innerHTML = orphans.length
      ? orphans.map((m) => `<button class="orphan-chip" data-nav="${m.id}"><code>${m.id}</code> ${m.label}</button>`).join("")
      : `<span class="ot-empty">everything is connected</span>`;
    els.orphanItems.querySelectorAll("[data-nav]").forEach((b) => b.onclick = () => S.selectNode(b.dataset.nav));
  }

  /* ---------- chips ---------- */
  function renderChips() {
    const m = S.model.modules;
    const counts = { all: m.length, suggestions: openSuggestions(S.model).length, updated: m.filter((x) => x.updated).length,
      leaks: m.filter((x) => (x.leaks || []).length).length, low: m.filter((x) => x.coverage < 40).length, orphan: m.filter((x) => isOrphan(S.model, x)).length };
    const defs = [["all", "All", ""], ["suggestions", "⚠ Suggestions", "var(--warn)"], ["updated", "Updated", "var(--updated)"],
      ["leaks", "Leaks", "var(--leak)"], ["low", "Low coverage", "var(--cov)"], ["orphan", "Not connected", "var(--text-faint)"]];
    els.chips.innerHTML = defs.map(([k, label, c]) =>
      `<button class="chip" data-filter="${k}" aria-pressed="${S.filter === k}">${c ? `<span class="dot" style="background:${c}"></span>` : ""}${label}<span class="ct">${counts[k]}</span></button>`).join("");
    els.chips.querySelectorAll("[data-filter]").forEach((b) => b.onclick = () => {
      S.filter = (S.filter === b.dataset.filter && b.dataset.filter !== "all") ? "all" : b.dataset.filter;
      renderChips(); refreshVisualState();
    });
  }

  /* ---------- search ---------- */
  function doSearch(term, center) {
    S.search = term.trim();
    const url = new URL(location.href);
    if (S.search) url.searchParams.set("q", S.search); else url.searchParams.delete("q");
    history.replaceState(null, "", url);
    refreshVisualState();
    if (center && S.search) { const hit = S.model.modules.find((m) => matchSearch(m) && layout.placedIds.has(m.id)); if (hit) S.centerOn(hit.id, true); }
  }

  /* ---------- rebuild / model sync ---------- */
  S.rebuildGraph = function () { structSig = sigOf(S.model); buildGraph(); renderOrphans(); renderChips(); };
  S.softUpdateGraph = function () { softUpdate(); renderOrphans(); renderChips(); };

  /* ---------- boot the canvas ---------- */
  S.bootGraph = function () {
    S.model = Store.get();   // the backend model loads async; pick up the live cache at boot
    ["stage", "viewport", "edges", "nodeLayer", "zoomInd", "orphanItems", "chips"].forEach((id) => els[id] = document.getElementById(id));
    initPanZoom();
    els.stage.addEventListener("click", (e) => { if (!e.target.closest(".node")) S.deselect && S.deselect(); });
    document.getElementById("fitBtn").onclick = () => S.fit(true);
    document.getElementById("zoomIn").onclick = () => S.zoomBy(1.25);
    document.getElementById("zoomOut").onclick = () => S.zoomBy(1 / 1.25);
    document.getElementById("allEdgesBtn").onclick = (e) => { S.allEdges = !S.allEdges; e.currentTarget.setAttribute("aria-pressed", S.allEdges); refreshVisualState(); };

    const sb = document.getElementById("searchInput");
    sb.addEventListener("input", () => doSearch(sb.value, false));
    sb.addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(sb.value, true); });
    S._searchBox = sb;

    S.rebuildGraph();
    // robust auto-fit: wait for layout to settle, then frame everything
    requestAnimationFrame(() => requestAnimationFrame(() => S.fit(false)));
    // refit on viewport resize (debounced)
    let rt;
    window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => S.fit(true), 160); });
  };
  S.sigOf = sigOf;
})(window.Studio);
