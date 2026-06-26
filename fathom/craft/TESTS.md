# Craft · Tests

The **craft** layer is the altitude *below* `LANGUAGE.md` and `MINIMALISM.md`: how to write the implementation **behind a seam** so it reads cleanly, not just so it's deep. This doc is the tests slice. Drawn from *Clean Code* ch. 9. Language-agnostic — xUnit, table tests, spec frameworks, hand-rolled harnesses alike.

Two of this chapter's lessons are **already load-bearing elsewhere in the suite** and are *not* re-stated as rules here — they're cited at their source:

- **The interface is the test surface.** Tests cross the same seam callers do; if a test must reach *past* the interface, the module is the wrong shape. This is a first-class principle in `LANGUAGE.md` and the rule `code` enforces while it works.
- **Replace, don't layer.** When a shallow cluster deepens, the unit tests on the absorbed pass-throughs become waste — delete them; assert at the new interface instead. This is the testing strategy in `../DEEPENING.md` and the migration `code` performs in §6.

*Clean Code* ch. 9 is the **source** of both. This doc records that, then adds what those two don't cover — how to keep the tests themselves clean — as a craft `rule`.

**Read by:** `code` (writing tests behind a fixed interface — the safety net in §4, the migration in §6), `review` (the craft pass), `design` (every interface it specifies *is* a test surface — §3 says so).

## Where this sits in the suite

- **Depth / seam** (`LANGUAGE.md`) decides *what the interface is* — and **the interface is the test surface**: tests assert across it, never behind it.
- **Deepening** (`../DEEPENING.md`) decides *how tests move when a module deepens* — replace the pass-through tests with interface tests; the interface is where coverage lives.
- **This doc** decides *how well the tests themselves read* — because a test suite that rots gets abandoned, and an abandoned suite is why code stops being changeable.

Tests are not second-class code that lives behind the seam — they sit *at* the seam, on the caller's side of it, exercising the interface. These rules are about the part `LANGUAGE.md` and `DEEPENING.md` leave open: the internal quality of the test code, so the surface that proves the module stays trustworthy and alive.

## The rules — each with its *why*

**Follow the three laws of TDD.** (1) Write no production code until you have a failing test that demands it. (2) Write no more of a test than is sufficient to fail — not compiling counts as failing. (3) Write no more production code than is sufficient to pass the failing test. *Why:* the laws lock test and code together in a tight cycle (tens of seconds), so the tests cover essentially all the production code and the code is shaped, from the first line, to be testable through its interface — which is the only place tests are allowed to reach.

**Keep tests as clean as production code.** Test code is not "throwaway" code — hold it to the same standard of clarity you hold the production code it guards. *Why:* dirty tests are *worse* than no tests, because they rot. As the production code changes, tangled tests get harder to change, then they get abandoned, then the code they protected can no longer be changed safely. The cleanliness of the tests is what decides whether they survive the next year of edits.

**Tests are what keep code changeable.** Treat the test suite as the thing that *enables* refactoring, not a tax on it. *Why:* tests pin observable behaviour, so you can improve the implementation behind the seam without fear — which is exactly the successive refinement the rest of craft depends on (`../DEEPENING.md`). No tests means every change is a risk, so changes stop; the code ossifies. Coverage at the interface is what buys the freedom to make modules deep and keep them clean.

**Build a domain-specific testing API so tests read clearly.** Don't write raw setup and assertions in every test — grow a small language of helpers (builders, custom assertions, a fluent setup) on top of the system, and write the tests *in that language*. *Why:* it lets each test say *what* it checks, not *how* it pokes the system; the messy detail of getting the system into a state and reading it back hides behind the helper, so the test stays at the level of the behaviour it describes. This is just **depth**, applied to tests: the testing API is a deep module the tests call.

```
// smell: the intent drowns in mechanism
state = new SystemState()
state.addController("hw"); state.setTemp("hw", 200); state.tick()
assert state.log().contains("HBchL"); assert state.cooler() == ON

// craft: a testing API carries the mechanism; the test reads as a claim
makeSystem("hw")
heatTo(200)
assertHardware("cooler on, blower on")
```

**One concept per test — and minimal assertions.** Each test exercises a single concept; keep the number of assertions low, ideally building toward one. *Why:* a test that checks several concepts fails ambiguously — you can't tell from the red which behaviour broke — and it can't be named precisely (its name becomes an `and`). One concept per test gives a precise name and a precise failure; minimal asserts keep each test's claim sharp.

**F.I.R.S.T. — the five properties of a trustworthy test.** *Why:* each letter removes a specific reason a suite stops getting run, and a suite that isn't run stops protecting anything:

- **Fast.** Slow tests get run less; run less, they catch less, and rot sets in. Keep them quick enough to run constantly.
- **Independent.** No test depends on another's state or ordering. *Why:* dependence cascades one failure into many and hides the real cause; independent tests can run in any order and each failure points at one thing.
- **Repeatable.** Same result in every environment — laptop, CI, offline. *Why:* a test that only passes "sometimes" or "only here" is one you'll learn to ignore, and an ignored failing test is worthless.
- **Self-validating.** The test decides pass or fail by itself, with a boolean outcome — no eyeballing a log. *Why:* if judging the result is manual, it won't get judged; the test must assert, not report.
- **Timely.** Write the test just *before* the production code it covers. *Why:* written after, the code tends to come out shaped so it's hard to test through its interface — and you discover that exactly when it's most expensive to fix.

## How you actually get there

The testing API is grown, not designed up front. Write the first tests with raw mechanism, watch the same setup-and-readback appear in the third and fourth test, then extract it into a helper and rewrite the earlier tests through it — successive refinement (`../DEEPENING.md`) applied to the suite. Do the same with assertions: when you see the same three checks together, fold them into one domain assertion (`assertHardware(...)`). The suite gets cleaner as it grows, the same way production code does — and that is what keeps it alive long enough to matter.

## Checklist (the `review` craft pass runs this)

- [ ] New production code arrived test-first (the three laws): a failing test demanded each piece
- [ ] Tests are as clean as production code — no tangle that will rot and be abandoned
- [ ] Tests assert **across the interface**, never reaching past the seam (see `LANGUAGE.md`)
- [ ] Pass-through tests were **deleted**, not layered under, when the module deepened (see `../DEEPENING.md`)
- [ ] A domain-specific testing API carries the mechanism; tests read as claims, not pokes
- [ ] One concept per test; assertions minimal (building toward one)
- [ ] F.I.R.S.T.: fast, independent, repeatable, self-validating, timely

## Signals this feeds (spine)

`untested-interface` fires on a **deep module whose interface coverage is thin** — the more behaviour a module hides behind its seam, the more its interface is the only thing standing between that behaviour and a silent regression, so a deep module with low coverage at its interface is the suite's sharpest test gap. Measured by `craft_ingest` (depth × interface-coverage) and surfaced by `archmap_scan_signals(map, family="craft")`; it is the same target `code`'s **test-first** mode (its §1 mode c) takes worst-first.

The *subjective* parts above stay as this `rule` the skills apply — they are not auto-measured: whether a test really checks *one concept*, whether the testing API reads as a claim, and whether the tests are clean enough to survive are judgement calls `code` and `review` make against this doc. A scanner can count coverage at an interface; it cannot tell a clean test from a tangled one.

## References

- `reference/tests.md` — the deep dive: the three laws worked through a red-green-refactor cycle, building a testing API from raw tests, the "one concept" split, and F.I.R.S.T. failure modes.
- Source chapter (original Java): *Clean Code* ch. 9, "Unit Tests" — also the **source** of *the interface is the test surface* (`LANGUAGE.md`) and *replace, don't layer* (`../DEEPENING.md`, `code` §6).
- Pairs with `../DEEPENING.md` (where tests live when a module deepens), `ERRORS.md` (write the failure scope first, like a test), and `FUNCTIONS.md` (clean tests follow the same craft as clean functions).
