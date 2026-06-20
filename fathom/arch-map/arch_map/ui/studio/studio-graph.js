/* arch-map studio — shared namespace + graph canvas (ELK rewrite) */
window.Studio = window.Studio || {};
(function (S) {
  "use strict";
  const { Store, subscribe, tierOf, isOrphan, openSuggestions, isOpen, STRENGTHS } = window.Arch;
  const Focus = window.Arch.Focus;   // the focus seam: owns selection/hover/isolation state
  const DocLens = window.Arch.DocLens; // the doc lens seam: owns active doc + highlight/dim set

  /* ================================================================ *
   *  CONSTANTS
   * ================================================================ */
  const NW = 150, NH = 82;
  const SUPER_W = 230, SUPER_H = 132;
  const MIN_K = 0.18, MAX_K = 2.4;
  const LOD_FAR = 0.42, LOD_NEAR = 0.74;
  const ZOOM_TO_DETAIL = 0.92;
  const ZOOM_TO_OVERVIEW = 0.34;

  /* ================================================================ *
   *  SHARED STUDIO STATE
   * ================================================================ */
  S.model      = Store.get();
  // selection/hover/isolation state now lives in the focus seam (window.Arch.Focus).
  S.filter     = "all";
  S.search     = "";
  S.allEdges   = false;

  /* ================================================================ *
   *  PRIVATE STATE
   * ================================================================ */
  const els = {};
  let view     = { x: 80, y: 40, k: 0.9 };
  let layout   = null;
  let nodeEl   = {}, hullEl = {};
  let mode     = "overview";
  const collapsed = new Set();
  let lastLod  = "";
  let fitTries = 0;
  let modeSwitching = false;
  let mmScale  = 1, mmOx = 0, mmOy = 0;

  // #8 reduced-motion: gate JS-driven smooth pans + the flash so the canvas honours
  // the OS "reduce motion" pref (the CSS animations are neutralized globally in ui.css).
  const reduceMotion = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  // #13/#14 view-preservation state: which modes we've already framed once, and the
  // last view saved before an isolate / mode switch so we can restore instead of re-fit.
  const seenModes = new Set();
  let savedView = null;
  // #12 breadcrumb scope mirror (rendered into #breadcrumb).
  let scope = { mode: "overview" };
  // #14 isolate state now lives in the focus seam (window.Arch.Focus).

  // #19 minimap throttling: an offscreen scene canvas (structure-time) + a rAF-coalesced
  // viewport redraw (per-frame). mmSceneDirty forces a scene rebuild on the next draw.
  let mmSceneCanvas = null;
  let mmSceneDirty  = true;
  let mmRaf = 0;

  /* ================================================================ *
   *  INLINE SVGs (no emoji)
   * ================================================================ */
  const FLASK_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="13" height="13"><path d="M9 3h6M10 3v6l-5 8.5A2 2 0 0 0 6.8 21h10.4a2 2 0 0 0 1.7-3.5L14 9V3"/><path d="M7.5 14.5h9"/></svg>';
  const X_SVG    = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" width="8" height="8"><path d="M5 5l14 14M19 5L5 19"/></svg>';

  /* ================================================================ *
   *  DOMAIN COLOR PALETTE
   * ================================================================ */
  const DOM_HUE   = {};
  let   DOM_ORDER = [];

  function buildDomainPalette() {
    const counts = {};
    S.model.modules.forEach(m => { counts[m.domain] = (counts[m.domain] || 0) + 1; });
    DOM_ORDER = Object.keys(counts).sort((a, b) => counts[b] - counts[a] || a.localeCompare(b));
    const n    = DOM_ORDER.length;
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    DOM_ORDER.forEach((d, i) => {
      const hue    = Math.round((i * 360 / n + i * 47) % 360);
      DOM_HUE[d]   = hue;
      const wash   = dark ? `oklch(0.265 0.028 ${hue})` : `oklch(0.967 0.036 ${hue})`;
      const accent = dark ? `oklch(0.70 0.13 ${hue})`   : `oklch(0.66 0.15 ${hue})`;
      document.documentElement.style.setProperty(`--domx-${d}`,   wash);
      document.documentElement.style.setProperty(`--domx-${d}-a`, accent);
    });
  }

  function domVar(dom)    { return DOM_HUE[dom] != null ? `var(--domx-${dom})`   : `var(--dom-default, oklch(0.97 0.006 270))`; }
  function domAccent(dom) { return DOM_HUE[dom] != null ? `var(--domx-${dom}-a)` : `var(--border-strong)`; }

  /* ================================================================ *
   *  HELPERS
   * ================================================================ */
  function esc(s) { return String(s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  // tierOf adapter: real app uses 0..100 integers
  function localTierOf(depth) {
    return depth >= 67 ? "deep" : depth >= 34 ? "mid" : "shallow";
  }

  // coverage color (0..100 integer scale)
  function covColor(c) {
    return c < 45 ? "var(--cov-low, oklch(0.60 0.21 27))" : c < 75 ? "var(--cov-mid, oklch(0.74 0.16 78))" : "var(--cov-high, oklch(0.62 0.16 152))";
  }

  function openSug(m) { return (m.suggestions || []).find(s => s.status === "open"); }
  function isGrilling(m) { return (m.suggestions || []).some(s => s.status === "grilling" || s.status === "requested"); }

  function cssVar(name) { return getComputedStyle(document.body).getPropertyValue(name).trim(); }

  function dist(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }
  function norm(from, to) {
    const dx = to.x - from.x, dy = to.y - from.y, L = Math.hypot(dx, dy) || 1;
    return { x: dx / L, y: dy / L };
  }
  function midpoint(pts) {
    const i = Math.floor(pts.length / 2);
    if (pts.length % 2) return pts[i];
    const a = pts[i - 1], b = pts[i];
    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  }

  /* ================================================================ *
   *  STRUCTURE SIGNATURE
   * ================================================================ */
  function sigOf(s) {
    return s.modules
      .map(m =>
        m.id + ":" +
        (m.dependsOn || []).join(",") + "|" +
        (m.leaks || []).join(",") + "|" +
        (m.intendsToDependOn || []).join(",") + "|" +
        (m.supersedes || []).join(",") + "|" +
        m.lifecycle + "|" + m.plane
      )
      .sort()
      .join(";");
  }
  S.sigOf = sigOf;

  /* ================================================================ *
   *  ELK INSTANCE
   * ================================================================ */
  const elk = new ELK();

  /* ================================================================ *
   *  DOMAIN HELPERS
   * ================================================================ */
  function domainsOf() {
    const map = new Map();
    S.model.modules.forEach(m => {
      if (!map.has(m.domain)) map.set(m.domain, []);
      map.get(m.domain).push(m);
    });
    return map;
  }

  function domainDepth(members) {
    return Math.max(...members.map(m => m.depth));
  }

  function domainAggEdges() {
    const byDom = domainsOf();
    const idDom = {};
    S.model.modules.forEach(m => { idDom[m.id] = m.domain; });
    const agg = new Map();
    S.model.modules.forEach(m => {
      const a = m.domain;
      const touch = (list, isLeak) => (list || []).forEach(t => {
        const b = idDom[t];
        if (!b || b === a) return;
        const k = a + ">" + b;
        const e = agg.get(k) || { from: a, to: b, weight: 0, leak: false };
        e.weight += 1;
        if (isLeak) e.leak = true;
        agg.set(k, e);
      });
      touch(m.dependsOn, false);
      touch(m.leaks, true);
    });
    return [...agg.values()];
  }

  /* ================================================================ *
   *  ROUNDED PATH (from ELK bend-points)
   * ================================================================ */
  function roundedPath(pts, r) {
    if (!pts || pts.length < 2) return "";
    if (pts.length === 2) return `M ${pts[0].x} ${pts[0].y} L ${pts[1].x} ${pts[1].y}`;
    let d = `M ${pts[0].x} ${pts[0].y}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const p = pts[i], a = pts[i - 1], b = pts[i + 1];
      const v1 = norm(p, a), v2 = norm(p, b);
      const d1 = Math.min(r, dist(p, a) / 2), d2 = Math.min(r, dist(p, b) / 2);
      const c1 = { x: p.x + v1.x * d1, y: p.y + v1.y * d1 };
      const c2 = { x: p.x + v2.x * d2, y: p.y + v2.y * d2 };
      d += ` L ${c1.x} ${c1.y} Q ${p.x} ${p.y} ${c2.x} ${c2.y}`;
    }
    const last = pts[pts.length - 1];
    d += ` L ${last.x} ${last.y}`;
    return d;
  }

  /* ================================================================ *
   *  MINIMAP CANVAS HELPERS
   * ================================================================ */
  function roundRect(ctx, x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  /* #19 minimap throttle — the hull/node/super fill is expensive and only changes
   * when `layout` (structure) changes, so render it ONCE into an offscreen canvas and
   * blit it each frame. Per-frame work is just clearRect + drawImage + the viewport
   * rect, coalesced to one redraw per rAF (applyTransform/pan/zoom fire far faster). */

  // invalidate the cached scene; the next requestMinimap rebuilds it before blitting.
  function invalidateMinimapScene() { mmSceneDirty = true; }

  function drawMinimapScene() {
    const cv = els.minimap;
    if (!cv || !layout) return;
    const DPR = 2, w = cv.width / DPR, h = cv.height / DPR;
    if (!mmSceneCanvas) {
      mmSceneCanvas = document.createElement("canvas");
    }
    mmSceneCanvas.width = cv.width; mmSceneCanvas.height = cv.height;
    const ctx = mmSceneCanvas.getContext("2d");
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const pad = 8;
    // mmScale/mmOx/mmOy depend on `layout` (not `view`), so they live here — keeping
    // drawViewportRect's coordinate mapping correct across pans/zooms.
    mmScale = Math.min((w - pad * 2) / layout.W, (h - pad * 2) / layout.H);
    mmOx = pad + (w - pad * 2 - layout.W * mmScale) / 2;
    mmOy = pad + (h - pad * 2 - layout.H * mmScale) / 2;
    const X = x => mmOx + x * mmScale, Y = y => mmOy + y * mmScale;

    // domain hull outlines
    ctx.lineWidth = 1;
    layout.hulls.forEach(hu => {
      ctx.fillStyle = cssVar(`--domx-${hu.dom}`) || cssVar("--dom-default") || "#f0f0f0";
      roundRect(ctx, X(hu.x), Y(hu.y), hu.w * mmScale, hu.h * mmScale, 3); ctx.fill();
      ctx.strokeStyle = cssVar(`--domx-${hu.dom}-a`) || cssVar("--border"); ctx.stroke();
    });

    // module nodes tinted by domain accent
    const domOf = {};
    S.model.modules.forEach(m => { domOf[m.id] = m.domain; });
    Object.entries(layout.nodes).forEach(([id, n]) => {
      ctx.fillStyle = cssVar(`--domx-${domOf[id]}-a`) || cssVar("--tier-mid") || "#999";
      roundRect(ctx, X(n.x), Y(n.y), Math.max(3, n.w * mmScale), Math.max(2, n.h * mmScale), 1.5); ctx.fill();
    });

    // overview super-nodes
    Object.entries(layout.supers).forEach(([dom, s]) => {
      ctx.fillStyle = cssVar(`--domx-${dom}-a`) || cssVar("--border-strong") || "#888";
      roundRect(ctx, X(s.x), Y(s.y), s.w * mmScale, s.h * mmScale, 2.5); ctx.fill();
    });

    mmSceneDirty = false;
  }

  function drawMinimapViewport() {
    const cv = els.minimap;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    const DPR = 2, w = cv.width / DPR, h = cv.height / DPR;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, cv.width, cv.height);
    if (!layout) return;
    if (mmSceneDirty || !mmSceneCanvas) drawMinimapScene();
    if (mmSceneCanvas) ctx.drawImage(mmSceneCanvas, 0, 0);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    drawViewportRect();
  }

  // rAF-coalesced: many applyTransform() calls per gesture collapse to one redraw/frame.
  function requestMinimap() {
    if (mmRaf) return;
    mmRaf = requestAnimationFrame(() => { mmRaf = 0; drawMinimapViewport(); });
  }

  // structure changed: rebuild the scene cache and repaint.
  function drawMinimap() { invalidateMinimapScene(); drawMinimapViewport(); }

  function drawViewportRect() {
    const cv = els.minimap;
    if (!cv || !layout || !els.stage) return;
    const ctx = cv.getContext("2d");
    const r = els.stage.getBoundingClientRect();
    const vx = -view.x / view.k, vy = -view.y / view.k;
    const vw = r.width / view.k, vh = r.height / view.k;
    const X = x => mmOx + x * mmScale, Y = y => mmOy + y * mmScale;
    ctx.save();
    ctx.strokeStyle = cssVar("--accent") || "#6366f1"; ctx.lineWidth = 1.5;
    ctx.fillStyle   = cssVar("--accent-weak") || "rgba(99,102,241,0.12)";
    ctx.globalAlpha = 0.18;
    ctx.fillRect(X(vx), Y(vy), vw * mmScale, vh * mmScale);
    ctx.globalAlpha = 1;
    ctx.strokeRect(X(vx), Y(vy), vw * mmScale, vh * mmScale);
    ctx.restore();
  }

  function initMinimapDrag() {
    const cv = els.minimap;
    if (!cv) return;
    function go(e) {
      const r = cv.getBoundingClientRect();
      const mx = (e.clientX - r.left), my = (e.clientY - r.top);
      const wx = (mx - mmOx) / mmScale, wy = (my - mmOy) / mmScale;
      const sr = els.stage.getBoundingClientRect();
      setSmooth(true);
      view.x = sr.width / 2 - wx * view.k;
      view.y = sr.height / 2 - wy * view.k;
      applyTransform();
      setTimeout(() => setSmooth(false), 300);
    }
    let down = false;
    cv.addEventListener("mousedown", e => { down = true; go(e); });
    window.addEventListener("mousemove", e => { if (down) go(e); });
    window.addEventListener("mouseup", () => { down = false; });
  }

  /* ================================================================ *
   *  ELK OVERVIEW LAYOUT
   * ================================================================ */
  async function computeOverview() {
    const allDomains = domainsOf();
    const doms = [...allDomains.keys()];

    const nodes = doms.map(d => ({
      id: "super:" + d,
      width: SUPER_W,
      height: SUPER_H,
      layoutOptions: { "elk.layered.layering.layerChoiceConstraint": "" }
    }));

    const agg = domainAggEdges();
    const edges = agg.map((e, i) => ({
      id: "ag" + i,
      sources: ["super:" + e.from],
      targets: ["super:" + e.to],
      _type: e.leak ? "leak" : "dep",
      _weight: e.weight,
      _fm: "super:" + e.from,
      _to: "super:" + e.to
    }));

    const graph = {
      id: "root",
      layoutOptions: {
        "elk.algorithm": "layered",
        "elk.direction": "DOWN",
        "elk.edgeRouting": "ORTHOGONAL",
        "elk.layered.spacing.nodeNodeBetweenLayers": "78",
        "elk.spacing.nodeNode": "78",
        "elk.layered.spacing.edgeNodeBetweenLayers": "34",
        "elk.spacing.edgeNode": "30",
        "elk.layered.spacing.edgeEdgeBetweenLayers": "16",
        "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
        "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
        "elk.layered.thoroughness": "12",
        "elk.padding": "[top=48,left=48,bottom=48,right=48]",
        "elk.spacing.componentComponent": "80"
      },
      children: nodes,
      edges
    };

    const res = await elk.layout(graph);
    const out = {
      mode: "overview",
      nodes: {}, supers: {}, hulls: [], edges: [],
      W: res.width || 1000,
      H: res.height || 800
    };

    (res.children || []).forEach(p => {
      if (!p.id.startsWith("super:")) return;
      const dom = p.id.slice(6);
      out.supers[dom] = {
        x: p.x || 0, y: p.y || 0,
        w: p.width, h: p.height,
        members: allDomains.get(dom)
      };
    });

    (res.edges || []).forEach(e => {
      const sec = (e.sections || [])[0];
      if (!sec) return;
      const pts = [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint];
      out.edges.push({
        type: e._type,
        from: e._fm, to: e._to,
        fromEp: e.sources[0], toEp: e.targets[0],
        weight: e._weight, pts
      });
    });

    return out;
  }

  /* ================================================================ *
   *  ELK DETAIL LAYOUT
   * ================================================================ */
  async function computeDetail() {
    const allDomains = domainsOf();
    const liveIds = new Set(S.model.modules.map(m => m.id));
    const openDomains = [...allDomains.keys()].filter(d => !collapsed.has(d));

    const children = [];

    openDomains.forEach(dom => {
      const members = allDomains.get(dom).filter(m => liveIds.has(m.id));
      children.push({
        id: "dom:" + dom,
        layoutOptions: {
          "elk.padding": "[top=34,left=18,bottom=18,right=18]",
          "elk.spacing.nodeNode": "22"
        },
        children: members.map(m => ({ id: m.id, width: NW, height: NH }))
      });
    });

    collapsed.forEach(dom => {
      children.push({ id: "super:" + dom, width: 196, height: 96 });
    });

    const edgeDefs = [];
    function endpointFor(id) {
      if (liveIds.has(id)) return id;
      const m = S.model.modules.find(x => x.id === id);
      if (m && collapsed.has(m.domain)) return "super:" + m.domain;
      return null;
    }
    let ei = 0;
    function addEdge(type, fromMod, toId) {
      const a = endpointFor(fromMod.id), b = endpointFor(toId);
      if (!a || !b || a === b) return;
      edgeDefs.push({ id: "e" + (ei++), sources: [a], targets: [b], _type: type, _fm: fromMod.id, _to: toId });
    }

    S.model.modules.forEach(m => {
      (m.dependsOn || []).forEach(d => addEdge("dep", m, d));
      (m.intendsToDependOn || []).forEach(d => addEdge("intended", m, d));
      (m.leaks || []).forEach(d => addEdge("leak", m, d));
      (m.supersedes || []).forEach(d => addEdge("supersede", m, d));
    });

    // de-dup, but count collapsed duplicates as the edge weight (#17). For dep edges
    // we also fold in the target's fan-in so a heavily-depended-on module reads heavier.
    const seen = new Map();
    const edges = edgeDefs.filter(e => {
      const key = e.sources[0] + ">" + e.targets[0] + ":" + e._type;
      if (seen.has(key)) { seen.get(key)._weight += 1; return false; }
      e._weight = 1;
      seen.set(key, e);
      return true;
    });
    const fanIn = {};
    S.model.modules.forEach(m => (m.dependsOn || []).forEach(d => { fanIn[d] = (fanIn[d] || 0) + 1; }));
    edges.forEach(e => { if (e._type === "dep") e._weight += Math.max(0, (fanIn[e._to] || 1) - 1); });

    const graph = {
      id: "root",
      layoutOptions: {
        "elk.algorithm": "layered",
        "elk.direction": "DOWN",
        "elk.edgeRouting": "ORTHOGONAL",
        "elk.hierarchyHandling": "INCLUDE_CHILDREN",
        "elk.layered.spacing.nodeNodeBetweenLayers": "56",
        "elk.spacing.nodeNode": "30",
        "elk.spacing.edgeNode": "22",
        "elk.layered.spacing.edgeNodeBetweenLayers": "22",
        "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
        "elk.padding": "[top=40,left=40,bottom=40,right=40]",
        "elk.spacing.componentComponent": "60"
      },
      children,
      edges
    };

    const res = await elk.layout(graph);
    const out = {
      mode: "detail",
      nodes: {}, supers: {}, hulls: [], edges: [],
      W: res.width || 1000,
      H: res.height || 800
    };

    (res.children || []).forEach(parent => {
      const px = parent.x || 0, py = parent.y || 0;
      if (parent.id.startsWith("dom:")) {
        const dom = parent.id.slice(4);
        out.hulls.push({ dom, x: px, y: py, w: parent.width, h: parent.height, count: allDomains.get(dom).length });
        (parent.children || []).forEach(ch => {
          out.nodes[ch.id] = { x: px + ch.x, y: py + ch.y, w: ch.width, h: ch.height };
        });
      } else if (parent.id.startsWith("super:")) {
        const dom = parent.id.slice(6);
        out.supers[dom] = { x: px, y: py, w: parent.width, h: parent.height, members: allDomains.get(dom) };
      }
    });

    (res.edges || []).forEach(e => {
      const sec = (e.sections || [])[0];
      if (!sec) return;
      const pts = [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint];
      out.edges.push({ type: e._type, from: e._fm, to: e._to, fromEp: e.sources[0], toEp: e.targets[0], weight: e._weight || 1, pts });
    });

    return out;
  }

  /* ================================================================ *
   *  BUILD GRAPH (async)
   * ================================================================ */
  async function buildGraph() {
    // #6 loading overlay: show while ELK lays out (the await below can take a beat on
    // large maps). Removed once the cards/edges are painted at the end of this fn.
    if (els.stageLoading) {
      const lbl = els.stageLoading.querySelector(".sl-label");
      if (lbl) lbl.textContent = `Laying out ${S.model.modules.length} modules…`;
      els.stageLoading.classList.add("show");
      els.stageLoading.setAttribute("aria-hidden", "false");
    }
    layout = (mode === "overview") ? await computeOverview() : await computeDetail();
    invalidateMinimapScene();   // #19: structure changed — rebuild the cached scene
    const W = layout.W, H = layout.H;

    // size the viewport + SVG
    els.viewport.style.width  = W + "px";
    els.viewport.style.height = H + "px";
    if (els.hulls) { els.hulls.style.width = W + "px"; els.hulls.style.height = H + "px"; }
    els.edges.setAttribute("width",   W);
    els.edges.setAttribute("height",  H);
    els.edges.setAttribute("viewBox", `0 0 ${W} ${H}`);

    const domOf = {};
    S.model.modules.forEach(m => { domOf[m.id] = m.domain; });

    /* ---- hulls ---- */
    if (els.hulls) {
      els.hulls.innerHTML = "";
      hullEl = {};
      layout.hulls.forEach(h => {
        const wrap = document.createElement("div");
        wrap.className = "hull";
        wrap.dataset.dom = h.dom;
        wrap.style.left   = h.x + "px";
        wrap.style.top    = h.y + "px";
        wrap.style.width  = h.w + "px";
        wrap.style.height = h.h + "px";
        wrap.style.background = domVar(h.dom);
        wrap.innerHTML = `<button class="hull-chip" data-collapse="${h.dom}">
          <span class="swatch" style="background:${domAccent(h.dom)}"></span>
          ${esc(h.dom)} <span class="ct">· ${h.count}</span><span class="caret">▾</span></button>`;
        els.hulls.appendChild(wrap);
        hullEl[h.dom] = wrap;
      });
    }

    /* ---- edges ---- */
    const SVGNS = "http://www.w3.org/2000/svg";
    els.edges.innerHTML = "";

    const defs = document.createElementNS(SVGNS, "defs");
    defs.innerHTML = `
      <marker id="ah-dep" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M1 1 L9 5 L1 9 z" fill="var(--edge, oklch(0.70 0.01 270))"/></marker>
      <marker id="ah-leak" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M1 1 L9 5 L1 9 z" fill="var(--leak)"/></marker>
      <marker id="ah-int" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M1 1 L9 5 L1 9 z" fill="var(--intended, oklch(0.55 0.20 300))"/></marker>`;
    els.edges.appendChild(defs);

    const order = { supersede: 0, dep: 1, intended: 2, leak: 3 };
    const isOv = layout.mode === "overview";

    layout.edges.slice().sort((a, b) => (order[a.type] || 0) - (order[b.type] || 0)).forEach(e => {
      const cross = isOv || (domOf[e.from] && domOf[e.to] && domOf[e.from] !== domOf[e.to]);
      const path = document.createElementNS(SVGNS, "path");

      let cls = "edge edge-" + e.type;
      if (e.type === "dep" && cross) cls += " cross";
      if (isOv) cls += " agg";

      // dep edges are visible by default (remove opacity:0 POC default)
      path.setAttribute("class", cls);

      if (isOv && e.type === "dep") {
        const w = 1.2 + Math.min(4.2, Math.log2((e.weight || 1) + 1) * 1.25);
        path.style.strokeWidth = w.toFixed(2) + "px";
        path.style.opacity     = Math.min(0.72, 0.34 + (e.weight || 1) * 0.03).toFixed(2);
      } else if (!isOv && e.type === "dep") {
        // #17: in detail, scale dep-edge WIDTH by weight (duplicate-count + target
        // fan-in) so heavily-depended-on seams read as thicker lines. Width-only —
        // opacity stays under the .fade/.hot/.show cascade so hover/filter still work
        // (inline opacity would shadow those CSS rules).
        const wt = e.weight || 1;
        const sw = 1.0 + Math.min(1.4, Math.log2(wt + 1) * 0.55);
        path.style.strokeWidth = sw.toFixed(2) + "px";
        path.dataset.weight = wt;
      }

      path.setAttribute("d", roundedPath(e.pts, isOv ? 10 : 6));
      path.dataset.from   = e.from;
      path.dataset.to     = e.to;
      path.dataset.fromEp = e.fromEp || e.from;
      path.dataset.toEp   = e.toEp   || e.to;
      path.dataset.type   = e.type;

      if (e.type === "dep")      path.setAttribute("marker-end", "url(#ah-dep)");
      if (e.type === "leak")     path.setAttribute("marker-end", "url(#ah-leak)");
      if (e.type === "intended") path.setAttribute("marker-end", "url(#ah-int)");

      els.edges.appendChild(path);

      // leak midpoint X mark
      if (e.type === "leak") {
        const mp = midpoint(e.pts);
        const t = document.createElementNS(SVGNS, "text");
        t.setAttribute("class", "leak-x");
        t.setAttribute("x", mp.x); t.setAttribute("y", mp.y + 4);
        t.setAttribute("text-anchor", "middle");
        t.textContent = "✕";
        t.dataset.from = e.from; t.dataset.to = e.to;
        els.edges.appendChild(t);
      }
    });

    /* ---- cards + super-nodes ---- */
    els.nodeLayer.innerHTML = "";
    nodeEl = {};

    Object.entries(layout.nodes).forEach(([id, n]) => {
      const m = S.model.modules.find(x => x.id === id);
      if (!m) return;
      const el = makeNode(m);
      el.style.left   = n.x + "px";
      el.style.top    = n.y + "px";
      el.style.width  = NW + "px";
      el.style.height = NH + "px";
      els.nodeLayer.appendChild(el);
      nodeEl[id] = el;
    });

    Object.entries(layout.supers).forEach(([dom, s]) => {
      const el = makeSuper(dom, s);
      el.style.left   = s.x + "px";
      el.style.top    = s.y + "px";
      el.style.width  = s.w + "px";
      el.style.height = s.h + "px";
      els.nodeLayer.appendChild(el);
      nodeEl["super:" + dom] = el;
    });

    applyTransform();
    refreshVisualState();
    applyDocBadges();
    drawMinimap();

    // sync overview button
    const ovBtn = document.getElementById("overviewBtn");
    if (ovBtn) ovBtn.setAttribute("aria-pressed", mode === "overview" ? "true" : "false");

    // #6: layout painted — hide the loading overlay.
    if (els.stageLoading) {
      els.stageLoading.classList.remove("show");
      els.stageLoading.setAttribute("aria-hidden", "true");
    }
  }

  /* ================================================================ *
   *  NODE CARD
   * ================================================================ */
  function makeNode(m) {
    const tier = localTierOf(m.depth);
    const el = document.createElement("div");
    el.className = `node tier-${tier}` +
      (m.updated            ? " updated"  : "") +
      (m.plane === "intended" ? " planned" : "") +
      (m.lifecycle === "building" ? " building" : "") +
      (isGrilling(m)        ? " grilling" : "");
    el.dataset.id = m.id;
    el.dataset.sig = nodeSig(m);   // #4: seed the diff signature so the first poll diffs cleanly
    el.innerHTML  = nodeInner(m);
    el.title = `${m.label} — ${m.domain}`;
    // #3 focusable + keyboard-activable card
    el.tabIndex = 0;
    el.setAttribute("role", "button");
    el.setAttribute("aria-label", `${m.id} — ${m.label}, ${m.domain}`);
    el.addEventListener("mouseenter", () => Focus.hover(m.id, "graph"));
    el.addEventListener("mouseleave", () => Focus.hover(null, "graph"));
    el.addEventListener("click", e => { e.stopPropagation(); Focus.select(m.id); });
    el.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
        e.preventDefault(); Focus.select(m.id);
      }
    });
    return el;
  }

  function nodeInner(m) {
    const sug  = m.suggestion || openSug(m);
    const flags = [];

    if (sug) {
      const str = (sug.strength || "speculative").toLowerCase().replace(/\s+/g, "-");
      const cls = str === "strong" ? "strong" : str === "worth-exploring" || str === "worth" ? "worth" : "speculative";
      flags.push(`<span class="sug-ring ${cls}" title="suggestion">!</span>`);
    }
    if (isGrilling(m)) {
      flags.push(`<span class="grill-flag" title="in grilling">${FLASK_SVG}</span>`);
    }
    if ((m.leaks || []).length) {
      flags.push(`<span class="flag-leak" title="${m.leaks.length} leak(s)">${X_SVG}${m.leaks.length}</span>`);
    }
    if (m.metrics && m.metrics.inCycle) {
      flags.push(`<span class="flag-cycle" title="part of a dependency cycle — circular import">↺</span>`);
    }

    const cov  = m.coverage; // 0..100
    const h = m.metrics ? m.metrics.health : null;
    const tint = m.plane === "intended" ? `<span class="card-fill-tint"></span>` : "";
    const cap  = m.plane === "intended" ? `<span class="planned-cap">PLANNED</span>` : "";

    return `${tint}
      <div class="node-top">
        <div style="min-width:0">
          <div class="node-id">${esc(m.id)}</div>
          <div class="node-label">${esc(m.label)}</div>
        </div>
        <div class="node-flags">${flags.join("")}</div>
      </div>
      <div class="node-foot">
        <div class="cov-bar" title="coverage ${cov}%"><i style="width:${cov}%;background:${covColor(cov)}"></i></div>
        <span class="cov-pct">${(m.plane === "intended" && cov === 0) ? "—" : cov + "%"}</span>
        ${(h !== null && h < 40) ? `<span class="health-dot health-bad" title="health score ${h}/100 — at risk"></span>` : ""}
      </div>${cap}`;
  }

  /* ================================================================ *
   *  SOFT UPDATE (in-place, no layout recompute)
   * ================================================================ */
  // #4: a compact signature of every field nodeInner()/className depend on. softUpdate
  // skips repainting a card whose signature is unchanged — turning a ~16-card full
  // re-render into a targeted one, and (item 10) letting the rail detect what changed.
  function nodeSig(m) {
    const sug = m.suggestion || openSug(m);
    return [
      localTierOf(m.depth), m.updated, m.plane, m.lifecycle, isGrilling(m),
      (m.leaks || []).length, m.coverage, m.metrics && m.metrics.health,
      m.metrics && m.metrics.inCycle, !!sug, (sug || {}).strength
    ].join("|");
  }

  function softUpdate() {
    Object.keys(nodeEl).forEach(id => {
      if (id.startsWith("super:")) return;
      const m  = S.model.modules.find(x => x.id === id);
      const el = nodeEl[id];
      if (!m || !el) return;
      const sig = nodeSig(m);
      if (el.dataset.sig === sig) return;   // #4: unchanged — skip the repaint
      el.className = `node tier-${localTierOf(m.depth)}` +
        (m.updated              ? " updated"  : "") +
        (m.plane === "intended" ? " planned"  : "") +
        (m.lifecycle === "building" ? " building" : "") +
        (isGrilling(m)          ? " grilling" : "");
      el.innerHTML = nodeInner(m);
      el.dataset.sig = sig;
    });
    refreshVisualState();
  }

  // #10/#15: flash a set of node cards (reused by agent-narration + nav). Respects
  // reduced-motion (the nodeflash animation is also neutralized globally in ui.css).
  S.flashNodes = function (ids) {
    if (reduceMotion || !ids) return;
    ids.forEach(id => {
      const el = nodeEl[id];
      if (!el) return;
      el.classList.remove("flash");
      void el.offsetWidth;
      el.classList.add("flash");
    });
  };

  /* ================================================================ *
   *  DOMAIN SUPER-NODE (overview)
   * ================================================================ */
  function makeSuper(dom, s) {
    const members  = s.members || [];
    const avgCov   = members.length ? members.reduce((a, m) => a + m.coverage, 0) / members.length : 0;
    const leakCount = members.reduce((a, m) => a + (m.leaks || []).length, 0);
    const sugCount  = members.filter(m => !!(m.suggestion || openSug(m))).length;
    const updCount  = members.filter(m => m.updated).length;
    const dTier     = localTierOf(domainDepth(members));

    // ring — coverage as 0..1 fraction of avgCov (which is 0..100)
    const C    = 15, circ = 2 * Math.PI * C;
    const frac = avgCov / 100;
    const ringSvg = `<svg class="sn-ring" viewBox="0 0 34 34">
        <circle cx="17" cy="17" r="${C}" fill="none" stroke="var(--cov-track, oklch(0.92 0.008 270))" stroke-width="4"/>
        <circle cx="17" cy="17" r="${C}" fill="none" stroke="${covColor(avgCov)}" stroke-width="4"
          stroke-linecap="round" stroke-dasharray="${circ}" stroke-dashoffset="${circ * (1 - frac)}"
          transform="rotate(-90 17 17)"/>
        <text x="17" y="20.5" text-anchor="middle" class="sn-ring-pct">${Math.round(avgCov)}</text></svg>`;

    const el = document.createElement("div");
    el.className  = `supernode tier-${dTier}`;
    el.dataset.dom = dom;
    el.style.background = domVar(dom);

    const flags = [];
    if (sugCount)  flags.push(`<span class="sn-flag sug" title="${sugCount} open suggestion(s)">! ${sugCount}</span>`);
    if (leakCount) flags.push(`<span class="sn-flag leak" title="${leakCount} leak(s)">${X_SVG}${leakCount}</span>`);

    el.innerHTML = `
      <div class="sn-top">
        <span class="sn-name"><span class="sn-swatch" style="background:${domAccent(dom)}"></span>${esc(dom)}</span>
        <span class="sn-badge">${members.length}</span>
      </div>
      <div class="sn-sub">${updCount}/${members.length} updated</div>
      <div class="sn-foot">
        ${ringSvg}
        <span class="sn-cov">${Math.round(avgCov)}%<br><i>coverage</i></span>
        <span class="sn-flags">${flags.join("")}</span>
      </div>`;

    el.title = `${dom} · ${members.length} modules — click to expand`;
    // #3 focusable + keyboard-activable supernode
    el.tabIndex = 0;
    el.setAttribute("role", "button");
    el.setAttribute("aria-label", `${dom} domain — ${members.length} modules, open`);
    el.addEventListener("mouseenter", () => Focus.hover("super:" + dom, "graph"));
    el.addEventListener("mouseleave", () => Focus.hover(null, "graph"));
    el.addEventListener("click", e => { e.stopPropagation(); enterDomain(dom); });
    el.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") { e.preventDefault(); enterDomain(dom); }
    });
    return el;
  }

  /* ================================================================ *
   *  TRANSFORM / PAN / ZOOM / LOD
   * ================================================================ */
  function applyLOD() {
    const lod = view.k < LOD_FAR ? "far" : view.k < LOD_NEAR ? "mid" : "near";
    if (lod !== lastLod) {
      els.stage.classList.remove("lod-far", "lod-mid", "lod-near");
      els.stage.classList.add("lod-" + lod);
      lastLod = lod;
      scope.lod = lod;
      renderBreadcrumb();   // #11/#12: the breadcrumb (revives the dead #lodTag) reflects zoom
    }
  }

  /* ================================================================ *
   *  #11/#12 BREADCRUMB — mode + scope readout, the "way back" home
   * ================================================================ */
  function renderBreadcrumb() {
    const el = els.breadcrumb;
    if (!el) return;
    const selId = Focus.current().selectedId;
    const sel = selId && S.model.modules.find(x => x.id === selId);
    let html = "";
    if (mode === "overview") {
      const n = domainsOf().size;
      html = `<span class="bc-cur">Overview · ${n} domain${n === 1 ? "" : "s"}</span>`;
    } else {
      // detail: "Overview › {scope}" with Overview clickable as the way home
      html = `<button class="bc-seg" data-bc="overview" title="Back to overview">Overview</button>`;
      if (scope.domain) {
        html += `<span class="bc-sep">›</span><button class="bc-seg" data-bc="domain" title="Refit ${esc(scope.domain)}">${esc(scope.domain)}${scope.count != null ? "·" + scope.count : ""}</button>`;
      } else {
        const n = Object.keys((layout && layout.nodes) || {}).length;
        html += `<span class="bc-sep">›</span><span class="bc-cur">detail · ${n} module${n === 1 ? "" : "s"}</span>`;
      }
      if (sel) html += `<span class="bc-sep">›</span><span class="bc-cur">${esc(sel.id)}</span>`;
    }
    el.innerHTML = html;
    const home = el.querySelector('[data-bc="overview"]');
    if (home) home.onclick = () => enterOverview();
    const dseg = el.querySelector('[data-bc="domain"]');
    if (dseg && scope.domain) dseg.onclick = () => enterDetail(scope.domain, { keepView: false });
  }

  // public so the rail can refresh the breadcrumb on select/deselect (item 12).
  S.setBreadcrumb = function (s) {
    if (s) {
      if (s.mode) scope.mode = s.mode;
      if ("domain" in s) scope.domain = s.domain;
      if ("count" in s) scope.count = s.count;
    }
    renderBreadcrumb();
  };

  function applyTransform() {
    els.viewport.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.k})`;
    if (els.zoomInd) els.zoomInd.textContent = Math.round(view.k * 100) + "%";
    applyLOD();
    requestMinimap();  // #19: rAF-coalesced viewport redraw (scene cache blitted, no ghost trails)
  }

  function setSmooth(on) {
    // #8: never enable the smooth-pan transition when the user prefers reduced motion.
    els.viewport.style.transition = (on && !reduceMotion) ? "transform .32s cubic-bezier(.4,0,.2,1)" : "none";
  }

  function maybeSwitchMode() {
    if (modeSwitching) return;
    if (mode === "overview" && view.k > ZOOM_TO_DETAIL) enterDetail();
    else if (mode === "detail" && view.k < ZOOM_TO_OVERVIEW) enterOverview();
  }

  function initPanZoom() {
    let drag = null;
    els.stage.addEventListener("mousedown", e => {
      if (e.target.closest(".node, .supernode, .hull-chip, .minimap")) return;
      setSmooth(false);
      drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
      els.stage.classList.add("panning");
    });
    window.addEventListener("mousemove", e => {
      if (!drag) return;
      view.x = drag.vx + (e.clientX - drag.x);
      view.y = drag.vy + (e.clientY - drag.y);
      applyTransform();
    });
    window.addEventListener("mouseup", () => { drag = null; els.stage.classList.remove("panning"); });
    els.stage.addEventListener("wheel", e => {
      e.preventDefault(); setSmooth(false);
      const r = els.stage.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
      if (e.shiftKey && !e.ctrlKey) { view.x -= e.deltaY; applyTransform(); return; }
      const k2 = Math.max(MIN_K, Math.min(MAX_K, view.k * Math.exp(-e.deltaY * 0.0014)));
      view.x = mx - (mx - view.x) * (k2 / view.k);
      view.y = my - (my - view.y) * (k2 / view.k);
      view.k = k2;
      applyTransform();
      maybeSwitchMode();
    }, { passive: false });
  }

  S.fit = function (smooth) {
    if (!layout) return;
    const r = els.stage.getBoundingClientRect();
    if ((r.width < 40 || r.height < 40) && fitTries < 30) {
      fitTries++;
      requestAnimationFrame(() => S.fit(smooth));
      return;
    }
    fitTries = 0;
    const W = layout.W, H = layout.H, pad = 96;
    const capK = mode === "overview" ? 0.88 : 0.85;
    const k = Math.min((r.width - pad) / W, (r.height - pad) / H, capK);
    if (smooth) setSmooth(true);
    view.k = Math.max(MIN_K, Math.min(MAX_K, k));
    view.x = (r.width  - W * view.k) / 2;
    view.y = (r.height - H * view.k) / 2;
    applyTransform();
    if (smooth) setTimeout(() => setSmooth(false), 340);
  };

  S.zoomBy = function (f) {
    setSmooth(true);
    const r = els.stage.getBoundingClientRect(), mx = r.width / 2, my = r.height / 2;
    const k2 = Math.max(MIN_K, Math.min(MAX_K, view.k * f));
    view.x = mx - (mx - view.x) * (k2 / view.k);
    view.y = my - (my - view.y) * (k2 / view.k);
    view.k = k2;
    applyTransform();
    setTimeout(() => setSmooth(false), 340);
    maybeSwitchMode();
  };

  S.centerOn = function (id, flash) {
    const n = layout && layout.nodes[id];
    if (!n) return;
    const r = els.stage.getBoundingClientRect();
    const targetK = flash ? Math.max(view.k, LOD_NEAR) : view.k;
    setSmooth(true);
    view.k = Math.min(MAX_K, targetK);
    view.x = r.width  / 2 - (n.x + n.w / 2) * view.k;
    view.y = r.height / 2 - (n.y + n.h / 2) * view.k;
    applyTransform();
    setTimeout(() => setSmooth(false), 340);
    if (flash && !reduceMotion && nodeEl[id]) {   // #8: skip the flash under reduced-motion
      nodeEl[id].classList.remove("flash");
      void nodeEl[id].offsetWidth;
      nodeEl[id].classList.add("flash");
    }
  };

  /* ================================================================ *
   *  NEIGHBOURHOOD
   * ================================================================ */
  function neighbourhood(id) {
    const set = new Set([id]);
    const m = S.model.modules.find(x => x.id === id);
    if (m) {
      (m.dependsOn          || []).forEach(d => set.add(d));
      (m.leaks              || []).forEach(d => set.add(d));
      (m.intendsToDependOn  || []).forEach(d => set.add(d));
      (m.supersedes         || []).forEach(d => set.add(d));
    }
    S.model.modules.forEach(x => {
      if (
        (x.dependsOn         || []).includes(id) ||
        (x.leaks             || []).includes(id) ||
        (x.intendsToDependOn || []).includes(id) ||
        (x.supersedes        || []).includes(id)
      ) set.add(x.id);
    });
    return set;
  }

  function domainNeighbourhood(dom) {
    const set = new Set(["super:" + dom]);
    domainAggEdges().forEach(e => {
      if (e.from === dom) set.add("super:" + e.to);
      if (e.to   === dom) set.add("super:" + e.from);
    });
    return set;
  }

  /* ================================================================ *
   *  #14 ISOLATE — show only one module's neighbourhood, fade the rest
   * ================================================================ */
  // strip the .isolating state + markers without restoring the view (used when a
  // mode switch or rebuild supersedes the isolation).
  function clearIsolateState() {
    Focus.clearIsolate();
    if (els.stage) els.stage.classList.remove("isolating");
    Object.values(nodeEl).forEach(el => el.classList.remove("iso-in"));
    els.edges.querySelectorAll(".iso-in").forEach(p => p.classList.remove("iso-in"));
    syncIsolateBtn();
  }

  S.isolate = function (id) {
    if (!id || !layout || !nodeEl[id]) return;
    const hood = neighbourhood(id);          // the module + everything it touches
    savedView = { ...view };                 // so clearIsolate can restore the framing
    Focus.isolate(id);
    // mark the kept cards + the edges fully inside the hood
    Object.entries(nodeEl).forEach(([k, el]) => el.classList.toggle("iso-in", hood.has(k)));
    els.edges.querySelectorAll(".edge, .leak-x").forEach(p => {
      p.classList.toggle("iso-in", hood.has(p.dataset.from) && hood.has(p.dataset.to));
    });
    els.stage.classList.add("isolating");    // CSS hides everything without .iso-in
    // frame the neighbourhood
    const rects = [...hood].map(k => layout.nodes[k]).filter(Boolean);
    if (rects.length) framePadded(boundsOf(rects), 1.1, true);
    syncIsolateBtn();
    renderBreadcrumb();
  };

  S.clearIsolate = function () {
    if (!Focus.current().isolatedId) return;
    clearIsolateState();
    if (savedView) {                          // #14: restore the pre-isolate framing
      setSmooth(true);
      view.x = savedView.x; view.y = savedView.y; view.k = clampK(savedView.k);
      applyTransform();
      setTimeout(() => setSmooth(false), 340);
      savedView = null;
    }
    renderBreadcrumb();
  };

  function syncIsolateBtn() {
    const btn = document.getElementById("isolateBtn");
    if (!btn) return;
    const f = Focus.current();
    const on = !!f.isolatedId;
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.disabled = !f.selectedId && !on;     // enabled when something is selected (or active)
  }
  S.syncIsolateBtn = syncIsolateBtn;

  /* ================================================================ *
   *  FILTER / SEARCH
   * ================================================================ */
  function matchFilter(m) {
    switch (S.filter) {
      case "suggestions": return !!m.suggestion;
      case "updated":     return !!m.updated;
      case "leaks":       return (m.leaks || []).length > 0;
      case "low":         return m.coverage < 40;
      case "orphan":      return isOrphan(S.model, m);
      case "planned":     return m.plane === "intended";
      case "grilling":    return (m.suggestions || []).some(s => s.status === "grilling" || s.status === "requested");
      default:            return true;
    }
  }

  function matchSearch(m) {
    if (!S.search) return true;
    const t = S.search.toLowerCase();
    return (
      m.id.toLowerCase().includes(t) ||
      m.label.toLowerCase().includes(t) ||
      m.domain.toLowerCase().includes(t)
    );
  }

  function domainMatches(dom, members) {
    if (S.filter === "all") return true;
    return members.some(matchFilter);
  }

  // #18: which toolbar chips a module belongs to — the rail's crossRefs() reuses this
  // so the same identity (module id) lights up the same surfaces everywhere.
  S.chipConcerns = function (m) {
    if (!m) return [];
    const out = [];
    if (m.suggestion) out.push("suggestions");
    if (m.updated) out.push("updated");
    if ((m.leaks || []).length) out.push("leaks");
    if (m.coverage < 40) out.push("low");
    if (isOrphan(S.model, m)) out.push("orphan");
    if (m.plane === "intended") out.push("planned");
    if ((m.suggestions || []).some(s => s.status === "grilling" || s.status === "requested")) out.push("grilling");
    return out;
  };
  // #18: let the rail drive the toolbar chip filter (so a cross-link chip can switch it).
  S.setFilter = function (k) {
    S.filter = (S.filter === k && k !== "all") ? "all" : k;
    renderChips();
    refreshVisualState();
  };

  /* ================================================================ *
   *  VISUAL STATE REFRESH
   * ================================================================ */
  function refreshVisualState() {
    if (!layout) return;
    // #1 sticky selection: a selected node keeps its neighbourhood spotlighted even
    // when the pointer leaves it (hover/railHot still win while active).
    const f       = Focus.current();
    const focusId = f.focusId;
    const isOv    = mode === "overview";
    const hot     = focusId
      ? (isOv && focusId.startsWith("super:") ? domainNeighbourhood(focusId.slice(6)) : neighbourhood(focusId))
      : null;

    // the doc lens: when a doc is active/hovered, modules in its resolved scope are
    // lens-hit and everything else gets dimmed — composes with focus/filter dimming.
    const lens    = DocLens ? DocLens.current() : null;
    const lensOn  = !!(lens && lens.focusDocId);
    const lensSet = lensOn ? new Set(lens.highlightIds) : null;
    if (els.stage) els.stage.classList.toggle("lens-on", lensOn);

    // cards + super-nodes
    Object.entries(nodeEl).forEach(([id, el]) => {
      if (id.startsWith("super:")) {
        const dom     = id.slice(6);
        const members = S.model.modules.filter(m => m.domain === dom);
        let dim = isOv ? !domainMatches(dom, members) : false;
        if (hot && !hot.has(id)) dim = true;
        const domHit = lensSet ? members.some(m => lensSet.has(m.id)) : false;
        if (lensSet && !domHit) dim = true;
        el.classList.toggle("lens-hit", domHit);
        el.classList.toggle("dim",  dim);
        el.classList.toggle("spot", id === focusId);
        return;
      }
      const m = S.model.modules.find(x => x.id === id);
      if (!m) return;
      let dim = !matchFilter(m) || !matchSearch(m);
      if (hot && !hot.has(id)) dim = true;
      if (lensSet && !lensSet.has(id)) dim = true;
      el.classList.toggle("dim",      dim);
      el.classList.toggle("sel",      id === f.selectedId);
      el.classList.toggle("spot",     id === focusId && focusId !== f.selectedId);
      el.classList.toggle("lens-hit", !!(lensSet && lensSet.has(id)));
      el.classList.toggle("match-hit", !!S.search && matchSearch(m));
    });

    // hulls
    Object.entries(hullEl).forEach(([dom, el]) => {
      const inHot = hot && [...hot].some(id => {
        const m = S.model.modules.find(x => x.id === id);
        return m && m.domain === dom;
      });
      el.classList.toggle("dim", !!(hot && !inHot));
      el.classList.toggle("hot", !!(hot && inHot));
    });

    // #5: with a filter or search active, an edge whose endpoint module is filtered/
    // searched out should fade (its cards are dimmed; the connector shouldn't shout).
    const filtering = S.filter !== "all" || !!S.search;
    const visibleId = id => {
      if (!id || id.startsWith("super:")) return true;   // supers handled by domain dim
      const m = S.model.modules.find(x => x.id === id);
      return m ? (matchFilter(m) && matchSearch(m)) : true;
    };
    const edgeFilteredOut = p =>
      filtering && (!visibleId(p.dataset.from) || !visibleId(p.dataset.to));

    // edges — in overview/detail with hot: show hot=full, fade rest
    els.edges.querySelectorAll(".edge").forEach(p => {
      if (!hot) {
        // no focus: dep/intended edges follow allEdges toggle
        if (p.classList.contains("edge-dep") || p.classList.contains("edge-intended")) {
          p.classList.toggle("show", S.allEdges);
        }
        p.classList.remove("hot");
        p.classList.toggle("fade", edgeFilteredOut(p));   // #5
        return;
      }
      const inHot = hot.has(p.dataset.from) && hot.has(p.dataset.to) &&
                    (p.dataset.from === focusId || p.dataset.to === focusId);
      p.classList.toggle("hot",  inHot);
      p.classList.toggle("fade", !inHot || edgeFilteredOut(p));
      if (p.classList.contains("edge-dep") || p.classList.contains("edge-intended")) {
        p.classList.toggle("show", inHot);
      }
    });

    els.edges.querySelectorAll(".leak-x").forEach(t => {
      const out = filtering && (!visibleId(t.dataset.from) || !visibleId(t.dataset.to));
      if (!hot) { t.classList.toggle("fade", out); return; }
      const inHot = hot.has(t.dataset.from) && hot.has(t.dataset.to) &&
                    (t.dataset.from === focusId || t.dataset.to === focusId);
      t.classList.toggle("fade", !inHot || out);
    });

    // #14: keep the isolate button's enabled/pressed state in sync with selection.
    syncIsolateBtn();
  }
  S.refreshVisualState = refreshVisualState;

  // ---- doc badges: a small "covered by N docs" chip on each module card -----
  // Driven off the DocLens membership index (O(1) per node), refreshed on every
  // lens change + rebuild so it never goes stale. Standing information scent.
  function applyDocBadges() {
    if (!DocLens) return;
    Object.keys(nodeEl).forEach(id => {
      if (id.startsWith("super:")) return;
      const el = nodeEl[id];
      if (!el) return;
      const n = DocLens.docsForModule(id).length;
      let badge = el.querySelector(".doc-badge");
      if (n > 0) {
        if (!badge) {
          badge = document.createElement("span");
          badge.className = "doc-badge";
          badge.title = "covered by documents";
          el.appendChild(badge);
        }
        badge.textContent = "❏ " + n;
      } else if (badge) {
        badge.remove();
      }
    });
  }
  S.applyDocBadges = applyDocBadges;

  // ---- zoom-to-scope: frame the lit modules (the "show models by doc" jump) --
  // Individual module nodes only exist in DETAIL layout, so in overview we switch to
  // detail first, then frame. The frame math mirrors S.fit but over the scope's bbox.
  function frameScope(ids) {
    if (!layout) return;
    const ns = ids.map(id => layout.nodes[id]).filter(Boolean);
    if (!ns.length) { S.fit(true); return; }   // still nothing laid out -> fit all
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    ns.forEach(n => { minX = Math.min(minX, n.x); minY = Math.min(minY, n.y); maxX = Math.max(maxX, n.x + n.w); maxY = Math.max(maxY, n.y + n.h); });
    const bw = Math.max(40, maxX - minX), bh = Math.max(40, maxY - minY), pad = 140;
    const r = els.stage.getBoundingClientRect();
    const k = Math.max(MIN_K, Math.min(MAX_K, LOD_NEAR, (r.width - pad) / bw, (r.height - pad) / bh));
    setSmooth(true);
    view.k = k;
    view.x = r.width / 2 - (minX + bw / 2) * k;
    view.y = r.height / 2 - (minY + bh / 2) * k;
    applyTransform();
    setTimeout(() => setSmooth(false), 340);
  }
  S.zoomToScope = function (ids) {
    if (!ids || !ids.length) return;
    if (mode === "overview") {
      // switch to detail so the modules are laid out, then frame on the next frame
      Promise.resolve(enterDetail(undefined, { keepView: true }))
        .then(() => requestAnimationFrame(() => frameScope(ids)));
    } else {
      frameScope(ids);
    }
  };

  /* ================================================================ *
   *  ORPHAN TRAY
   * ================================================================ */
  function renderOrphans() {
    if (!els.orphanItems) return;
    const orphans = S.model.modules.filter(m => isOrphan(S.model, m));
    els.orphanItems.innerHTML = orphans.length
      ? orphans.map(m => `<button class="orphan-chip" data-nav="${m.id}"><code>${m.id}</code> ${m.label}</button>`).join("")
      : `<span class="ot-empty">everything is connected</span>`;
    els.orphanItems.querySelectorAll("[data-nav]").forEach(b => b.onclick = () => Focus.select(b.dataset.nav));
  }

  /* ================================================================ *
   *  CHIPS
   * ================================================================ */
  function renderChips() {
    if (!els.chips) return;
    const m = S.model.modules;
    const counts = {
      all:         m.length,
      suggestions: openSuggestions(S.model).length,
      updated:     m.filter(x => x.updated).length,
      leaks:       m.filter(x => (x.leaks || []).length).length,
      low:         m.filter(x => x.coverage < 40).length,
      orphan:      m.filter(x => isOrphan(S.model, x)).length,
      planned:     m.filter(x => x.plane === "intended").length,
      grilling:    m.filter(x => (x.suggestions || []).some(s => s.status === "grilling" || s.status === "requested")).length
    };
    const defs = [
      ["all",         "All",           ""],
      ["suggestions", "Suggestions",   "var(--warn)"],
      ["updated",     "Updated",       "var(--updated)"],
      ["leaks",       "Leaks",         "var(--leak)"],
      ["low",         "Low coverage",  "var(--cov-high, oklch(0.62 0.16 152))"],
      ["orphan",      "Not connected", "var(--text-faint)"],
      ["planned",     "Planned",       "var(--intended, oklch(0.62 0.14 285))"],
      ["grilling",    "Grilling",      "var(--accent)"]
    ];
    els.chips.innerHTML = defs.map(([k, label, c]) =>
      `<button class="chip" data-filter="${k}" aria-pressed="${S.filter === k}">` +
      (c ? `<span class="dot" style="background:${c}"></span>` : "") +
      `${label}<span class="ct">${counts[k]}</span></button>`
    ).join("");
    els.chips.querySelectorAll("[data-filter]").forEach(b => b.onclick = () => {
      S.filter = (S.filter === b.dataset.filter && b.dataset.filter !== "all") ? "all" : b.dataset.filter;
      renderChips(); refreshVisualState();
    });
  }

  /* ================================================================ *
   *  SEARCH
   * ================================================================ */
  function doSearch(term, center) {
    S.search = term.trim();
    const url = new URL(location.href);
    if (S.search) url.searchParams.set("q", S.search); else url.searchParams.delete("q");
    history.replaceState(null, "", url);
    refreshVisualState();
    if (center && S.search) {
      const hit = S.model.modules.find(m => matchSearch(m) && layout && layout.nodes[m.id]);
      if (hit) S.centerOn(hit.id, true);
    }
  }

  /* ================================================================ *
   *  MODE STATE MACHINE
   * ================================================================ */
  function boundsOf(rects) {
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    rects.forEach(r => {
      x0 = Math.min(x0, r.x); y0 = Math.min(y0, r.y);
      x1 = Math.max(x1, r.x + r.w); y1 = Math.max(y1, r.y + r.h);
    });
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }

  function framePadded(b, maxK, smooth) {
    const r = els.stage.getBoundingClientRect(), pad = 120;
    const k = Math.max(MIN_K, Math.min(MAX_K, Math.min((r.width - pad) / b.w, (r.height - pad) / b.h, maxK || 1.2)));
    if (smooth) setSmooth(true);
    view.k = k;
    view.x = (r.width  - b.w * k) / 2 - b.x * k;
    view.y = (r.height - b.h * k) / 2 - b.y * k;
    applyTransform();
    if (smooth) setTimeout(() => setSmooth(false), 340);
  }

  async function enterOverview(focusDom) {
    if (mode === "overview" && layout && !focusDom) return;
    modeSwitching = true;
    if (Focus.current().isolatedId) clearIsolateState();   // #14: isolate is mode-scoped
    const wasSeen = seenModes.has("overview");
    const prevView = { ...view };
    mode = "overview";
    collapsed.clear();
    Focus.deselect();
    scope = { mode: "overview", lod: scope.lod };
    await buildGraph();
    if (focusDom && layout.supers[focusDom]) {
      framePadded(boundsOf([layout.supers[focusDom]]), 0.9, true);
    } else if (wasSeen) {
      // #13: returning to a mode we've framed before — keep the user's pan/zoom.
      view.x = prevView.x; view.y = prevView.y; view.k = clampK(prevView.k);
      setSmooth(true); applyTransform(); setTimeout(() => setSmooth(false), 340);
    } else {
      S.fit(true);
    }
    seenModes.add("overview");
    const ovBtn = document.getElementById("overviewBtn");
    if (ovBtn) ovBtn.setAttribute("aria-pressed", "true");
    renderBreadcrumb();
    setTimeout(() => { modeSwitching = false; }, 360);
  }

  async function enterDetail(focusDom, opts) {
    opts = opts || {};
    if (mode === "detail" && layout && !focusDom) return;
    modeSwitching = true;
    if (Focus.current().isolatedId) clearIsolateState();   // #14: isolate is mode-scoped
    const wasSeen = seenModes.has("detail");
    const prevView = { ...view };
    mode = "detail";
    collapsed.clear();
    if (focusDom) {
      const dm = domainsOf().get(focusDom);
      scope = { mode: "detail", domain: focusDom, count: dm ? dm.length : null, lod: scope.lod };
    } else {
      scope = { mode: "detail", lod: scope.lod };
    }
    await buildGraph();
    if (focusDom) {
      const h = layout.hulls.find(x => x.dom === focusDom);
      if (h) framePadded({ x: h.x, y: h.y, w: h.w, h: h.h }, 0.86, true);
      else S.fit(true);
    } else if (wasSeen && opts.keepView !== false) {
      // #13: button-driven Overview→Detail toggle keeps the previous detail view.
      view.x = prevView.x; view.y = prevView.y; view.k = clampK(prevView.k);
      setSmooth(true); applyTransform(); setTimeout(() => setSmooth(false), 340);
    } else {
      S.fit(true);
    }
    seenModes.add("detail");
    const ovBtn = document.getElementById("overviewBtn");
    if (ovBtn) ovBtn.setAttribute("aria-pressed", "false");
    renderBreadcrumb();
    setTimeout(() => { modeSwitching = false; }, 360);
  }

  function clampK(k) { return Math.max(MIN_K, Math.min(MAX_K, k)); }

  async function enterDomain(dom) { await enterDetail(dom); }

  /* ================================================================ *
   *  PUBLIC REBUILD / SOFT UPDATE
   * ================================================================ */
  S.rebuildGraph = async function () {
    if (Focus.current().isolatedId) clearIsolateState();   // #14: isolation doesn't survive a structural rebuild
    buildDomainPalette();
    await buildGraph();
    renderOrphans();
    renderChips();
  };

  // #9 reveal — the single "find→focus→act" primitive. Every rail handler routes
  // navigation through this so overview→detail→center is implemented once. Optionally
  // closes the issues panel in the same motion (the canonical issues-row locate).
  S.reveal = async function (id, opts) {
    opts = opts || {};
    const flash = opts.flash !== false;
    if (mode !== "detail") await enterDetail(undefined, { keepView: true });
    S.centerOn(id, flash);
    if (opts.close && S.toggleIssuesPanel) S.toggleIssuesPanel(false);
  };

  // expose so the issues panel (and any other caller) can force detail mode
  // before navigating to a specific node that only exists in detail view.
  // (delegates to the reveal primitive — item 9.)
  S.showNodeInGraph = function (id) { return S.reveal(id, {}); };

  S.softUpdateGraph = function () {
    softUpdate();
    renderOrphans();
    renderChips();
  };

  /* ================================================================ *
   *  BOOT
   * ================================================================ */
  S.bootGraph = function () {
    S.model = Store.get();

    // acquire DOM elements
    ["stage", "viewport", "edges", "nodeLayer", "zoomInd", "orphanItems", "chips",
     "stageLoading", "breadcrumb"].forEach(
      id => { const el = document.getElementById(id); if (el) els[id] = el; }
    );
    // hulls container (inject if missing)
    let hulls = document.getElementById("hulls");
    if (!hulls) {
      hulls = document.createElement("div");
      hulls.id = "hulls";
      hulls.className = "hulls";
      if (els.viewport) els.viewport.insertBefore(hulls, els.viewport.firstChild);
    }
    els.hulls   = hulls;
    els.minimap = document.getElementById("minimap");

    initPanZoom();
    initMinimapDrag();

    // The focus seam drives every selection/hover/isolation visual: repaint on any
    // change, and refresh the breadcrumb only when the selection itself moves. The rail
    // is a separate subscriber — the two no longer reach across each other's state.
    Focus.subscribe((next, prev) => {
      refreshVisualState();
      if (next.selectedId !== prev.selectedId) renderBreadcrumb();
    });

    // the doc lens is a sibling subscriber: repaint the highlight/dim + refresh the
    // per-node doc badges whenever the active doc, hover preview, or model changes.
    if (DocLens) DocLens.subscribe(() => { refreshVisualState(); applyDocBadges(); });

    els.stage.addEventListener("click", e => {
      if (!e.target.closest(".node, .supernode, .hull-chip")) Focus.deselect();
    });

    // hull chip collapse (delegate from hulls div)
    if (els.hulls) {
      els.hulls.addEventListener("click", e => {
        const b = e.target.closest("[data-collapse]");
        if (b) { e.stopPropagation(); enterOverview(b.dataset.collapse); }
      });
    }

    const fitBtn       = document.getElementById("fitBtn");
    const zoomIn       = document.getElementById("zoomIn");
    const zoomOut      = document.getElementById("zoomOut");
    const allEdgesBtn  = document.getElementById("allEdgesBtn");
    const overviewBtn  = document.getElementById("overviewBtn");

    if (fitBtn)      fitBtn.onclick      = () => S.fit(true);
    if (zoomIn)      zoomIn.onclick      = () => S.zoomBy(1.25);
    if (zoomOut)     zoomOut.onclick     = () => S.zoomBy(1 / 1.25);
    if (allEdgesBtn) allEdgesBtn.onclick  = e => {
      S.allEdges = !S.allEdges;
      e.currentTarget.setAttribute("aria-pressed", S.allEdges);
      refreshVisualState();
    };
    if (overviewBtn) overviewBtn.onclick = () => {
      // button-driven toggle preserves the user's pan/zoom (#13) once a mode is seen.
      if (mode === "overview") enterDetail(undefined, { keepView: true }); else enterOverview();
    };

    // #14 isolate toggle: isolate the selected module's neighbourhood, or clear it.
    const isolateBtn = document.getElementById("isolateBtn");
    if (isolateBtn) isolateBtn.onclick = () => {
      const f = Focus.current();
      if (f.isolatedId) S.clearIsolate();
      else if (f.selectedId) S.isolate(f.selectedId);
      syncIsolateBtn();
    };
    syncIsolateBtn();

    const sb = document.getElementById("searchInput");
    if (sb) {
      sb.addEventListener("input",   () => doSearch(sb.value, false));
      sb.addEventListener("keydown", e => { if (e.key === "Enter") doSearch(sb.value, true); });
      S._searchBox = sb;
    }

    buildDomainPalette();

    S.rebuildGraph().then(() => {
      requestAnimationFrame(() => requestAnimationFrame(() => S.fit(false)));
    });

    let rt;
    window.addEventListener("resize", () => {
      clearTimeout(rt);
      rt = setTimeout(() => { S.fit(true); drawMinimap(); }, 160);
    });
  };

})(window.Studio);
