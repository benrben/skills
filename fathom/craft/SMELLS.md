# Craft · Smells

The **craft** layer is the altitude *below* `LANGUAGE.md` and `MINIMALISM.md`: how the implementation behind a seam reads. **Smells** is the catalog the other craft docs draw from — the generalized list of "things that smell bad when you read code," and the **source list the `review` craft pass walks** over the modules a diff touched. Drawn from *Clean Code* ch. 17. Language-agnostic — the Java-specific J-items are folded in as "language-specific pitfalls," and every heuristic is restated so it applies to any language.

**Read by:** `review` (the primary reader — this *is* the craft pass's checklist), `code` (as a do-not-do list while building behind a fixed seam — pairs with `MINIMALISM.md`), `design` (the structural smells, which become deepening candidates).

## Where this sits in the suite

- The other craft docs say *do this*; **Smells is the negative image** — *don't do this* — over the same ground, indexed so a reviewer can walk it top to bottom.
- Every heuristic is tagged with its **home**, which decides what Fathom does with it:
  - **[signal]** — *measurable.* A parser can count it, so it fires via `archmap_scan_signals` (e.g. duplication, dead code, magic numbers, too-many-args). The reviewer confirms; the spine surfaces.
  - **[rule]** — *subjective convention.* Taste a parser can't judge (a good name, a useful comment, consistent style). Lives as a per-map **`rule` doc** that `code` and `review` read; checked by a human. Fathom never fakes taste as a metric.
  - **[design]** — *structural.* The fix moves the seam (wrong level of abstraction, feature envy, transitive navigation). Becomes a **deepening candidate** for `design` (`DEEPENING.md` / `INTERFACE-DESIGN.md`), not a local edit. Where a smell meets architecture, the architecture word wins (`craft/README.md`).

A smell's tag is *where it goes*, not how bad it is. A [design] smell isn't worse than a [signal] one — it just can't be fixed without re-cutting a boundary, so it travels to `design` instead of being patched in place.

## The core — the universal heuristics worth memorizing

The full annotated catalog (every C/E/F/G/N/T/J item, generalized + tagged) is in `reference/smells.md`. These are the ones that bite in every language and pay back most when caught early:

- **G5 · Duplication.** The single most important rule in the book — every duplicated clump, repeated `if/else`/`switch` chain, or parallel algorithm is a missed abstraction. Fold it into one place. **[signal]** → `duplication`.
- **G30 / F-family · Do one thing, few arguments, no flags, no output args.** A function with sections, or with a boolean that switches its behaviour, or that returns through a mutated argument, is doing several things. **[signal]** for the countable parts (`too-many-args`, function length), **[rule]** for "is this really one thing?" (see `FUNCTIONS.md`).
- **G25 · Magic numbers / unexplained literals.** A raw value that isn't self-describing (a number, a sentinel string) must hide behind a named constant. **[signal]** → `magic-numbers`. (Truly universal literals like 0, 1, or a well-known mathematical constant are exempt.)
- **G9 / F4 / C5 · Dead things.** Code that never runs, functions never called, and commented-out code are all rot — delete them; version control remembers. **[signal]** → `dead-code`, `dead-function`, `commented-out`.
- **G6 · Code at the wrong level of abstraction.** High-level policy and low-level detail mixed in one place; a feature that belongs in a derivative leaking into the base. **[design]** — the fix separates levels, which moves the seam.
- **G14 · Feature envy.** A method more interested in another object's data than its own — reaching through accessors to compute what that object should compute itself. **[design]** — the behaviour wants to move to where the data lives.
- **G34 · Functions descend only one level of abstraction.** Every statement in a function sits one level below the function's name; mixing levels (policy + raw string surgery) trips the reader. **[design]** when the fix extracts a new module; otherwise the `FUNCTIONS.md` stepdown **[rule]**.
- **G36 · Transitive navigation (Law of Demeter).** `a.getB().getC().doThing()` — a module that knows the whole navigation map, not just its neighbours. **[design]** → this is the **`leaky-seam`** signal's structural twin (`STRUCTURE.md`): a `leaksTo` edge, fixed by deepening the intermediate module.
- **G8 · Too much information (wide interface).** A module exposing many functions/variables forces high coupling; hide everything that isn't the interface. **[design]** — the inverse of **depth**.
- **N1 / N7 · Descriptive names that describe side effects.** Names are ~90% of readability; a name that hides a side effect (a "get" that also creates) is a lie. **[rule]** (see `NAMING.md`).
- **C2 / C3 · Obsolete and redundant comments.** A comment that has drifted from the code, or that merely restates it, is worse than none. **[rule]** (see `COMMENTS.md`).
- **T1 / T9 · Insufficient and slow tests.** A suite that doesn't test everything that could break, or that's too slow to run, fails the first rule of simple design. **[signal]** for the measurable part (`untested-interface` / coverage), **[rule]** for "enough?" (see `TESTS.md`).

## The full catalog, by category (summary)

The complete, individually-annotated list lives in `reference/smells.md`. The categories and their character:

- **Comments (C1–C5)** — information in the wrong system, comments gone stale or redundant, poorly written, or commented-out code. Mostly **[rule]**; C5 commented-out is **[signal]**.
- **Environment (E1–E2)** — build and test must each be a single trivial command. **[rule]** (a tooling/process convention, not a code metric).
- **Functions (F1–F4)** — too many arguments, output arguments, flag arguments, dead functions. The countable ones (F1 arg count, F4 dead function) are **[signal]**; output/flag args are **[rule]** pointing at `FUNCTIONS.md`.
- **General (G1–G36)** — the large heart of the catalog: duplication, dead code, wrong abstraction level, feature envy, magic numbers, hidden temporal couplings, transitive navigation, and more. A mix of all three tags — this is where most **[signal]** and most **[design]** smells live.
- **Names (N1–N7)** — descriptive, right-level, standard, unambiguous, scope-scaled, un-encoded names that describe side effects. Almost entirely **[rule]** → `NAMING.md` (naming quality is taste; Fathom does not fake it as a metric).
- **Tests (T1–T9)** — sufficient, fast, boundary-covering, pattern-revealing tests; use a coverage tool. Coverage is **[signal]**; "enough / well-chosen" is **[rule]** → `TESTS.md`.
- **Language-specific pitfalls (the J-items)** — the original's Java items (wildcard imports, don't-inherit-constants, enums-over-int-constants) generalized to "know your language's scoping and idiom traps." **[rule]** — each language has its own list; the *general* lesson is "don't abuse the language's scoping to smuggle state."

## The signal / rule / design split (where each smell goes)

The same split, read as three buckets — this is what `review` uses to route a finding:

**[signal] — measured, surfaced by `archmap_scan_signals`:**
G5 → `duplication` · G9 → `dead-code` · F4 → `dead-function` · C5 → `commented-out` · G25 → `magic-numbers` · F1 → `too-many-args` · (function length → `long-function`, deep nesting → `deep-nesting`, from `FUNCTIONS.md`) · (insufficient tests → `untested-interface` / coverage, from `TESTS.md`). A measured smell still wants a human to confirm it's worth fixing — the count is the *prompt*, not the verdict.

**[rule] — subjective convention, a per-map `rule` doc, checked by a human:**
all of Names (N1–N7); Comments quality (C1–C4); Environment (E1–E2); Follow-standard-conventions (G24); the *judgement* halves of the function rules (is this one thing? is this name honest?). Taste enforced as guidance, never as a fake metric.

**[design] — structural, a deepening candidate for `design`:**
G6 (wrong level of abstraction) · G14 (feature envy) · G34 (functions descend one level) · G36 (transitive navigation / Demeter) · G8 (too-wide interface) · G7 (base depends on derivative) · G17/G13 (misplaced responsibility / artificial coupling). Each is fixed by moving the seam — so it goes to `DEEPENING.md` / `INTERFACE-DESIGN.md`, and where it meets an architecture term, that term wins (a "god function" is a `design` candidate, not merely a `long-function` count).

## How the `review` craft pass walks this

For each module a diff touched: read the **core** list above first (it catches the costly, universal ones), then the relevant category in `reference/smells.md`. Route each finding by its tag — **[signal]** confirm against the spine's count, **[rule]** check against the project's `rule` doc, **[design]** raise as a deepening candidate rather than patching locally. A clean pass means no unrouted findings, not zero findings — a [design] smell handed to `design` is *resolved*, not ignored.

## Checklist (the `review` craft pass runs this)

- [ ] No duplication — identical clumps, repeated condition-chains, parallel algorithms folded into one place (G5)
- [ ] No dead code, dead functions, or commented-out code — deleted, not kept "just in case" (G9, F4, C5)
- [ ] No unexplained literals — magic numbers/strings behind named constants (G25)
- [ ] Functions do one thing, few args, no flag or output arguments (F1–F3, G30)
- [ ] Levels of abstraction not mixed; nothing leaking from base into derivative or vice versa (G6, G34, G7)
- [ ] No feature envy, no transitive navigation / train wrecks (G14, G36)
- [ ] Interfaces narrow — information hidden, coupling low (G8)
- [ ] Names descriptive, unambiguous, scope-scaled, honest about side effects (N1–N7)
- [ ] Comments carry only what code can't; none obsolete, redundant, or commented-out (C1–C5)
- [ ] Tests sufficient, fast, and cover boundaries; coverage checked (T1–T9)
- [ ] Each finding routed by tag: [signal] confirmed, [rule] checked, [design] raised to `design`

## Signals this feeds (spine)

This doc is the *origin* of the craft signal family: G5 → `duplication`, G9 → `dead-code`, F4 → `dead-function`, C5 → `commented-out`, G25 → `magic-numbers`, F1 → `too-many-args`, plus `long-function`/`deep-nesting` from `FUNCTIONS.md` and the coverage signals from `TESTS.md` — all measured by `craft_ingest` and surfaced by `archmap_scan_signals(map, family="craft")`. The structural smells (G6, G14, G34, G36, G8, G7, G17) carry no count — they surface as **deepening candidates** for `design`, and where they touch a boundary they meet the architecture signals `large-class` and `leaky-seam` (`STRUCTURE.md`). The **[rule]** smells (all of Names, Comments quality, Environment, conventions) feed **no signal at all** — they are enforced by the `review` craft pass against the project's `rule` docs, by a human, because measuring them would be faking taste.

## References

- `reference/smells.md` — the full catalog: every C/E/F/G/N/T/J heuristic, each with a one-line generalized statement, its **[signal]/[rule]/[design]** tag, and a pointer to the craft doc that owns the *do-this* side.
- Source chapter (original Java): *Clean Code* ch. 17, "Smells and Heuristics" (cross-referenced in Appendix C).
- The *do-this* counterparts: `FUNCTIONS.md` (F/G30/G34), `NAMING.md` (all N), `COMMENTS.md` (all C), `TESTS.md` (all T), `STRUCTURE.md` (G6/G8/G14/G36 and the structural [design] smells), `ERRORS.md` (error-handling smells). The measured thresholds live with each owning doc's "Signals this feeds" section.
