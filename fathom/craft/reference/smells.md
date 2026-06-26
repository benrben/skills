# Craft · Smells — deep reference

The full catalog behind `../SMELLS.md`. Read on demand. Every heuristic from *Clean Code* ch. 17, **generalized to any language**, each with: a one-line statement, its **home tag** — **[signal]** (measured, fires via `archmap_scan_signals`), **[rule]** (subjective convention, a per-map `rule` doc, human-checked), or **[design]** (structural, a deepening candidate for `design`) — and a pointer to the craft doc that owns its *do-this* side. The Java-specific J-items are kept as "language-specific pitfalls." Original examples (a Java stack, a payroll calculator, a bowling scorer, a SQL builder) are in the source chapter; statements here are language-neutral.

Tag legend: **[signal]** → surfaced by the spine; **[rule]** → enforced by the `review` craft pass against a `rule` doc; **[design]** → raised to `design` (`DEEPENING.md` / `INTERFACE-DESIGN.md`) because the fix moves the seam.

---

## Comments (C1–C5) — owns: `COMMENTS.md`

- **C1 · Inappropriate information.** A comment holding what belongs in another system — version-control history, issue-tracker metadata, authorship. Keep comments to technical notes about the code. **[rule]**
- **C2 · Obsolete comment.** A comment gone old, irrelevant, or wrong; it drifts from the code and misleads. Update or delete on sight. **[rule]**
- **C3 · Redundant comment.** A comment that restates what the code already says (`i++ // increment i`, a doc-block echoing the signature). Comments should say what code can't. **[rule]**
- **C4 · Poorly written comment.** If it's worth writing, write it well — brief, correct, no rambling, no stating the obvious. **[rule]**
- **C5 · Commented-out code.** Stretches of code left commented "in case"; nobody dares delete it and it rots. Delete it — version control remembers. **[signal]** → `commented-out` (a parser can detect commented-out code blocks).

## Environment (E1–E2) — owns: `TESTS.md` (E2) / project `runbook`

- **E1 · Build requires more than one step.** Building should be one trivial command, not a hunt for scattered artifacts and arcane scripts. **[rule]** (a process/tooling convention).
- **E2 · Tests require more than one step.** Running the whole suite should be one command (ideally one button). **[rule]** — supports simple-design rule 1 (`STRUCTURE.md`).

## Functions (F1–F4) — owns: `FUNCTIONS.md`

- **F1 · Too many arguments.** Zero is best, then one, two; three is questionable; more is avoided. Wrap longer lists in an argument object. **[signal]** → `too-many-args` (≥ 4 parameters).
- **F2 · Output arguments.** Returning a result by mutating a passed-in argument; readers expect args in, results back. Mutate the object the method is called on, or return a value. **[rule]** → `FUNCTIONS.md`.
- **F3 · Flag arguments.** A boolean that makes the function behave two ways — a loud admission it does more than one thing. Split into two named functions. **[rule]** → `FUNCTIONS.md`.
- **F4 · Dead function.** A method never called. Delete it; version control remembers. **[signal]** → `dead-function` (a parser can find uncalled functions).

## General (G1–G36) — owns: mixed (`FUNCTIONS.md`, `STRUCTURE.md`, project `rule`)

- **G1 · Multiple languages in one source file.** Mixing languages (markup, query strings, templating, prose) in one file is confusing; minimize the number and extent of extra languages. **[rule]**
- **G2 · Obvious behavior unimplemented.** A function that doesn't do what its name leads any reader to expect (least surprise) destroys trust in names. **[rule]**
- **G3 · Incorrect behavior at the boundaries.** Corner and boundary cases handled by intuition instead of a test. Find every boundary condition and test it. **[rule]** → `TESTS.md` (pairs with T5).
- **G4 · Overridden safeties.** Turning off failing tests, warnings, or checks to make progress — borrowing against a debt that comes due in debugging. **[rule]**
- **G5 · Duplication.** *The most important rule.* Identical clumps, repeated `if/else`/`switch` chains testing the same conditions, and parallel algorithms are all missed abstractions — fold each into one place (a function, a class, or polymorphism). **[signal]** → `duplication`.
- **G6 · Code at wrong level of abstraction.** High-level concepts and low-level detail mixed in one container; a detail that belongs in a derivative present in the base. The separation must be complete. **[design]** — separating levels moves the seam.
- **G7 · Base class depending on its derivatives.** A base mentioning the names of its subtypes; in general the base should know nothing of its derivatives, so they can vary independently. **[design]** — a coupling fixed by re-cutting the inheritance seam.
- **G8 · Too much information.** A wide interface exposing many functions/variables → high coupling. Hide data, utilities, constants; keep the interface narrow. **[design]** — the inverse of **depth** (`LANGUAGE.md`).
- **G9 · Dead code.** Code that never executes — an impossible `if` branch, an unreachable `catch`, an uncalled utility. It rots out of step with the rest. Delete it. **[signal]** → `dead-code`.
- **G10 · Vertical separation.** Variables and private functions defined far from their first use; declare locals just above use, private functions just below. **[rule]** (a formatting/locality convention).
- **G11 · Inconsistency.** Doing similar things different ways; once a convention is chosen, follow it everywhere (least surprise). **[rule]**
- **G12 · Clutter.** Empty default constructors, unused variables, meaningless comments — artifacts that add nothing. Remove them. **[rule]** (overlaps the dead-* signals when countable).
- **G13 · Artificial coupling.** Two things that don't depend on each other bound together — a general utility parked inside a specific class for convenience. Put things where they belong. **[design]** — misplacement fixed by moving the seam.
- **G14 · Feature envy.** A method more interested in another object's data than its own, reaching through that object's accessors to do work the object should do. Move the behaviour to the data. **[design]** (a known necessary-evil exception when moving it would couple a class to a foreign concern, e.g. a report's format).
- **G15 · Selector arguments.** A dangling argument (boolean, enum, int) that selects behaviour inside the function — a lazy substitute for splitting into named functions. **[rule]** → `FUNCTIONS.md` (generalizes F3).
- **G16 · Obscured intent.** Run-on expressions, dense one-liners, encoded names, magic numbers — code that hides what the author meant. Make intent visible. **[rule]** (overlaps G25 where literals are countable).
- **G17 · Misplaced responsibility.** Code placed where it was convenient to write, not where a reader expects it (least surprise) — a total computed by the report instead of where the data accrues. **[design]** — fixed by moving responsibility across the seam.
- **G18 · Inappropriate static.** A function made static that may need to behave polymorphically later; prefer non-static unless there's no chance of polymorphism. **[rule]** → `STRUCTURE.md` (a structural-leaning convention).
- **G19 · Use explanatory variables.** Break a calculation into intermediate values with meaningful names; an opaque expression becomes transparent. **[rule]** → `NAMING.md`.
- **G20 · Function names should say what they do.** If you must read the implementation to know what a call does, the name failed (`date.add(5)` — days? weeks? mutates?). **[rule]** → `NAMING.md`.
- **G21 · Understand the algorithm.** Don't stop at "passes the tests" via piled-up flags; know *why* the solution is correct. Often the way to know is to refactor it clean. **[rule]**
- **G22 · Make logical dependencies physical.** A module that *assumes* a fact about another (a hard-coded page size it expects the formatter to honour) should *ask* for it instead. **[design]** — a hidden dependency made explicit across the seam.
- **G23 · Prefer polymorphism to if/else or switch/case.** Every type-switch is suspect; cases where functions vary more than types are rare. The ONE-SWITCH rule: at most one switch per selection, and it creates the polymorphic objects. **[design]** → `STRUCTURE.md` / `FUNCTIONS.md`.
- **G24 · Follow standard conventions.** The team follows one coding standard, evidenced by the code itself. **[rule]**
- **G25 · Replace magic numbers with named constants.** Any token whose value isn't self-describing — a raw number, a sentinel string — hides behind a named constant. (Self-evident universals like a well-known mathematical constant or `8` hours can stay raw.) **[signal]** → `magic-numbers`.
- **G26 · Be precise.** Don't paper over decisions — check for the null you might get, the second matching record, the rounding on money, the concurrent update. Ambiguity is laziness. **[rule]**
- **G27 · Structure over convention.** Enforce a design decision with structure (an abstract method the compiler demands) over a naming convention (which nothing forces). **[design]** → `STRUCTURE.md`.
- **G28 · Encapsulate conditionals.** Extract a named function for a boolean test — `if (shouldBeDeleted(timer))` over a raw compound condition. **[rule]** → `FUNCTIONS.md`.
- **G29 · Avoid negative conditionals.** Positives read easier than negatives — `if (shouldCompact())` over `if (!shouldNotCompact())`. **[rule]**
- **G30 · Functions should do one thing.** A function with multiple sections doing a series of operations should become several functions, each doing one thing. **[rule]** → `FUNCTIONS.md` (the *judgement*; the countable proxies are `long-function` / nesting signals).
- **G31 · Hidden temporal couplings.** An order dependency between calls that the code doesn't enforce; structure arguments so the call order is the only one possible (each produces what the next needs). **[rule]** → `FUNCTIONS.md` (no hidden side effects).
- **G32 · Don't be arbitrary.** Structure code for a reason and let the structure communicate it; an arbitrary structure invites others to change it. **[rule]**
- **G33 · Encapsulate boundary conditions.** Put a `+1`/`-1` boundary computation in one named variable (`nextLevel`) instead of scattering it. **[rule]**
- **G34 · Functions should descend only one level of abstraction.** Every statement one level below the function's name; mixing the notion of a thing with the syntax of building it trips the reader. **[design]** when the fix extracts a new module; the stepdown **[rule]** otherwise → `FUNCTIONS.md` / `STRUCTURE.md`.
- **G35 · Keep configurable data at high levels.** A default/config value known at a high level shouldn't be buried in a low-level function — pass it down from the top. **[rule]** → `STRUCTURE.md`.
- **G36 · Avoid transitive navigation.** A module should talk only to immediate collaborators, not roam the object graph (`a.getB().getC().doThing()`) — the Law of Demeter / "writing shy code." Too many such chains make the architecture rigid. **[design]** → `STRUCTURE.md`; this is the **`leaky-seam`** signal's structural twin (a `leaksTo` edge).

## Names (N1–N7) — owns: `NAMING.md`

- **N1 · Choose descriptive names.** Names are ~90% of readability; choose them carefully and re-evaluate as meanings drift. **[rule]**
- **N2 · Names at the right level of abstraction.** Name for the concept, not the implementation (`connectionLocator`, not `phoneNumber`, when the medium may vary). **[rule]**
- **N3 · Use standard nomenclature.** Lean on existing convention — pattern names, the project's ubiquitous language. **[rule]** (domain words → the `glossary` doc).
- **N4 · Unambiguous names.** A name should make the workings clear; `renamePageAndOptionallyAllReferences` over a vague `doRename`. **[rule]**
- **N5 · Long names for long scopes.** Name length tracks scope — `i` is fine in a five-line loop, not across a class. **[rule]**
- **N6 · Avoid encodings.** No type/scope prefixes (Hungarian, `m_`, interface `I`-tags); modern tooling makes them dead weight and they lie when types change. **[rule]**
- **N7 · Names describe side effects.** A name must cover everything the thing does; a "get" that also creates should say so (`createOrReturn…`). **[rule]**

> All of Names is **[rule]** → `NAMING.md`. A parser can flag a one-letter name in a wide scope, but cannot tell a *good* name from `Manager` — so naming feeds **no `naming` signal**; adding one would fake taste.

## Tests (T1–T9) — owns: `TESTS.md`

- **T1 · Insufficient tests.** "Seems like enough" is the wrong metric; test everything that could break. **[signal]**-adjacent → coverage / `untested-interface` (the measurable proxy; "enough?" stays **[rule]**).
- **T2 · Use a coverage tool.** Coverage reports show the gaps; use one. **[signal]** → coverage is a measured fact.
- **T3 · Don't skip trivial tests.** They're cheap and their documentary value exceeds their cost. **[rule]**
- **T4 · An ignored test is a question about an ambiguity.** Express uncertainty about a requirement as an ignored/commented test, not a missing one. **[rule]**
- **T5 · Test boundary conditions.** Take special care at the edges — the middle is usually right, the boundaries aren't. **[rule]** (pairs with G3).
- **T6 · Exhaustively test near bugs.** Bugs congregate; when you find one, test its neighbourhood hard. **[rule]**
- **T7 · Patterns of failure are revealing.** Complete, ordered test cases let the *pattern* of red/green diagnose the cause. **[rule]**
- **T8 · Test coverage patterns can be revealing.** What the passing tests do/don't execute hints at why the failing ones fail. **[rule]**
- **T9 · Tests should be fast.** A slow test is a test that won't get run, and gets dropped under pressure. **[signal]**-adjacent (test runtime is measurable) / **[rule]** → `TESTS.md`.

## Language-specific pitfalls (the J-items) — owns: project `rule`

The original's Java items, generalized to **"know your language's scoping and idiom traps."** Each language has its own list; the universal lesson is *don't abuse the language's scoping rules to smuggle state, and prefer the language's purpose-built construct over an older trick.*

- **J1 · Avoid long import/dependency lists via wildcards (Java).** General: keep a module's dependency declarations a concise statement of what it collaborates with, not 80 lines of noise. **[rule]**
- **J2 · Don't inherit constants (Java).** General: don't use inheritance to smuggle constants into scope and cheat the language's scoping rules; import/reference them explicitly. **[rule]** (relates to G6/G17 — misplaced shared state).
- **J3 · Constants vs enums (Java).** General: prefer the language's named-enumeration construct over bare integer constants whose meaning can be lost. **[rule]**

---

## How `review` routes a finding (recap)

For each touched module: scan the **core** list in `../SMELLS.md` first (the costly universals), then the relevant category above. Route by tag — **[signal]** confirm against the spine's count and decide if it's worth fixing; **[rule]** check against the project's `rule` doc; **[design]** raise as a deepening candidate rather than patching locally. A clean pass = every finding routed, not zero findings.

## See also

- `../SMELLS.md` — the categories, the memorizable core, and the signal/rule/design split (the `review` craft pass).
- `../FUNCTIONS.md` · `../NAMING.md` · `../COMMENTS.md` · `../TESTS.md` · `../STRUCTURE.md` · `../ERRORS.md` — the *do-this* counterparts; each owns the measured thresholds for its smells in its "Signals this feeds" section.
- `../STRUCTURE.md` — where the [design] smells (G6, G8, G14, G34, G36, G7, G17) become deepening candidates and meet `large-class` / `leaky-seam`.
- Source: *Clean Code* ch. 17 "Smells and Heuristics," Appendix C (cross-references).
