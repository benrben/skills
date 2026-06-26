# Craft · Naming

The **craft** layer is the altitude *below* `LANGUAGE.md` and `MINIMALISM.md`: how to write the implementation **behind a seam** so it reads cleanly. Naming is the cheapest, highest-leverage craft there is — every name you choose is read far more often than it's written. Drawn from *Clean Code* ch. 2. Language-agnostic — applies to variables, functions, types, modules, packages, files alike.

**Read by:** `code` (every identifier written behind a fixed interface — pairs with `MINIMALISM.md`), `review` (the craft pass), `map`/`code` (keeping the project's domain language honest — map §8, code §9).

## Where this sits in the suite

- **Depth / seam** (`LANGUAGE.md`) decides *what the interface is* — and its name is the first thing a caller meets.
- **Minimalism** (`MINIMALISM.md`) decides *how little* sits behind it; fewer things means fewer names, each carrying more.
- **This doc** decides *how well* each name reads.

Naming spans the whole stack but never moves the seam. A bad name on a public interface is still a craft fix (rename it) until the *concept* is wrong — when the name can't be made honest without re-cutting the boundary, that's `design`, not craft. Two destinations matter for Fathom: **domain** names — the project's nouns and verbs — live in the **`glossary` doc** (`fathom/CONTEXT-FORMAT.md` already says "be opinionated, pick the best word, list the others under _Avoid_", which *is* "one word per concept"); **general** naming conventions become a per-map **`rule` doc** that `code` and `review` read.

## The rules — each with its *why*

**Use intention-revealing names.** The name should answer why it exists, what it does, how it's used — with no comment needed. *Why:* `d` (elapsed time in days) tells you nothing; `elapsedTimeInDays` lets a reader skip the hunt entirely. If you need a comment to explain a name, the name failed.

```
// smell — the reader has to decode the cells and the magic 4
list = grid.filter(x => x[STATUS] == 4)
// craft — the names carry the meaning
flaggedCells = gameBoard.filter(cell => cell.isFlagged())
```

**Avoid disinformation.** Don't use a name whose connotation is false: don't call something a `list` if it isn't one, don't reuse a platform term (`hp`, `aix`) for something unrelated, don't name two things with nearly identical spellings. *Why:* a wrong name is worse than a vague one — it actively misleads, and the reader trusts it until it burns them.

**Make meaningful distinctions.** If two things differ, their names must say *how* they differ — no noise words. `Info`/`Data`, `a`/`the`, and number series `a1`/`a2`/`a3` distinguish nothing. *Why:* `getActiveAccount` / `getActiveAccountInfo` forces the reader to guess which to call and what the difference is; the names promise a distinction they don't deliver.

**Use pronounceable names.** If you can't say it in a conversation, rename it. `genymdhms` → `generationTimestamp`. *Why:* programming is social — people discuss code aloud, and an unpronounceable name makes that discussion stupid ("gen why em dee aitch em ess").

**Use searchable names.** Single letters and raw literals can't be grepped; give a name length that tracks its scope. *Why:* `7` appears everywhere and `e` matches every word, so neither can be found; `MAX_CLASSES_PER_STUDENT` and `workDaysPerWeek` locate instantly. A one-letter name is fine *only* as a local in a tiny scope — the bigger the scope, the longer the name should be.

```
// the literal 5 hides in the noise; the constant is findable and self-explaining
WORK_DAYS_PER_WEEK = 5
total = tasks * WORK_DAYS_PER_WEEK
```

**Avoid encodings.** Don't bake type or scope into names — no Hungarian notation (`phoneString`), no member prefixes (`m_description`), no interface/implementation tags (`IShapeFactory`). *Why:* modern tooling and small classes make encodings dead weight that the reader must mentally strip; an encoded name also becomes a lie the day the type changes. If you must mark one side of an interface/implementation pair, prefer encoding the *implementation* (`ShapeFactoryImpl`) over the interface.

**Avoid mental mapping.** Don't make the reader translate a name into the real concept in their head. *Why:* a loop counter `i` is fine, but a placeholder `r` that "really means the lowercased URL without the host" forces a silent lookup every time it's read — clarity beats cleverness, and the reader's working memory is finite.

**Class names are noun phrases; method names are verb phrases.** Classes/types: `Customer`, `WikiPage`, `AddressParser` — never a verb. Methods/functions: `save`, `deletePage`, `isPosted` — accessors/predicates take the `get`/`set`/`is` prefix. *Why:* a type *is a thing* and a method *does a thing*; matching the part of speech to the role lets the call read like a sentence (`page.deleteReference()`).

**Don't be cute.** Say what you mean: `deleteItems`, not `whack`; `abort`, not `eatMyShorts`. *Why:* cleverness depends on shared culture and a mood; it stops being funny the second a maintainer doesn't get the joke, and then it's just an obscure name.

**Pick one word per concept — and stick to it.** One term for one abstract idea across the whole codebase: choose among `fetch` / `retrieve` / `get`, or `controller` / `manager` / `driver`, and don't mix them. *Why:* a consistent lexicon lets a reader assume that the same word means the same thing everywhere; mixing synonyms makes them wonder whether `DeviceManager` and `ProtocolController` differ on purpose. (This is exactly the `glossary` doc's "pick the best word, list the rest under _Avoid_.")

**Don't pun — one word, one meaning.** The flip side: don't use one word for two different ideas. If `add` means "concatenate two values" in one place, don't reuse `add` for "insert into a collection" — call that `insert` or `append`. *Why:* a pun breaks the promise that the same word means the same thing; the reader, trusting consistency, picks the wrong method.

**Use solution-domain names where the reader is a programmer.** Reach for CS/pattern/math terms freely — `AccountVisitor`, `JobQueue`, `Bloomfilter`. *Why:* the people reading code know these words; a technical name communicates precisely to the audience that's actually there. Don't force a problem-domain word onto a purely technical thing.

**Use problem-domain names when there is no programmer term.** When nothing in the solution domain fits, use the name an expert in the field would use. *Why:* it lets a maintainer ask a domain expert what it means — and separating problem-domain from solution-domain names is itself information about which is which.

**Add meaningful context — but no gratuitous context.** Give a name the context it needs (a bare `state` is ambiguous; `addrState`, or a field inside an `Address` type, is not) — but don't prefix every name in the application with the app's name. *Why:* unscoped names like `firstName`/`lastName`/`state` floating free don't read as an address; yet `GSDAccountAddress` in an app called "Gas Station Deluxe" makes every name longer and the autocomplete useless. Prefer a *class* that supplies the context over a prefix that pollutes it.

## How you actually get there

You will not name everything right the first time, and that's expected. Pick a workable name, get the code under tests, then rename freely as the concept sharpens — modern tooling makes a rename safe and cheap, and the cost of a wrong name compounds the longer it sits. Naming is refinement (see `../DEEPENING.md`), and renaming *is* improving the code, never busywork.

## Checklist (the `review` craft pass runs this)

- [ ] Name reveals intent — why it exists, what it does, how it's used — without a comment
- [ ] No disinformation: no false connotations, no near-identical spellings, no misused platform terms
- [ ] Distinctions are meaningful — no `Info`/`Data`/`a`/`the` noise words, no `a1`/`a2` number series
- [ ] Pronounceable and searchable; name length scales with scope (no bare literals, no `i` outside tiny scopes)
- [ ] No encodings — no Hungarian, no `m_`/member prefixes, no `I`-for-interface tags
- [ ] Class = noun phrase, method = verb phrase; predicates read as `is`/`has`
- [ ] One word per concept across the codebase, and no word reused for two concepts (no puns)
- [ ] Domain nouns/verbs match the project's `glossary` doc
- [ ] Context added where a name is ambiguous; no app-name prefixes on every identifier

## Signals this feeds (spine)

**None — naming quality is taste, and Fathom does not fake taste as a metric.** A parser can flag a single-letter identifier in a wide scope, but it cannot tell `Manager` from a *good* name, judge whether a distinction is meaningful, or know the project's domain words. So naming is enforced entirely as guidance, not measurement: the *general* conventions above live in a per-map **`rule` doc** (read by `code` and `review`), and the *domain* vocabulary lives in the **`glossary` doc** (where "pick one word, list the rest under _Avoid_" already encodes "one word per concept"). There is no `naming` signal in `archmap_scan_signals`, and adding one would be a lie. Naming is checked by the `review` craft pass against this rule, by a human.

## References

- `reference/naming.md` — the deep dive: the intention-revealing before/after in full, the noise-word and number-series catalog, the encoding cases (Hungarian, member, interface prefixes), and the context-vs-gratuitous-context worked example.
- Source chapter (original Java): *Clean Code* ch. 2, "Meaningful Names."
- Domain vocabulary: `fathom/CONTEXT-FORMAT.md` (the `glossary` doc — "be opinionated, pick the best word"). Adjacent craft: `FUNCTIONS.md` (descriptive function names), `COMMENTS.md` (a good name beats a comment).
