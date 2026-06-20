/* Characterization tests for the optimistic-write PROTOCOL in createStore (s3).
 *
 * studio-state's deep behaviour is the reconcile protocol: optimistic writes, the
 * monotonic writeGen + pendingWrites guards that stop a stale server snapshot from
 * clobbering a newer write, rollback on a rejected write, and the focus/poll
 * reconcile. It used to be welded to a live transport and so had zero tests; now
 * the transport is an injected PORT, so we drive it against an in-memory stub.
 *
 * No framework. Run with:  node state.protocol.test.js   (or via ui-tests.js)
 */
"use strict";
const assert = require("node:assert");
const { createStore } = require("./state.js");

// async-aware runner: register tests, then run them in order so one failure
// isolates and the process exits non-zero (ui-tests.js keys off the exit code).
const tests = [];
function test(name, fn) { tests.push({ name, fn }); }

const flush = () => new Promise((r) => setTimeout(r, 0));
function deferred() { let resolve, reject; const promise = new Promise((res, rej) => { resolve = res; reject = rej; }); return { promise, resolve, reject }; }

// raw backend model (depth is 0..1) with one module
function rawModel(depth) {
  return { repo: "r", modules: [{ id: "m1", label: "M1", domain: "d", depth: depth, coverage: 0.2 }],
           plans: [], docs: [], worktrees: [], board: null };
}

// in-memory transport adapter the protocol runs against. Gates let a test hold a
// getModel / act open to interleave a poll with a write deterministically.
function makeStub(depth) {
  const stub = {
    model: rawModel(depth),
    actCalls: [],
    rejectActOnce: null,   // string -> the next act throws it
    actGate: null,         // deferred -> act awaits before applying/returning
    getModelGate: null,    // deferred -> getModel returns the SNAPSHOT taken at call time
    apply(body) {
      const m = (stub.model.modules || []).find((x) => x.id === body.module || x.id === body.id);
      if (body.action === "set_depth" && m) m.depth = body.score;
      if (body.action === "set_coverage" && m) m.coverage = body.fraction;
    },
    transport: {
      async getModel() {
        const snap = JSON.stringify(stub.model);     // capture at call time
        if (stub.getModelGate) { await stub.getModelGate.promise; return snap; }
        return JSON.stringify(stub.model);
      },
      async act(body) {
        stub.actCalls.push(body);
        if (stub.actGate) await stub.actGate.promise;
        if (stub.rejectActOnce) { const e = stub.rejectActOnce; stub.rejectActOnce = null; throw new Error(e); }
        stub.apply(body);
        return JSON.stringify(stub.model);
      },
      async docAct() { return JSON.stringify(stub.model); },
      async wtAct() { return JSON.stringify(stub.model); },
    },
  };
  return stub;
}

function depthOf(store) { return store.get().modules.find((m) => m.id === "m1").depth; }

async function loaded(stub, onError) {
  const store = createStore({ transport: stub.transport, onError: onError || (() => {}) });
  await store.refetch(false);   // hydrate cur from the server (no broadcast)
  return store;
}

// --- 1. optimistic write is visible immediately -----------------------------
test("setDepth updates the cache synchronously, before the server responds", async () => {
  const stub = makeStub(0.5);
  const store = await loaded(stub);
  store.setDepth("m1", 10);                 // 50 -> 60, optimistic
  assert.strictEqual(depthOf(store), 60);   // immediate — no await
  await flush();
  assert.strictEqual(stub.actCalls[0].action, "set_depth");
  assert.strictEqual(stub.actCalls[0].score, 0.6);   // de-normalized 60 -> 0.6 on the wire
  assert.strictEqual(depthOf(store), 60);            // server applied 0.6 -> stays 60
});

// --- 2. a rejected write rolls back to server truth -------------------------
test("a server-rejected write rolls the optimistic value back and reports the error", async () => {
  const errs = [];
  const stub = makeStub(0.5);
  const store = await loaded(stub, (e) => errs.push(e));
  stub.rejectActOnce = "duplicate id";
  store.setDepth("m1", 10);                 // optimistic 60
  assert.strictEqual(depthOf(store), 60);
  await flush();
  assert.strictEqual(depthOf(store), 50);   // rolled back to server truth
  assert.strictEqual(errs.length, 1);
  assert.match(errs[0].message, /duplicate id/);
});

// --- 3. pendingWrites gate: a poll cannot clobber an in-flight write ---------
test("a poll during an in-flight write does not clobber the optimistic value", async () => {
  const stub = makeStub(0.5);
  const store = await loaded(stub);
  stub.actGate = deferred();                // hold the write open
  store.setDepth("m1", 20);                 // optimistic 70; pendingWrites = 1
  assert.strictEqual(store.pending(), true);
  stub.model.modules[0].depth = 0.9;        // another writer moved the server to 90
  const changed = await store.refetch(true);
  assert.strictEqual(changed, false);       // refused: a write is in flight
  assert.strictEqual(depthOf(store), 70);   // optimistic value intact
  stub.actGate.resolve();                   // let the write finish
  await flush();
  assert.strictEqual(depthOf(store), 70);   // the write's own reconcile wins (0.7)
});

// --- 4. writeGen gate: a stale poll started before a newer write is discarded -
test("a poll whose snapshot predates a newer write is discarded, not applied", async () => {
  const stub = makeStub(0.5);
  const store = await loaded(stub);
  stub.getModelGate = deferred();           // the poll's getModel will return a stale snapshot (depth 0.5)
  const pollPromise = store.refetch(true);  // captures gen = writeGen now
  store.setDepth("m1", 5);                   // a newer write: optimistic 55, writeGen bumped
  await flush();                             // ...and it completes -> server 0.55 -> cur 55
  assert.strictEqual(depthOf(store), 55);
  stub.getModelGate.resolve();               // now the stale poll resolves (snapshot was 0.5)
  const changed = await pollPromise;
  assert.strictEqual(changed, false);        // discarded: writeGen advanced since the poll began
  assert.strictEqual(depthOf(store), 55);    // NOT reverted to 50
});

// --- 5. an idle poll/focus reconcile adopts server changes + broadcasts ------
test("an idle refetch adopts server changes and notifies subscribers", async () => {
  const stub = makeStub(0.5);
  const store = await loaded(stub);
  let events = 0;
  const off = store.subscribe(() => events++);
  stub.model.modules[0].depth = 0.8;         // another surface changed the server
  const changed = await store.refetch(true);
  assert.strictEqual(changed, true);
  assert.strictEqual(depthOf(store), 80);
  assert.strictEqual(events, 1);
  off();                                      // unsubscribe stops delivery
  stub.model.modules[0].depth = 0.3;
  await store.refetch(true);
  assert.strictEqual(events, 1);              // no further notification
  assert.strictEqual(depthOf(store), 30);     // cache still reconciled
});

// --- 6. a write's reconcile broadcasts once it lands ------------------------
test("a successful write broadcasts the reconciled model to subscribers", async () => {
  const stub = makeStub(0.5);
  const store = await loaded(stub);
  let events = 0;
  store.subscribe(() => events++);
  store.setDepth("m1", 10);
  await flush();
  assert.strictEqual(events, 1);              // reconcile after the act broadcast once
});

// --- 7. reload() force-adopts the current model and bumps the generation -----
test("reload() force-adopts and broadcasts even on a byte-identical model", async () => {
  const stub = makeStub(0.5);
  const store = await loaded(stub);
  let events = 0;
  store.subscribe(() => events++);
  await store.reload();                        // same bytes, but reload always broadcasts
  assert.strictEqual(events, 1);
  assert.strictEqual(depthOf(store), 50);
});

(async function run() {
  let passed = 0, failed = 0;
  for (const t of tests) {
    try { await t.fn(); passed++; console.log("  ok  " + t.name); }
    catch (e) { failed++; console.log("  ✗   " + t.name + "\n      " + (e && e.message || e)); }
  }
  console.log("\n" + passed + " passed" + (failed ? ", " + failed + " FAILED" : ""));
  process.exit(failed ? 1 : 0);
})();
