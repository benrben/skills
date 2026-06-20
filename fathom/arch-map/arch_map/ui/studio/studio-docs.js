/* arch-map studio — Doc Browser (the "Docs" rail tab).
 *
 * The UI adapter over the docs axis: a summary-first faceted list, a markdown
 * reader with metadata + drift badge + supersedes links, and create/edit forms
 * with a scope picker. It DRIVES + SUBSCRIBES to the DocLens seam (doclens.js):
 *   - hovering a card  -> DocLens.hover(id)   (graph previews the scope)
 *   - clicking a card  -> DocLens.setActive(id) (graph highlights + dims)  + zoom
 *   - facet controls   -> DocLens.setFacets(...)
 * It never reaches into the graph; the graph is a separate DocLens subscriber.
 * Mutations go through Store.addDoc / updateDoc / deleteDoc (-> /api/docs). The
 * faceting/derivation logic itself lives + is tested in doclens.js; this file is
 * DOM only, so it is browser-verified.
 */
(function () {
  "use strict";
  const S = (window.Studio = window.Studio || {});
  const Store = window.Arch.Store;
  const DocLens = window.Arch.DocLens;

  const DOC_TYPES = ["glossary", "note", "risk", "runbook", "postmortem",
                     "diagram", "rfc", "adr", "spec", "rule", "ceiling"];
  const SCOPE_KINDS = ["system", "domain", "explicit", "query"];

  let view = "list";       // list | reader | form
  let editingId = null;    // doc id when editing an existing doc; null = creating
  let formKind = "system"; // live scope-kind in the open form
  let pane = null;

  function esc(s) {
    return (s == null ? "" : String(s)).replace(/[&<>"]/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
  function slug(s) {
    return (String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "")) || "doc";
  }
  function distinct(arr) { return Array.from(new Set(arr.filter(Boolean))); }
  function allDocs() { return (Store.get().docs) || []; }

  // tiny, safe markdown: escape FIRST, then apply a small set of patterns.
  function md(src) {
    if (!src) return "";
    let h = esc(src)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>")
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, t, u) =>
        /^(https?:|\/|#)/.test(u) ? `<a href="${u}" target="_blank" rel="noopener">${t}</a>` : t);
    return h.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean).map((b) => {
      const hm = b.match(/^(#{1,4})\s+([\s\S]*)$/);
      if (hm && b.indexOf("\n") < 0) { const l = Math.min(6, hm[1].length + 2); return `<h${l}>${hm[2]}</h${l}>`; }
      if (/^[-*]\s+/.test(b)) {
        const items = b.split(/\n/).filter((l) => /^[-*]\s+/.test(l))
          .map((l) => `<li>${l.replace(/^[-*]\s+/, "")}</li>`).join("");
        return `<ul>${items}</ul>`;
      }
      return `<p>${b.replace(/\n/g, "<br>")}</p>`;
    }).join("");
  }

  // A `diagram` doc's body IS Mermaid source — render it as a graph, not prose.
  // The raw source is the fallback if Mermaid can't load (offline / MCP-App host).
  function bodyHtml(d) {
    if (d.type !== "diagram") return md(d.body);
    return `<pre class="mermaid" data-diagram>${esc(d.body || "")}</pre>`;
  }
  // Lazy-load Mermaid from a CDN the first time a diagram is shown, then render
  // any pending <pre class="mermaid"> in the pane. ceiling: CDN esm import — vendor
  // it under /assets if the studio must render diagrams fully offline.
  let _mermaid = null;
  function renderDiagrams() {
    const nodes = pane ? Array.from(pane.querySelectorAll("[data-diagram]")) : [];
    if (!nodes.length) return;
    const run = (m) => { try { m.run({ nodes }); } catch (e) {} };
    if (_mermaid) return run(_mermaid);
    import("https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs")
      .then((mod) => { _mermaid = mod.default; _mermaid.initialize({ startOnLoad: false, theme: "dark" }); run(_mermaid); })
      .catch(() => {});  // leave the raw source visible on failure
  }

  function scopeText(sc) {
    sc = sc || { kind: "system" };
    if (sc.kind === "system") return "Whole system";
    if (sc.kind === "domain") return "Domain: " + (sc.domain || "?");
    if (sc.kind === "explicit") return "Explicit: " + ((sc.ids || []).length) + " modules";
    if (sc.kind === "query") return "Query";
    return sc.kind || "";
  }
  function typeChip(t) { return `<span class="doc-type doc-type-${esc(t)}">${esc(t)}</span>`; }

  // ---- list ----------------------------------------------------------------
  function facetBar(cur) {
    const f = cur.facets;
    const docs = allDocs();
    const opt = (val, cur) => `<option value="${esc(val)}"${val === cur ? " selected" : ""}>${esc(val || "all")}</option>`;
    const typeSel = [""].concat(DOC_TYPES).map((t) => opt(t, f.type)).join("");
    const statusSel = [""].concat(distinct(docs.map((d) => d.status))).map((s) => opt(s, f.status)).join("");
    const kindSel = [""].concat(SCOPE_KINDS).map((k) => opt(k, f.scopeKind)).join("");
    const tags = distinct(docs.reduce((a, d) => a.concat(d.tags || []), []));
    const tagSel = [""].concat(tags).map((t) => opt(t, f.tag)).join("");
    return `
      <div class="docs-facets">
        <select data-facet="type" title="Filter by type">${typeSel}</select>
        <select data-facet="status" title="Filter by status">${statusSel}</select>
        <select data-facet="scopeKind" title="Filter by scope">${kindSel}</select>
        <select data-facet="tag" title="Filter by tag"${tags.length ? "" : " disabled"}>${tagSel}</select>
        <button class="btn primary docs-new" data-docs-new>+ New</button>
      </div>`;
  }

  function card(d) {
    const drift = (d.drift && d.drift.length)
      ? `<span class="doc-drift" title="${esc(d.drift.length)} referenced module(s) no longer exist">⚠ drift</span>` : "";
    return `<article class="doc-card" data-doc="${esc(d.id)}" tabindex="0">
        <div class="doc-card-top">${typeChip(d.type)}${d.status ? `<span class="doc-status">${esc(d.status)}</span>` : ""}${drift}</div>
        <div class="doc-card-title">${esc(d.title)}</div>
        ${d.summary ? `<div class="doc-card-summary">${esc(d.summary)}</div>` : ""}
        <div class="doc-card-scope">${esc(d.scopeLabel || scopeText(d.scope))}</div>
      </article>`;
  }

  function listHtml(cur) {
    const docs = cur.docs;
    const total = allDocs().length;
    let body;
    if (!total) {
      body = `<div class="docs-empty">No docs yet. Attach a spec, adr, diagram, note or runbook to a module, a domain, or the whole system.<br><button class="btn primary docs-new" data-docs-new>+ New doc</button></div>`;
    } else if (!docs.length) {
      body = `<div class="docs-empty">No docs match these filters.</div>`;
    } else {
      body = `<div class="docs-list">${docs.map(card).join("")}</div>`;
    }
    return facetBar(cur) + body;
  }

  // ---- reader --------------------------------------------------------------
  function reader(d) {
    const meta = [d.author && ("by " + esc(d.author)), d.updated && ("updated " + esc(d.updated)),
                  d.created && ("created " + esc(d.created))].filter(Boolean).join(" · ");
    const sup = (d.supersedes || []).map((id) => `<button class="doc-link" data-doc-link="${esc(id)}">${esc(id)}</button>`).join(" ");
    const drift = (d.drift && d.drift.length)
      ? `<span class="doc-drift" title="missing: ${esc((d.drift || []).join(", "))}">⚠ ${esc(d.drift.length)} missing</span>` : "";
    const adr = d.adrRef ? `<div class="doc-adrref">ADR: <button class="doc-link" data-doc-link="${esc(d.adrRef)}">${esc(d.adrRef)}</button></div>` : "";
    return `
      <div class="doc-reader">
        <div class="doc-reader-head">
          <button class="doc-back" data-docs-back>← all docs</button>
          <div class="doc-reader-actions">
            <button class="btn" data-doc-edit="${esc(d.id)}">Edit</button>
            <button class="btn danger" data-doc-del="${esc(d.id)}">Delete</button>
          </div>
        </div>
        <div class="doc-reader-meta">${typeChip(d.type)}${d.status ? `<span class="doc-status">${esc(d.status)}</span>` : ""}${meta ? `<span class="doc-meta-bits">${meta}</span>` : ""}</div>
        <h2 class="doc-reader-title">${esc(d.title)}</h2>
        <div class="doc-scope-row">
          <span class="doc-scope-label">${esc(d.scopeLabel || scopeText(d.scope))}</span>
          <button class="btn ghost" data-doc-zoom>⌖ Zoom to scope</button>
          ${drift}
        </div>
        ${(d.tags && d.tags.length) ? `<div class="doc-tags">${d.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>` : ""}
        ${sup ? `<div class="doc-supersedes">supersedes: ${sup}</div>` : ""}
        ${adr}
        <div class="doc-body">${bodyHtml(d)}</div>
      </div>`;
  }

  // ---- form ----------------------------------------------------------------
  function scopeFieldsHtml(kind, sc) {
    sc = sc || {};
    if (kind === "domain") return `<input name="scopeDomain" value="${esc(sc.domain || "")}" placeholder="domain name (e.g. ui)">`;
    if (kind === "explicit") return `<textarea name="scopeIds" rows="2" placeholder="module ids — comma or newline separated">${esc((sc.ids || []).join(", "))}</textarea>`;
    if (kind === "query") return `<textarea name="scopePredicate" rows="2" placeholder='{"domain":"ui","tag":"pii"}'>${esc(sc.predicate ? JSON.stringify(sc.predicate) : "")}</textarea>`;
    return `<div class="doc-form-hint">Applies to the whole system.</div>`;
  }
  function formHtml(d) {
    d = d || { type: "note", scope: { kind: "system" } };
    const sc = d.scope || { kind: "system" };
    const typeOpts = DOC_TYPES.map((t) => `<option value="${t}"${t === d.type ? " selected" : ""}>${t}</option>`).join("");
    const kindOpts = SCOPE_KINDS.map((k) => `<option value="${k}"${k === formKind ? " selected" : ""}>${k}</option>`).join("");
    return `
      <form class="doc-form" id="docForm">
        <div class="doc-form-head"><button type="button" class="doc-back" data-docs-back>← cancel</button><b>${editingId ? "Edit doc" : "New doc"}</b></div>
        <label>Type<select name="type">${typeOpts}</select></label>
        <label>Title<input name="title" value="${esc(d.title || "")}" required></label>
        <label>Summary<input name="summary" value="${esc(d.summary || "")}" placeholder="one-line TL;DR"></label>
        <label>Status<input name="status" value="${esc(d.status || "")}" placeholder="e.g. accepted / active / draft"></label>
        <label>Tags<input name="tags" value="${esc((d.tags || []).join(", "))}" placeholder="comma, separated"></label>
        <label>Scope<select name="scopeKind">${kindOpts}</select></label>
        <div id="scopeFields">${scopeFieldsHtml(formKind, sc)}</div>
        <label>Body (markdown)<textarea name="body" rows="8">${esc(d.body || "")}</textarea></label>
        <label>ADR ref<input name="adrRef" value="${esc(d.adrRef || "")}" placeholder="id of the adr doc this records"></label>
        <div class="doc-form-foot"><button type="button" class="btn ghost" data-docs-back>Cancel</button><button type="submit" class="btn primary">${editingId ? "Save" : "Create"}</button></div>
      </form>`;
  }

  // ---- render + wiring -----------------------------------------------------
  function render() {
    if (!pane) return;
    const cur = DocLens ? DocLens.current() : { docs: [], facets: {}, activeDocId: null };
    if (view === "form") {
      const d = editingId ? DocLens.doc(editingId) : null;
      if (!formKind) formKind = (d && d.scope && d.scope.kind) || "system";
      pane.innerHTML = formHtml(d);
      wireForm();
    } else if (view === "reader" && cur.activeDocId && DocLens.doc(cur.activeDocId)) {
      pane.innerHTML = reader(DocLens.doc(cur.activeDocId));
      wireReader();
      renderDiagrams();
    } else {
      view = "list";
      pane.innerHTML = listHtml(cur);
      wireList();
    }
  }
  S.renderDocs = render;

  function wireList() {
    pane.querySelectorAll("[data-facet]").forEach((sel) => {
      sel.onchange = () => { const p = {}; p[sel.dataset.facet] = sel.value; DocLens.setFacets(p); };
    });
    pane.querySelectorAll("[data-docs-new]").forEach((b) => b.onclick = openNew);
    pane.querySelectorAll(".doc-card").forEach((c) => {
      const id = c.dataset.doc;
      c.onmouseenter = () => DocLens.hover(id);
      c.onmouseleave = () => DocLens.hover(null);
      c.onclick = () => openDoc(id);
      c.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDoc(id); } };
    });
  }
  function wireReader() {
    pane.querySelectorAll("[data-docs-back]").forEach((b) => b.onclick = backToList);
    const z = pane.querySelector("[data-doc-zoom]");
    if (z) z.onclick = () => { const ids = DocLens.current().highlightIds; if (S.zoomToScope) S.zoomToScope(ids); };
    const e = pane.querySelector("[data-doc-edit]");
    if (e) e.onclick = () => openEdit(e.dataset.docEdit);
    const del = pane.querySelector("[data-doc-del]");
    if (del) del.onclick = () => {
      const id = del.dataset.docDel;
      if (window.confirm("Delete doc '" + id + "'?")) { Store.deleteDoc(id); DocLens.clear(); view = "list"; render(); }
    };
    pane.querySelectorAll("[data-doc-link]").forEach((b) => b.onclick = () => openDoc(b.dataset.docLink));
  }
  function wireForm() {
    pane.querySelectorAll("[data-docs-back]").forEach((b) => b.onclick = backToList);
    const kindSel = pane.querySelector('select[name="scopeKind"]');
    if (kindSel) kindSel.onchange = () => {
      formKind = kindSel.value;
      const host = pane.querySelector("#scopeFields");
      if (host) host.innerHTML = scopeFieldsHtml(formKind, {});
    };
    const form = pane.querySelector("#docForm");
    if (form) form.onsubmit = onSubmit;
  }

  // ---- actions -------------------------------------------------------------
  function openDoc(id) {
    if (!id || !DocLens.doc(id)) return;
    DocLens.setActive(id);        // highlights its scope + dims the rest, in place
    view = "reader";
    render();                     // zoom is opt-in via the reader's "⌖ Zoom to scope" button
  }
  function backToList() { DocLens.clear(); editingId = null; view = "list"; render(); }
  function openNew() { editingId = null; formKind = "system"; view = "form"; render(); }
  function openEdit(id) {
    const d = DocLens.doc(id); if (!d) return;
    editingId = id; formKind = (d.scope && d.scope.kind) || "system"; view = "form"; render();
  }
  function buildScope(form) {
    const kind = form.scopeKind.value;
    if (kind === "domain") return { kind: "domain", domain: (form.scopeDomain ? form.scopeDomain.value.trim() : "") };
    if (kind === "explicit") {
      const ids = (form.scopeIds ? form.scopeIds.value : "").split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);
      return { kind: "explicit", ids };
    }
    if (kind === "query") {
      let predicate = {};
      const raw = (form.scopePredicate ? form.scopePredicate.value.trim() : "");
      if (raw) { try { predicate = JSON.parse(raw); } catch (e) { throw new Error("Scope query must be valid JSON"); } }
      return { kind: "query", predicate };
    }
    return { kind: "system" };
  }
  function onSubmit(e) {
    e.preventDefault();
    const form = e.target;
    let scope;
    try { scope = buildScope(form); }
    catch (err) { if (S.toast) S.toast(String(err.message || err), "var(--leak)"); return; }
    const tags = form.tags.value.split(",").map((s) => s.trim()).filter(Boolean);
    const fields = {
      type: form.type.value, title: form.title.value.trim(), summary: form.summary.value.trim(),
      status: form.status.value.trim(), tags, scope, body: form.body.value, adrRef: form.adrRef.value.trim(),
    };
    if (!fields.title) { if (S.toast) S.toast("Title is required", "var(--leak)"); return; }
    if (editingId) {
      Store.updateDoc(editingId, fields);
      view = "reader"; render();
    } else {
      const id = slug(fields.title) + "-" + Date.now().toString(36).slice(-4);
      Store.addDoc(Object.assign({ id }, fields));
      DocLens.clear(); editingId = null; view = "list"; render();
      if (S.toast) S.toast("Created doc " + id, "var(--accent)");
    }
  }

  // ---- lens subscription (re-render on active/facets/content, NOT on hover) -
  let lastSig = null;
  function sigOf(s) {
    return s.activeDocId + "|" + JSON.stringify(s.facets) + "|" +
      s.docs.map((d) => d.id + ":" + d.status + ":" + d.title + ":" + (d.resolvedModuleIds ? d.resolvedModuleIds.length : 0) + ":" + d.scopeLabel).join(",");
  }
  function onLensChange(next) {
    const sig = sigOf(next);
    if (sig === lastSig) return;          // hover-only delta -> the graph handles it
    lastSig = sig;
    if (view === "form") return;          // don't yank a form out from under the user
    if (!next.activeDocId && view === "reader") view = "list";
    if (next.activeDocId && view === "list") view = "reader";
    render();
  }

  S.bootDocs = function () {
    pane = document.getElementById("docsPane");
    if (!pane) return;
    if (DocLens) {
      DocLens.subscribe(onLensChange);
      // broadcast() feeds DocLens on every later change, but it does NOT fire on the
      // initial model load (graph/rail read Store.get() directly at boot), so seed it
      // here — otherwise the pane + graph badges stay empty until the first mutation.
      DocLens.setModel(Store.get());
    }
    render();
  };
})();
