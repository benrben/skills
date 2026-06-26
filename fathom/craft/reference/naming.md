# Craft · Naming — deep reference

The depth behind `../NAMING.md`. Read on demand. All examples are neutral pseudocode; the originals (Java) are in *Clean Code* ch. 2.

## Intention-revealing names — the full transform

A name should make the reader need no further explanation. Watch a fragment with opaque names acquire meaning through renaming alone — no logic changes:

```
// no intent: what is the list? what is 4? what is the cell?
function getThem(list):
    result = []
    for x in list:
        if x[0] == 4:
            result.add(x)
    return result
```

Three questions are unanswered: what's in the list, what does index `0` mean, what does `4` mean, what's the returned list for. Name them and the code explains itself with the *same structure*:

```
function getFlaggedCells(gameBoard):
    flaggedCells = []
    for cell in gameBoard:
        if cell.status == FLAGGED:
            flaggedCells.add(cell)
    return flaggedCells
```

Better still, give the cell a type so `cell.status == FLAGGED` becomes `cell.isFlagged()`. The lesson: the difficulty was never the logic — it was that the names hid the intent.

## Disinformation — the traps

- **False container types.** Don't call a group `accountList` unless it's actually a List; if the type might change, `accounts` or `accountGroup` won't lie.
- **Near-identical names.** `XYZControllerForEfficientHandlingOfStrings` next to `XYZControllerForEfficientStorageOfStrings` differ by two words buried mid-name; the eye and the autocomplete both slip.
- **Misleading lookalikes.** Lowercase `l` and uppercase `O` read as `1` and `0`. `int a = l; if (O == l)` is a trap.
- **Hijacked platform words.** Reusing `hp`, `aix`, `sco` (which mean specific things to readers) for unrelated concepts plants a false association.

## Meaningful distinctions — noise words and number series

When two names exist in the same scope, the difference between them must be *information*, not decoration.

```
// number series: carries zero information about how the three differ
function copy(a1, a2, a3): …
// craft: the names say what each role is
function copy(source, destination, count): …
```

Noise words are categorical filler that distinguishes nothing — they could be deleted with no loss:

- **`Info` / `Data`** — `ProductInfo` and `ProductData` and `Product` are indistinguishable; `Info` and `Data` are "a" and "the" wearing a tie.
- **`a` / `the` / `variable` / `Object` / `String`** — `theMessage` vs `message`, `nameString` vs `name`, `Customer` vs `CustomerObject`: the suffix adds nothing.
- **Method pairs that promise a distinction they don't keep** — if `getActiveAccount`, `getActiveAccounts`, and `getActiveAccountInfo` coexist, a reader cannot know which to call. Distinguish so that a reader can choose correctly without reading the bodies.

## Pronounceable and searchable — why scope sets length

These two rules pull together: a name must be sayable in conversation and findable with a search, and both push toward *longer* names as scope grows.

```
// unpronounceable, unsearchable
genymdhms; dtaRcrd102; e
// pronounceable, searchable
generationTimestamp; record; event
```

The length-vs-scope rule, stated plainly:

- **Tiny scope (a few lines)** — a single letter is fine; `for i in range` reads cleanly and `i` never escapes.
- **Wide scope (a field, a module-level constant, a long method)** — the name must be long enough to be unambiguous *and* to grep. `MAX_CLASSES_PER_STUDENT` can be found and changed safely; the literal `7` cannot — a search for `7` drowns, and not every `7` means the same thing.

The inverse holds too: a name far longer than its scope is also noise. Match the length to the distance over which the reader must hold it.

## Encodings — Hungarian, members, interfaces

Three encoding habits, each dead weight today:

- **Hungarian notation** — `phoneString`, `iCount`. Types were once invisible and unchecked; now they're not, and the encoding becomes a lie the moment the type changes (a `phoneString` that becomes a structured `PhoneNumber` is now misnamed everywhere).
- **Member prefixes** — `m_description`, `_count`. Classes small enough to read don't need their fields flagged; the editor already colors them, and the prefix is just visual static the reader learns to skip (which defeats its purpose).
- **Interface / implementation tags** — given an interface and one implementation, *don't* tag the interface (`IShapeFactory`); callers shouldn't have to know they're holding an interface. If one side must be marked, mark the implementation: `ShapeFactory` (interface) / `ShapeFactoryImpl` (concrete). In Fathom terms the interface *is* the seam — leave the seam's name clean and let the adapter carry the suffix.

## Mental mapping — clarity over cleverness

A name that forces the reader to translate to the real concept taxes every read. The classic case is a too-clever placeholder:

```
// the reader must remember "r is the lowercased url without the host"
r = url.lower().stripHost()
// say it
hostlessLowercaseUrl = url.lower().stripHost()
```

Single-letter loop indices are the *one* sanctioned mental "mapping" — they're a universal convention in a tiny scope. Everywhere else, smart programmers are precisely the ones who can afford clarity instead of showing they can hold a private mapping in their head.

## Parts of speech — nouns, verbs, and prefixes

- **Types are noun phrases** — `Customer`, `Account`, `AddressParser`. A class named with a verb (`ManageAccount` as a type) is a function pretending to be a thing.
- **Methods are verb phrases** — `postPayment`, `deletePage`, `save`. The call then reads as an action: `account.postPayment(total)`.
- **Accessors / mutators / predicates take prefixes** — `getName`, `setName`, `isPosted`, `hasChildren`. The predicate prefix lets conditionals read in English: `if employee.isActive()`.
- **Factory over telescoping constructor** — when a constructor is overloaded, prefer a named factory method that describes the argument: `Complex.fromRealNumber(23)` reads better than `new Complex(23)`.

## One word per concept, and the pun trap

Two complementary rules, easy to state, easy to violate:

- **One word per concept.** Pick a single verb for a single abstract operation and use it everywhere: don't have `fetch`, `retrieve`, and `get` all meaning "read by key" across sibling classes. Don't mix `controller`, `manager`, and `driver` for the same role. A consistent lexicon is a gift to every future reader — and this is exactly what the `glossary` doc enforces ("pick the best word, list the others under _Avoid_").
- **Don't pun.** The other edge: one word must not name two *different* concepts. If `add` has meant "return the sum of two values," don't also use `add` for "put one item into a collection" — name the second `insert` or `append`. The reader trusts that the same word means the same thing and will reach for the wrong method.

## Solution-domain vs problem-domain names

Two sources to draw names from, and a rule for choosing:

- **Solution domain** — CS terms, algorithm names, pattern names, math. The reader is a programmer, so `JobQueue`, `AccountVisitor`, `Bloomfilter` communicate precisely. Prefer these for things that are purely technical.
- **Problem domain** — the language of the field the software serves. When no solution-domain term fits, use the word a domain expert would use, so a maintainer can go ask that expert.

Keeping the two separated is itself useful: code that wears a problem-domain name is doing domain work; code with a solution-domain name is plumbing. In Fathom, the problem-domain words are exactly what the `glossary` doc pins down.

## Context — meaningful vs gratuitous

A name needs *enough* context and no more.

```
// no context: these three, seen alone, don't read as an address
firstName; lastName; street; city; state
// meaningful context: a class supplies it
class Address:
    street; city; state
// — now `state` inside Address is unambiguous; a bare `state` was not
```

Add context with a containing type or a prefix only where ambiguity demands it (`addrState` if you truly can't make a type). The opposite error is *gratuitous* context — stamping the application's name onto everything:

```
// gratuitous: in an app called "Gas Station Deluxe," every class starts GSD
GSDAccountAddress
// — autocomplete for "GSD" now lists the entire app; the prefix buys nothing
```

Shorter names are better than longer *when they're clear*. Prefer a class that scopes a group of names over a prefix that lengthens every one of them.

## See also

- `../NAMING.md` — the rules + checklist (the `review` craft pass), and why naming feeds **no** signal.
- `fathom/CONTEXT-FORMAT.md` — the `glossary` doc, where the project's domain words live ("one word per concept").
- `../FUNCTIONS.md` — descriptive function names as the function's documentation; `../COMMENTS.md` — a good name deletes the comment that would have explained it.
