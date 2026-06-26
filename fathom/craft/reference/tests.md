# Craft · Tests — deep reference

The depth behind `../TESTS.md`. Read on demand. All examples are neutral pseudocode; the originals (Java) are in *Clean Code* ch. 9.

Two of this chapter's ideas live elsewhere in the suite and are only cited here, not re-derived: **the interface is the test surface** (`../LANGUAGE.md`) and **replace, don't layer** (`../DEEPENING.md`, `code` §6). This reference deepens the rest — the laws, clean test code, the testing API, one-concept, and F.I.R.S.T.

## The three laws, as a cycle

The laws aren't three separate rules; they describe one loop you ride continuously:

```
loop:
    write just enough of a test to fail        // law 2 — not compiling is failing
    (production code won't compile / test red)  // law 1 — you may now write production code
    write just enough production code to pass    // law 3 — no more than that
    refactor freely under the green tests        // tests pin behaviour; clean up
```

A consequence worth stating: because no production line is written without a failing test demanding it, the suite ends up exercising **essentially all** the production code, and every line of that code was shaped — at birth — to be reachable *through its interface*, since the test could only ever assert there. Test-first isn't only about coverage; it's what forces testable-through-the-seam shape from the first line. (When this shape *can't* be achieved — the test wants to reach behind the seam — that's the signal in `../LANGUAGE.md`: the module is the wrong shape.)

## Clean tests, and why dirty ones are worse than none

The thing that makes tests valuable is also fragile: they only help if they keep getting run and keep getting maintained. Dirty tests decay on a predictable path:

```
tests grow tangled
  → each production change is harder to update the tests for
    → updating tests costs more than the change itself
      → tests get skipped, then deleted
        → the code they protected can no longer be changed safely
          → the code rots
```

So the cleanliness of the test code is not cosmetic — it's what determines whether the suite survives, and the surviving suite is the only thing that keeps the production code changeable. Hold tests to the **same** standard as production code: readable names, no duplication, one level of abstraction, small focused cases. The craft in `../FUNCTIONS.md` and `../ERRORS.md` applies to test code unchanged.

## Build a domain-specific testing API

The single highest-leverage move in a test suite is to stop writing raw mechanism in every test and grow a small **testing language** on top of the system. Watch the duplication, then extract it.

```
// stage 1 — raw mechanism, intent buried
state = new ControllerState()
state.add("hw"); state.heater("hw", true); state.fan("hw", true)
state.advance(); state.advance()
assert state.readLog().endsWith("HBchl"); assert state.coolerState() == false

// stage 2 — the same setup-and-readback appears a third time; extract it
function makeSystem(name): ...        // build + register
function heatTo(temp): ...            // drive to a state
function assertHardware(spec): ...    // read back + assert, in domain words

// stage 3 — every test now reads as a claim about behaviour
makeSystem("hw")
heatTo(200)
assertHardware("heater on, blower on, cooler off")
```

The testing API is itself a **deep module**: a lot of poking-the-system behaviour behind a tiny, expressive interface the tests call. It is built the way all deep modules are — not designed up front, but grown by successive refinement (`../DEEPENING.md`) as duplication reveals where the helpers belong. A test written in this language says *what* it verifies; the *how* lives behind the seam, exactly where complexity should sit.

## One concept per test — split the multi-concept test

A test that verifies several concepts fails ambiguously and can't be named without an `and`. Split by concept:

```
// smell: three concepts, one test — which one broke when it goes red?
function testCalendar():
    assert addDays(may31, 1)   == jun1     // month rollover
    assert addDays(jun1, -1)   == may31    // negative deltas
    assert addDays(feb28_2020, 1) == feb29 // leap year

// craft: one concept each — precise name, precise failure
function testAddingDaysRollsOverMonthEnd(): assert addDays(may31, 1) == jun1
function testAddingNegativeDaysGoesBackward(): assert addDays(jun1, -1) == may31
function testAddingDaysHandlesLeapDay(): assert addDays(feb28_2020, 1) == feb29
```

"One concept" is the test-side cousin of *do one thing* (`../FUNCTIONS.md`): the unit you can name without conjunctions. Keep assertions minimal within each — ideally building toward a single assertion (a domain assertion like `assertHardware(...)` can fold several raw checks into that one claim without checking several *concepts*).

## F.I.R.S.T. — each property is a defence against a dead suite

Read each letter as removing a specific way suites stop getting run:

- **Fast** — slow suites get run rarely; run rarely, they catch regressions late and rot quietly. Keep them quick enough to run on every change. (A test bound to real I/O is usually the cause — inject the dependency as a port and use a fast adapter; see `../DEEPENING.md` categories 3 & 4.)
- **Independent** — no shared mutable state, no ordering dependence. A test that relies on a predecessor cascades one real failure into a wall of red and hides the cause; an independent test fails alone and points at one thing. Each must set up its own world and tear it down.
- **Repeatable** — same verdict on a laptop, in CI, on a plane with no network. A test that passes "only here" or "only sometimes" trains the team to ignore red — and an ignored failing test protects nothing. Non-determinism (clock, network, random) is the usual culprit; pin it.
- **Self-validating** — the test ends in a boolean pass/fail it computes itself; no reading a log to decide. If judging the outcome is manual, it won't get judged. Assert, don't report.
- **Timely** — write the test just *before* the code it covers, not after. Written after, the production code tends to come out shaped so testing through its interface is awkward — and you find out at the most expensive moment. Timely tests keep the seam testable by construction.

## What this reference deliberately does not re-derive

- **The interface is the test surface** — a test that reaches past the seam means the module is the wrong shape. Source: *Clean Code* ch. 9; lives as a principle in `../LANGUAGE.md` and a rule `code` enforces.
- **Replace, don't layer** — when a cluster deepens, delete the pass-through tests and assert at the new interface. Source: *Clean Code* ch. 9; lives as the testing strategy in `../DEEPENING.md` and the migration `code` runs in §6.

Both are *applications* of clean testing to Fathom's module model; the craft this doc adds (laws, clean tests, testing API, one-concept, F.I.R.S.T.) is what makes the tests at that surface worth keeping.

## See also

- `../TESTS.md` — the rules + checklist (the `review` craft pass).
- `../LANGUAGE.md` — *the interface is the test surface*: where tests are allowed to assert.
- `../DEEPENING.md` — where tests move when a module deepens; the port/adapter that makes a slow test fast.
- `../FUNCTIONS.md`, `../ERRORS.md` — the craft that clean test code follows unchanged.
