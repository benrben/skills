# Craft

The **craft** layer is Fathom one altitude down. The suite reasons about a codebase at the **module / seam** level (`LANGUAGE.md`); craft reasons at the **name / function / test / error / smell** level — the implementation *behind* the seam. Drawn from Robert C. Martin's *Clean Code*, generalized to **any language**.

It is **substrate, not skills** — like `MINIMALISM.md`, these docs have no `SKILL.md` and are *referenced by* the five skills at the right cycle step. The five stay five.

## How craft reaches each skill

| Skill | Reads | At |
|-------|-------|----|
| `code` | `FUNCTIONS` · `NAMING` · `ERRORS` · `COMMENTS` · `TESTS` | writing behind the fixed seam (pairs with `MINIMALISM.md`) |
| `review` | `SMELLS` (+ all, as the checklist) | the craft pass over touched modules |
| `design` | `STRUCTURE` · `ERRORS` | shaping modules/interfaces (SRP/cohesion = depth; boundaries = seams; error modes ∈ interface) |
| `map` | seeds the project's craft `rule` docs; runs `craft_ingest` | reconcile / find-indicators |
| `understand` | reads craft debt | the read-only tour |

## The docs

| Doc | Clean Code | Holds |
|-----|-----------|-------|
| [`FUNCTIONS.md`](FUNCTIONS.md) | ch. 3 (+5) | small, one-thing, few args, no flags/side effects |
| `NAMING.md` | ch. 2 | intention-revealing, unambiguous, searchable names |
| `ERRORS.md` | ch. 7 | exceptions/results over codes; error modes are part of the interface |
| `TESTS.md` | ch. 9 | clean tests, one concept, F.I.R.S.T.; the interface is the test surface |
| `STRUCTURE.md` | ch. 6, 8, 10, 11, 12 | abstraction, SRP/cohesion (= depth), boundaries (= seams), simple design |
| `COMMENTS.md` | ch. 4 | explain *why* in code; delete the comments that lie |
| `SMELLS.md` | ch. 17 | the catalog, generalized — the source of the `review` craft pass and the signal thresholds |

`reference/` holds the deep dives (e.g. [`reference/functions.md`](reference/functions.md)) — read on demand, the way skills layer `SKILL.md` → `fathom/*.md`.

## How much of Clean Code is drawn in

Three destinations, so the book lands where it actually bites:

- **Measured signals** — what a parser can count: function length, argument count, nesting, duplication, untested interfaces, large classes, dead code, magic numbers. These fire via `archmap_scan_signals(map, family="craft")`.
- **`rule` docs** — the *subjective* craft (a good name, a useful comment, formatting) recorded per-map as the existing `rule` doc type, which `code` and `review` already read. Taste is enforced as a convention, never faked as a metric.
- **`design` candidates** — the *structural* craft (a god function, a class with no cohesion, a leaking boundary) becomes a deepening candidate, because the fix changes the seam, not just the implementation.

## The sub-vocabulary

Craft adds words below the architecture vocabulary; it never renames an architecture term. *function · name · smell · heuristic · level of abstraction · side effect.* Where craft meets architecture, the architecture word wins: a "god function" you fix by splitting behind a **seam** is a `design` candidate, not just a `long-function` smell.

> Status: `FUNCTIONS.md` is the built sample. The rest land as the substrate is filled in (see the craft-integration design doc).
