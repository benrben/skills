/* Unit tests for the PURE transforms in state.js (s1).
 *
 * The normalization layer is the studio's translation between the backend
 * ArchModel (0..1 floats, free-text tests, a suggestion queue) and the studio
 * shape (0..100 ints, tests array, primary suggestion + decisions map). It is the
 * test surface: these assert the mappings directly, with no server.
 *
 * No framework. Run with:  node state.normalize.test.js   (or via ui-tests.js)
 */
"use strict";
const assert = require("node:assert");
const S = require("./state.js");

let passed = 0;
function test(name, fn) { fn(); passed++; console.log("  ok  " + name); }

// --- depth / coverage: backend 0..1 -> studio 0..100 (rounded) --------------
test("depth and coverage scale 0..1 -> 0..100 and round", () => {
  const m = S.normalize({ modules: [{ id: "a", depth: 0.5, coverage: 0.236 }] });
  assert.strictEqual(m.modules[0].depth, 50);
  assert.strictEqual(m.modules[0].coverage, 24);   // 0.236 -> 23.6 -> 24
});

test("missing depth/coverage default to 0", () => {
  const m = S.normalize({ modules: [{ id: "a" }] });
  assert.strictEqual(m.modules[0].depth, 0);
  assert.strictEqual(m.modules[0].coverage, 0);
});

// --- field renames: iface -> interface, leaksTo -> leaks ---------------------
test("iface becomes interface; leaksTo becomes leaks", () => {
  const m = S.normalize({ modules: [{ id: "a", iface: "the promise", leaksTo: ["b"] }] });
  assert.strictEqual(m.modules[0].interface, "the promise");
  assert.deepStrictEqual(m.modules[0].leaks, ["b"]);
});

// --- tests: backend free-text string <-> studio array -----------------------
test("tests string -> single-entry array; empty -> []", () => {
  assert.deepStrictEqual(S.testsToArray("t.py"), ["t.py"]);
  assert.deepStrictEqual(S.testsToArray("  "), []);
  assert.deepStrictEqual(S.testsToArray(["a", "", "b"]), ["a", "b"]);
  const m = S.normalize({ modules: [{ id: "a", tests: "test_a.py" }] });
  assert.deepStrictEqual(m.modules[0].tests, ["test_a.py"]);
});

test("denormFields joins a tests array back to a string on the way out", () => {
  assert.strictEqual(S.testsToString(["a", "b"]), "a\nb");
  const out = S.denormFields({ tests: ["x.py", "y.py"], depth: 0.4 });
  assert.strictEqual(out.tests, "x.py\ny.py");
  assert.strictEqual(out.depth, 0.4);
  // no tests key -> object passed through untouched
  const same = { depth: 0.4 };
  assert.strictEqual(S.denormFields(same), same);
});

// --- suggestion strength spelling -------------------------------------------
test("strength maps Strong/Worth exploring/Speculative -> keys, with fuzzy fallback", () => {
  assert.strictEqual(S.strengthKey("Strong"), "strong");
  assert.strictEqual(S.strengthKey("Worth exploring"), "worth");
  assert.strictEqual(S.strengthKey("Speculative"), "speculative");
  assert.strictEqual(S.strengthKey("very strongly"), "strong");   // fuzzy
  assert.strictEqual(S.strengthKey(""), "speculative");           // default
});

// --- suggestion queue -> primary suggestion + decisions map ------------------
test("primary suggestion is the first still-open candidate", () => {
  const m = S.normalize({ modules: [{ id: "a", suggestions: [
    { id: "a-1", strength: "Strong", decision: "accepted", note: "done", status: "grilled" },
    { id: "a-2", strength: "Worth exploring", status: "open" },
  ] }] });
  // a-1 is decided, so the open a-2 is the primary
  assert.strictEqual(m.modules[0].suggestion.sid, "a-2");
  assert.strictEqual(m.modules[0].suggestions.length, 2);
  // the decided one populates the decisions map, keyed by sid, verdict spelled studio-side
  assert.strictEqual(m.decisions["a-1"].verdict, "accept");
  assert.strictEqual(m.decisions["a-1"].reason, "done");
  assert.ok(!m.decisions["a-2"]);
});

test("a candidate with no open entry has a null primary suggestion", () => {
  const m = S.normalize({ modules: [{ id: "a", suggestions: [
    { id: "a-1", strength: "Strong", decision: "rejected", status: "grilled" },
  ] }] });
  assert.strictEqual(m.modules[0].suggestion, null);
  assert.strictEqual(m.decisions["a-1"].verdict, "reject");
});

test("back-compat: a single m.suggestion is read when there is no queue", () => {
  const m = S.normalize({ modules: [{ id: "a", suggestion: { id: "a-x", strength: "Strong", status: "open" } }] });
  assert.strictEqual(m.modules[0].suggestion.sid, "a-x");
  assert.strictEqual(m.modules[0].suggestions.length, 1);
});

// --- seq increments from the prior cache seq --------------------------------
test("seq is prevSeq + 1 (and starts at 1 with no prior)", () => {
  assert.strictEqual(S.normalize({}).seq, 1);
  assert.strictEqual(S.normalize({}, 7).seq, 8);
});

// --- arrays are always defined ----------------------------------------------
test("array fields default to [] so the UI never sees undefined", () => {
  const m = S.normalize({ modules: [{ id: "a" }] });
  const x = m.modules[0];
  ["files", "tests", "dependsOn", "leaks", "intendsToDependOn", "supersedes", "supersededBy", "suggestions"].forEach((k) => {
    assert.ok(Array.isArray(x[k]), k + " should be an array");
  });
  assert.deepStrictEqual(m.plans, []);
  assert.deepStrictEqual(m.docs, []);
  assert.deepStrictEqual(m.worktrees, []);
});

// --- derived helpers (pure) -------------------------------------------------
test("tierOf thresholds: deep >=67, mid >=34, else shallow", () => {
  assert.strictEqual(S.tierOf(80), "deep");
  assert.strictEqual(S.tierOf(67), "deep");
  assert.strictEqual(S.tierOf(50), "mid");
  assert.strictEqual(S.tierOf(34), "mid");
  assert.strictEqual(S.tierOf(33), "shallow");
});

test("isOrphan: no inbound and no outbound edges", () => {
  const model = { modules: [
    { id: "a", dependsOn: [], leaks: [], intendsToDependOn: [], supersedes: [] },
    { id: "b", dependsOn: ["a"], leaks: [], intendsToDependOn: [], supersedes: [] },
    { id: "c", dependsOn: [], leaks: [], intendsToDependOn: [], supersedes: [] },
  ] };
  assert.strictEqual(S.isOrphan(model, model.modules[0]), false); // b depends on a -> inbound
  assert.strictEqual(S.isOrphan(model, model.modules[1]), false); // b depends out
  assert.strictEqual(S.isOrphan(model, model.modules[2]), true);  // c: nothing in or out
});

test("isOpen / openSuggestions reflect the decisions map", () => {
  const model = S.normalize({ modules: [
    { id: "a", suggestions: [{ id: "a-1", strength: "Strong", status: "open" }] },
    { id: "b", suggestions: [{ id: "b-1", strength: "Strong", decision: "accepted", status: "grilled" }] },
  ] });
  const open = S.openSuggestions(model);
  assert.strictEqual(open.length, 1);
  assert.strictEqual(open[0].sid, "a-1");
});

test("diffModels reports depth changes and +/- module rows", () => {
  const prev = S.normalize({ modules: [{ id: "a", depth: 0.5 }, { id: "gone", depth: 0.2 }] });
  const next = S.normalize({ modules: [{ id: "a", depth: 0.9 }, { id: "new", depth: 0.1 }] });
  const d = S.diffModels(prev, next);
  assert.ok(d.some((r) => r.id === "a" && r.field === "depth" && r.from === 50 && r.to === 90));
  assert.ok(d.some((r) => r.id === "gone" && r.field === "-module"));
  assert.ok(d.some((r) => r.id === "new" && r.field === "+module"));
});

console.log("\n" + passed + " passed");
