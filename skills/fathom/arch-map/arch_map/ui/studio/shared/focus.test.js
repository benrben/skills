/* Interface tests for the focus seam (focus.js).
 *
 * The interface IS the test surface: these assert the precedence rule and the
 * selection / hover / isolation transitions — the deep behaviour that used to be
 * smeared across DOM handlers in studio-graph.js + studio-rail.js and was untestable.
 *
 * No framework (the repo has no JS test runner). Run with:  node focus.test.js
 */
"use strict";
const assert = require("node:assert");
const { createFocus } = require("./focus.js");

let passed = 0;
function test(name, fn) {
  const f = createFocus();
  fn(f);
  passed++;
  console.log("  ok  " + name);
}

// --- precedence: hover > railHot > selected ---------------------------------
test("focusId falls back to selection when nothing is hovered", (f) => {
  f.select("a");
  assert.strictEqual(f.current().focusId, "a");
});

test("a graph hover wins over the selection, and releasing it falls back", (f) => {
  f.select("a");
  f.hover("b", "graph");
  assert.strictEqual(f.current().focusId, "b");
  f.hover(null, "graph");
  assert.strictEqual(f.current().focusId, "a");
});

test("a rail hover wins over selection but loses to a graph hover", (f) => {
  f.select("a");
  f.hover("r", "rail");
  assert.strictEqual(f.current().focusId, "r");        // railHot > selected
  f.hover("g", "graph");
  assert.strictEqual(f.current().focusId, "g");        // hover > railHot
  f.hover(null, "graph");
  assert.strictEqual(f.current().focusId, "r");        // back to railHot
});

// --- isolation is independent of selection ----------------------------------
test("isolate/clearIsolate do not disturb the selection", (f) => {
  f.select("a");
  f.isolate("x");
  assert.strictEqual(f.current().isolatedId, "x");
  assert.strictEqual(f.current().selectedId, "a");
  f.clearIsolate();
  assert.strictEqual(f.current().isolatedId, null);
  assert.strictEqual(f.current().selectedId, "a");
});

// --- deselect clears focus when nothing is hovered --------------------------
test("deselect drops the selection (and the focus with it)", (f) => {
  f.select("a");
  f.deselect();
  assert.strictEqual(f.current().selectedId, null);
  assert.strictEqual(f.current().focusId, null);
});

// --- subscription carries next + prev ---------------------------------------
test("subscribers receive (next, prev) on a real change", (f) => {
  let calls = [];
  f.subscribe((next, prev) => calls.push({ next, prev }));
  f.select("a");
  assert.strictEqual(calls.length, 1);
  assert.strictEqual(calls[0].prev.selectedId, null);
  assert.strictEqual(calls[0].next.selectedId, "a");
});

// --- no-op changes do not notify --------------------------------------------
test("re-selecting the same id does not notify", (f) => {
  let n = 0;
  f.subscribe(() => n++);
  f.select("a");
  f.select("a");                 // no-op
  f.hover(null, "graph");        // no-op (already null)
  assert.strictEqual(n, 1);
});

// --- unsubscribe stops delivery ---------------------------------------------
test("unsubscribe removes the subscriber", (f) => {
  let n = 0;
  const off = f.subscribe(() => n++);
  f.select("a");
  off();
  f.select("b");
  assert.strictEqual(n, 1);
});

console.log("\n" + passed + " passed");
