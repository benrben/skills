/* Interface tests for the doc lens seam (doclens.js).
 *
 * The interface IS the test surface: these assert the hover>active precedence, the
 * highlight/dim derivation from baked resolvedModuleIds, drift passthrough, facet
 * filtering of the doc list, and the setModel transitions (deleted active doc,
 * no-op poll). Pure (no DOM, no fetch) — the model is a plain object.
 *
 * No framework. Run with:  node doclens.test.js
 */
"use strict";
const assert = require("node:assert");
const { createDocLens } = require("./doclens.js");

const MODEL = {
  modules: [{ id: "a" }, { id: "b" }, { id: "c" }],
  docs: [
    { id: "d1", type: "rule", status: "active", scope: { kind: "domain" },
      tags: ["pii"], resolvedModuleIds: ["a", "b"], drift: [], scopeLabel: "Domain: ui — 2 modules" },
    { id: "d2", type: "adr", status: "accepted", scope: { kind: "explicit" },
      tags: [], resolvedModuleIds: ["c"], drift: ["gone"], scopeLabel: "Explicit — 1 module (1 missing)" },
  ],
  docMembership: { a: ["d1"], b: ["d1"], c: ["d2"] },
};

let passed = 0;
function test(name, fn) {
  const f = createDocLens();
  f.setModel(JSON.parse(JSON.stringify(MODEL)));   // fresh copy per test
  fn(f);
  passed++;
  console.log("  ok  " + name);
}

// --- highlight / dim derivation ---------------------------------------------
test("activating a doc highlights its resolved ids and dims the rest", (f) => {
  f.setActive("d1");
  const s = f.current();
  assert.strictEqual(s.focusDocId, "d1");
  assert.deepStrictEqual(s.highlightIds, ["a", "b"]);
  assert.deepStrictEqual(s.dimmedIds, ["c"]);        // allIds \ highlight
});

test("nothing focused = nothing highlighted or dimmed", (f) => {
  const s = f.current();
  assert.deepStrictEqual(s.highlightIds, []);
  assert.deepStrictEqual(s.dimmedIds, []);
});

// --- hover preview wins over the active pin ----------------------------------
test("a hover preview wins over the active doc, releasing it falls back", (f) => {
  f.setActive("d1");
  f.hover("d2");
  let s = f.current();
  assert.strictEqual(s.focusDocId, "d2");
  assert.deepStrictEqual(s.highlightIds, ["c"]);
  assert.deepStrictEqual(s.missingIds, ["gone"]);    // drift passthrough
  f.hover(null);
  assert.strictEqual(f.current().focusDocId, "d1");  // back to the pin
});

// --- facets filter the doc list ---------------------------------------------
test("facets filter the doc list", (f) => {
  assert.deepStrictEqual(f.current().docs.map((d) => d.id), ["d1", "d2"]);
  f.setFacets({ type: "adr" });
  assert.deepStrictEqual(f.current().docs.map((d) => d.id), ["d2"]);
  f.setFacets({ type: "" });                          // clear -> all again
  assert.deepStrictEqual(f.current().docs.map((d) => d.id), ["d1", "d2"]);
  f.setFacets({ tag: "pii" });
  assert.deepStrictEqual(f.current().docs.map((d) => d.id), ["d1"]);
});

// --- membership lookup ------------------------------------------------------
test("docsForModule returns the inverted membership", (f) => {
  assert.deepStrictEqual(f.docsForModule("a"), ["d1"]);
  assert.deepStrictEqual(f.docsForModule("c"), ["d2"]);
  assert.deepStrictEqual(f.docsForModule("nope"), []);
});

// --- setModel drops a deleted active doc ------------------------------------
test("setModel drops the active doc if it was deleted", (f) => {
  f.setActive("d1");
  const without = { modules: MODEL.modules, docs: [MODEL.docs[1]], docMembership: { c: ["d2"] } };
  f.setModel(without);
  assert.strictEqual(f.current().activeDocId, null);
});

// --- no-op poll does not notify ---------------------------------------------
test("re-feeding an unchanged model does not notify", (f) => {
  let n = 0;
  f.subscribe(() => n++);
  f.setModel(JSON.parse(JSON.stringify(MODEL)));     // identical -> no notify
  assert.strictEqual(n, 0);
});

// --- subscription carries (next, prev) --------------------------------------
test("subscribers receive (next, prev) on activation", (f) => {
  let calls = [];
  f.subscribe((next, prev) => calls.push({ next, prev }));
  f.setActive("d1");
  assert.strictEqual(calls.length, 1);
  assert.strictEqual(calls[0].prev.focusDocId, null);
  assert.strictEqual(calls[0].next.focusDocId, "d1");
});

test("unsubscribe stops delivery", (f) => {
  let n = 0;
  const off = f.subscribe(() => n++);
  f.setActive("d1");
  off();
  f.setActive("d2");
  assert.strictEqual(n, 1);
});

console.log("\n" + passed + " passed");
