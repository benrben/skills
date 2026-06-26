# Craft · Functions

The **craft** layer is the altitude *below* `LANGUAGE.md` and `MINIMALISM.md`: how to write the implementation **behind a seam** so it reads cleanly, not just so it's deep. Drawn from *Clean Code* ch. 3. Language-agnostic — methods, procedures, subroutines, free functions alike.

**Read by:** `code` (writing behind a fixed interface — pairs with `MINIMALISM.md`), `review` (the craft pass), `design` (when a function is so large it's really a missing module).

## Where this sits in the suite

- **Depth / seam** (`LANGUAGE.md`) decides *what the interface is*.
- **Minimalism** (`MINIMALISM.md`) decides *how little* implementation sits behind it.
- **This doc** decides *how well* that implementation reads.

A function is implementation. These rules never widen or collapse the seam — they make what's already behind it legible. When a function can't be cleaned without changing the interface, that's not a craft fix; hand it to `design`.

## The rules — each with its *why*

**Small.** Functions should be small; then smaller. Rarely over ~20 lines; blocks inside `if`/`else`/`while` are about one line — usually a call to a well-named function, so nesting stays one or two levels deep. *Why:* a small function can be named, read, and verified at a glance, and it lets the whole file be read top-to-bottom.

**Do one thing.** A function should do one thing, do it well, do only that. The test: you cannot extract another function from it with a name that isn't just a restatement of its code. *Why:* "sections" inside a function (a setup part, a loop part, a formatting part) are the smell that it's doing several things — and several things can't be reused or tested apart.

**One level of abstraction per function.** Don't mix high-level policy (`addFooter(report)`) with low-level detail (appending characters to a buffer). *Why:* mixing levels forces the reader to constantly change gears and hides what's essential behind what's incidental.

**Read top-to-bottom — the Stepdown Rule.** Order functions so each is followed by those one level of abstraction below it; the program reads as a descending narrative. *Why:* you can read it like prose — "to do X we do A then B" — instead of hunting.

**Bury switch/long-if behind polymorphism.** A `switch` (or long `if/else` chain) inherently does N things. Tolerate one only when it *creates* polymorphic objects and is hidden behind an interface (an abstract factory) so the rest of the system never repeats it. *Why:* an unburied type-switch reappears at every call site; polymorphism pays the dispatch once.

**Use descriptive names.** Long, clear names beat short cryptic ones and beat comments; rename freely until the name fits, and keep the vocabulary consistent across the module. *Why:* a precise verb-phrase name *is* the documentation — if you must comment what a function does, the name failed.

**Few arguments.** Aim for zero, one, or two; avoid three; replace longer lists with an argument object. A monadic function should either ask about its argument or transform it (not signal via an output side effect). *Why:* every argument is something the reader must hold and the test must cover; arguments also fight the name — `assertEquals(expected, actual)` only works because the order is learned.

**No flag arguments.** Never pass a boolean to make a function behave two ways. *Why:* it's a loud admission the function does more than one thing; split it into two named functions (`renderForSuite()` / `renderForSingleTest()`).

**No output arguments.** Don't mutate a passed-in object to return a result; return a value, or make it a method on the object being changed. *Why:* readers expect information to go *in* through arguments and *out* through the return; output arguments force a double-take.

**No hidden side effects.** A function must not secretly change state, mutate inputs, or do anything its name doesn't promise. *Why:* a hidden change creates a temporal coupling ("you must call A before B") that surprises every caller and breeds order-dependent bugs.

**Command–Query Separation.** A function either *does* something (a command, returns nothing) or *answers* something (a query, changes nothing) — never both. *Why:* `if (set("k","v"))` is ambiguous — did it ask whether the key existed, or assert it was set? Separation removes the riddle.

**Prefer exceptions to error codes, and isolate the handling.** Signal failure with your language's error mechanism (exceptions, result/option types), not returned status codes; extract the body of each `try`/`catch` into its own function so error handling is *one thing* — ideally the only thing that function does. *Why:* error codes force the caller to check and nest immediately, tangling the happy path; pulling handling aside keeps the main logic clear. (See `ERRORS.md`.)

**Don't repeat yourself.** Fold duplicated logic into one function. *Why:* duplication is a prime source of bloat and of bugs that get half-fixed — every copy is another place a change must land.

**Structured-programming dogma is optional at this size.** One-entry/one-exit adds little when functions are tiny; multiple `return`s (and the odd `break`/`continue`) can be clearer. Just avoid `goto`. *Why:* the rule earns its keep only in large functions — and you aren't writing those.

## How you actually get there

Nobody writes clean functions first try. Write a rough draft that works — clumsy, too long, wrong names — and get it under tests. Then massage it: split, rename, drop duplication, reorder for the Stepdown Rule, all while the tests stay green. Clean functions are the product of refinement (see `../DEEPENING.md` and `refining-code-successively` in *Clean Code* ch. 14), not of first drafts.

## Checklist (the `review` craft pass runs this)

- [ ] Small — fits on a screen, ideally < ~20 lines, ≤ 2 levels of indent
- [ ] Does one thing at one level of abstraction (nothing extractable with a non-restating name)
- [ ] Name is a clear verb phrase matching exactly what it does
- [ ] ≤ 2 arguments; no flag/boolean args; no output args; long lists wrapped in an object
- [ ] No hidden side effects; inputs not mutated
- [ ] Either a command or a query, not both
- [ ] Failure via exceptions/results, not error codes; handling extracted to its own function
- [ ] No duplicated logic

## Signals this feeds (spine)

`long-function` (max function length), `too-many-args` (≥ 4 parameters), `deep-nesting` (≥ 4 levels), `duplication` (repeated blocks) — measured by `craft_ingest` and surfaced by `archmap_scan_signals(map, family="craft")`. The *subjective* parts above (is this name good? is this really one thing?) stay as this rule the skills apply — they are not auto-measured.

## References

- `reference/functions.md` — the deep dive: argument forms in detail, the switch/abstract-factory pattern, the "extract until you drop" worked example, and more before/after transforms.
- Source chapter (original Java): *Clean Code* ch. 3, "Functions."
- Pairs with `MINIMALISM.md` (how little behind the seam) and `ERRORS.md` (error handling as one thing).
