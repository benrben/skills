/* arch-map studio — focus seam.
 *
 * The single owner of the studio's "what is focused" state: selection, the two
 * transient hover channels (pointer-over-a-graph-node vs. pointer-over-a-rail-row),
 * and isolation. Before this module that state was four globals declared on the graph
 * but mutated from both the graph and the rail, so neither surface could be tested or
 * changed without the other (the map's one bidirectional leak). Now both are plain
 * subscribers: they call select/hover/isolate and re-render from the change
 * notification — they never reach across each other.
 *
 * The deep behaviour here is the FOCUS PRECEDENCE rule: a transient hover wins over a
 * sticky selection, and a graph hover wins over a rail hover —
 *   focusId = hoverId || railHotId || selectedId
 * That single rule, plus the transitions around it, is what callers can no longer get
 * wrong by poking globals in the wrong order. It is pure (no DOM), so it is the test
 * surface — see focus.test.js.
 *
 * Interface (window.Arch.Focus):
 *   select(id)        — set the sticky selection (null clears; deselect() is the alias)
 *   deselect()        — clear the selection
 *   hover(id, source) — set a transient hover; source "rail" → railHotId, else hoverId
 *   isolate(id)       — mark the isolated neighbourhood (the graph does the framing)
 *   clearIsolate()    — clear isolation
 *   current()         — { selectedId, hoverId, railHotId, isolatedId, focusId }
 *   subscribe(cb)     — cb(next, prev) on every change; returns an unsubscribe fn
 */
(function (root) {
  "use strict";

  function createFocus() {
    let selectedId = null;
    let hoverId    = null;
    let railHotId  = null;
    let isolatedId = null;
    const subs = [];

    function snapshot() {
      return {
        selectedId: selectedId,
        hoverId:    hoverId,
        railHotId:  railHotId,
        isolatedId: isolatedId,
        // precedence: a live hover wins over a sticky selection; graph hover wins over rail.
        focusId:    hoverId || railHotId || selectedId,
      };
    }

    function notify(prev) {
      const next = snapshot();
      for (let i = 0; i < subs.length; i++) {
        try { subs[i](next, prev); } catch (e) { /* a bad subscriber must not break the others */ }
      }
    }

    return {
      select: function (id) {
        id = id || null;
        if (selectedId === id) return;          // no-op changes don't notify
        const prev = snapshot(); selectedId = id; notify(prev);
      },
      deselect: function () {
        if (selectedId === null) return;
        const prev = snapshot(); selectedId = null; notify(prev);
      },
      hover: function (id, source) {
        id = id || null;
        if (source === "rail") {
          if (railHotId === id) return;
          const prev = snapshot(); railHotId = id; notify(prev);
        } else {
          if (hoverId === id) return;
          const prev = snapshot(); hoverId = id; notify(prev);
        }
      },
      isolate: function (id) {
        id = id || null;
        if (isolatedId === id) return;
        const prev = snapshot(); isolatedId = id; notify(prev);
      },
      clearIsolate: function () {
        if (isolatedId === null) return;
        const prev = snapshot(); isolatedId = null; notify(prev);
      },
      current: snapshot,
      subscribe: function (cb) {
        if (typeof cb !== "function") return function () {};
        subs.push(cb);
        return function () { const i = subs.indexOf(cb); if (i >= 0) subs.splice(i, 1); };
      },
      // test-only: reset all state without notifying (lets each test start clean).
      _reset: function () { selectedId = hoverId = railHotId = isolatedId = null; },
    };
  }

  // Browser: expose the shared singleton on window.Arch (created by state.js, but be
  // defensive about load order). Node (tests): export the factory.
  if (root) {
    root.Arch = root.Arch || {};
    root.Arch.Focus = createFocus();
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { createFocus: createFocus };
  }
})(typeof window !== "undefined" ? window : null);
