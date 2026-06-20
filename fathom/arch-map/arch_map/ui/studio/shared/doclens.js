/* arch-map studio — doc lens seam.
 *
 * The single owner of the studio's "docs" axis, the sibling of the focus seam
 * (focus.js). It owns: the ACTIVE lens (which doc overlays the graph), a transient
 * HOVER doc (for pre-commit scope preview from the list), and the FACET filter
 * state (type / status / scope-kind / tag) for the doc browser. Graph and browser
 * are plain subscribers: they call setActive / hover / setFacets and re-render from
 * the change notification — they never reach across each other.
 *
 * The deep behaviour is DERIVATION + PRECEDENCE: from the model's baked
 * doc.resolvedModuleIds it computes, for the focused doc,
 *   focusDocId  = hoverDocId || activeDocId         (a preview wins over the pin)
 *   highlightIds = focus doc's resolvedModuleIds
 *   dimmedIds    = every module id NOT in highlightIds (only when a doc is focused)
 *   missingIds   = the focus doc's drift (explicit ids that no longer exist)
 * plus the faceted doc list. It is pure (no DOM, no fetch), so it is the test
 * surface — see doclens.test.js. The graph computes the *complement* here, never
 * the resolver: the resolver returns ids, the lens turns them into a paint plan.
 *
 * Interface (window.Arch.DocLens):
 *   setModel(model)    — feed the normalized studio model {modules,docs,docMembership}
 *   setActive(docId)   — set the sticky lens (null clears); clear() is the alias
 *   clear()            — clear the active lens
 *   hover(docId)       — set the transient preview doc (null clears)
 *   setFacets(partial) — merge {type?,status?,scopeKind?,tag?}; "" means "no filter"
 *   current()          — the snapshot (see below)
 *   doc(id) / docsForModule(id) — lookups backed by the fed model
 *   subscribe(cb)      — cb(next, prev) on every change; returns an unsubscribe fn
 */
(function (root) {
  "use strict";

  function matchFacets(d, f) {
    if (f.type && d.type !== f.type) return false;
    if (f.status && d.status !== f.status) return false;
    if (f.scopeKind && (d.scope && d.scope.kind) !== f.scopeKind) return false;
    if (f.tag && !(Array.isArray(d.tags) && d.tags.indexOf(f.tag) >= 0)) return false;
    return true;
  }

  function modelSignature(docs, mods) {
    // changes that affect derivation: a doc's resolved set / facet fields, or the
    // module id set (so a doc whose domain gained a module re-notifies).
    var parts = docs.map(function (d) {
      return d.id + ":" + (d.resolvedModuleIds || []).join(".") +
             ":" + d.type + ":" + d.status + ":" + (d.tags || []).join(".");
    });
    return parts.join("|") + "##" + mods.map(function (m) { return m.id; }).join(",");
  }

  function createDocLens() {
    var activeDocId = null;
    var hoverDocId  = null;
    var facets = { type: "", status: "", scopeKind: "", tag: "" };
    var docsById = {};
    var order    = [];
    var allIds   = [];
    var membership = {};
    var modelSig = "";
    var subs = [];

    function focusDoc() {
      var id = hoverDocId || activeDocId;
      return id ? (docsById[id] || null) : null;
    }

    function highlightIds() {
      var d = focusDoc();
      return d && Array.isArray(d.resolvedModuleIds) ? d.resolvedModuleIds.slice() : [];
    }

    function dimmedIds() {
      var d = focusDoc();
      if (!d) return [];
      var hi = {};
      (d.resolvedModuleIds || []).forEach(function (id) { hi[id] = 1; });
      return allIds.filter(function (id) { return !hi[id]; });
    }

    function facetedDocs() {
      var out = [];
      for (var i = 0; i < order.length; i++) {
        var d = docsById[order[i]];
        if (d && matchFacets(d, facets)) out.push(d);
      }
      return out;
    }

    function snapshot() {
      var d = focusDoc();
      return {
        activeDocId: activeDocId,
        hoverDocId:  hoverDocId,
        focusDocId:  hoverDocId || activeDocId,
        facets:      { type: facets.type, status: facets.status, scopeKind: facets.scopeKind, tag: facets.tag },
        highlightIds: highlightIds(),
        dimmedIds:    dimmedIds(),
        missingIds:   d && Array.isArray(d.drift) ? d.drift.slice() : [],
        scopeLabel:   d ? (d.scopeLabel || "") : "",
        docs:         facetedDocs(),
      };
    }

    function notify(prev) {
      var next = snapshot();
      for (var i = 0; i < subs.length; i++) {
        try { subs[i](next, prev); } catch (e) { /* a bad subscriber must not break the others */ }
      }
    }

    return {
      setModel: function (model) {
        model = model || {};
        var docs = Array.isArray(model.docs) ? model.docs : [];
        var mods = Array.isArray(model.modules) ? model.modules : [];
        var sig = modelSignature(docs, mods);
        if (sig === modelSig) return;            // unchanged poll -> don't notify
        var prev = snapshot();
        docsById = {}; order = [];
        docs.forEach(function (d) { docsById[d.id] = d; order.push(d.id); });
        allIds = mods.map(function (m) { return m.id; });
        membership = model.docMembership || {};
        if (activeDocId && !docsById[activeDocId]) activeDocId = null;   // active doc was deleted
        if (hoverDocId && !docsById[hoverDocId]) hoverDocId = null;
        modelSig = sig;
        notify(prev);
      },
      setActive: function (id) {
        id = id || null;
        if (activeDocId === id) return;
        var prev = snapshot(); activeDocId = id; notify(prev);
      },
      clear: function () {
        if (activeDocId === null) return;
        var prev = snapshot(); activeDocId = null; notify(prev);
      },
      hover: function (id) {
        id = id || null;
        if (hoverDocId === id) return;
        var prev = snapshot(); hoverDocId = id; notify(prev);
      },
      setFacets: function (partial) {
        partial = partial || {};
        var next = {
          type:      "type" in partial ? (partial.type || "") : facets.type,
          status:    "status" in partial ? (partial.status || "") : facets.status,
          scopeKind: "scopeKind" in partial ? (partial.scopeKind || "") : facets.scopeKind,
          tag:       "tag" in partial ? (partial.tag || "") : facets.tag,
        };
        if (next.type === facets.type && next.status === facets.status &&
            next.scopeKind === facets.scopeKind && next.tag === facets.tag) return;
        var prev = snapshot(); facets = next; notify(prev);
      },
      current: snapshot,
      doc: function (id) { return docsById[id] || null; },
      docsForModule: function (id) { return (membership[id] || []).slice(); },
      subscribe: function (cb) {
        if (typeof cb !== "function") return function () {};
        subs.push(cb);
        return function () { var i = subs.indexOf(cb); if (i >= 0) subs.splice(i, 1); };
      },
      // test-only: reset all state without notifying.
      _reset: function () {
        activeDocId = hoverDocId = null;
        facets = { type: "", status: "", scopeKind: "", tag: "" };
        docsById = {}; order = []; allIds = []; membership = {}; modelSig = "";
      },
    };
  }

  if (root) {
    root.Arch = root.Arch || {};
    root.Arch.DocLens = createDocLens();
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { createDocLens: createDocLens };
  }
})(typeof window !== "undefined" ? window : null);
