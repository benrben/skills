# Minimalism

How to write **less code without losing the seam**. Assumes the vocabulary in [LANGUAGE.md](LANGUAGE.md) — **module**, **interface**, **depth**, **seam**, **leverage**.

## The tension this resolves

Two good instincts pull opposite ways. *Minimalism* (YAGNI, "the best code is the code you never wrote") says: write less. *Deep modules* (Ousterhout) say it is **more important for a module to have a simple interface than a simple implementation** — some implementation is worth keeping if it buys callers a smaller interface. Pushed to extremes they collide: naive minimalism breaks deep modules up into many small shallow ones, and Ousterhout's own warning is that *small modules tend to be shallow* — a lot of little interfaces accumulate more total complexity than the implementation they saved.

The spine already separates the two instincts into two fields on every `Module`:

- **`depth`** — leverage at the interface (the seam). Keep it **high**.
- **`size`** — implementation mass behind the seam (measured from LOC by `archmap_ingest` for actual-plane modules with files; 1.0 == the median module). Drive it **down**.

They are different fields. "Write less code" means **lower `size`**; "keep the seam" means **hold `depth`**. They only conflict when you cut `size` by touching the interface — so don't.

## The rule

> Minimize the implementation **behind** a seam. Never minimize the seam itself, and never split a deep module to make its pieces small.

For a module whose interface is fixed, the implementation should be the **smallest that still satisfies it**.

## The ladder — climb it behind the seam

For each piece of behaviour the interface promises, take the first rung that holds, *behind the fixed interface*:

1. **Does this need to exist?** Behaviour no caller requires isn't deferred — it's not written, and you say so in one line (YAGNI).
2. **Standard library** — does stdlib already do it?
3. **Native platform feature** — is it already in the language/runtime/platform?
4. **An installed dependency** — does something already in the project do it? **Never add a *new* dependency for what a few lines do** — a new dependency is a new edge and a new seam to own (and one adapter is only a hypothetical seam; see LANGUAGE.md).
5. **One line** — can the remaining logic be one expression?
6. **Only then** — write the minimum implementation that passes the interface tests.

Rungs 2–4 are the most Fathom-aligned move there is: **reaching for stdlib or a dependency is consuming someone else's deep module.** Hand-rolling what `tomllib`/`itertools`/the runtime already does is manufacturing a *shallow* module beside a deep one that already exists. `leverage` is the same word in both vocabularies.

## The two ways minimalism erodes depth — both forbidden

`size` must come down **without** lowering `depth`. Two failure modes:

1. **Inlining the seam away** to save a file. If `load_config` becomes three raw `tomllib.loads` calls at three call sites, the validation / ordering / error-mode knowledge it hid reappears across N callers — the **deletion test fails** (complexity scattered, didn't concentrate). You traded `depth` for `size`.
2. **Fragmenting a deep module** into many small "simpler" ones to make each piece tiny. Each new piece carries its own interface; the total interface surface — the thing callers must learn — *grows*. "Fewest files" is right only when it means **not splitting** a deep module; it is never a licence to split one.

"Fewer files" yields to "one small interface." The interface is still the test surface — delegating to stdlib changes the implementation, not the contract, so the existing interface tests must stay green untouched.

## Never simplify away the contract

Some things are **part of the interface's promise** (its invariants and error modes), so cutting them isn't writing less code — it's breaking the contract. Never simplify away:

- input validation at trust boundaries,
- error handling that prevents data loss,
- security and access control,
- accessibility basics,
- anything the caller explicitly asked for.

Non-trivial logic on a money, security, or parsing path leaves **one runnable check behind** — the smallest assertion that fails if the logic breaks. That check is a minimal expression of "the interface is the test surface," not framework overhead.

## Mark the ceiling, keep the upgrade path

When you stop at a rung deliberately, **mark the seam with the ceiling and the upgrade path** so the simplification is legible and its deepening is a known next step, not silent debt:

```python
# ceiling: one global lock — switch to per-account locks if throughput matters
```

A marked ceiling is a **pre-registered deepening**: the simplest thing that works *today*, plus the exact condition under which it should grow. On the spine, record it as a **`ceiling` doc** scoped to the module (the current rung + the trigger to deepen; see [DOC-TYPES.md](DOC-TYPES.md)) — or, when the upgrade is worth queuing, as a **deferred candidate** (`archmap_suggestions(map, action="decide", decision="deferred", note="ceiling: …")`) — so when the constraint that justifies deepening actually arrives, `fathom:design` already has it. Minimalism and deepening are the same lifecycle seen from two ends.

## The tie-break

When two implementations both satisfy the interface **and** pass its tests, choose the one with **less code** — boring over clever ("clever is what someone decodes at 3am"). This is the only place raw line-count decides anything, and it decides only ties.

## Where the suite applies this

- **fathom:code** — when building to a chosen interface, climb the ladder behind the seam and pick the smallest implementation that passes the interface tests, never cutting the contract. This is where less code actually gets written, and where the `ceiling` doc is recorded when it stops at a rung.
- **fathom:design (improve mode)** — a distinct candidate flavour: a module is shallow because it **hand-rolls what stdlib/a dependency already does**. The deepening is *delegate behind the seam*, not *merge modules*. Category is usually **in-process** (DEEPENING.md). Deferred ceilings live here too.
- **fathom:design (new mode)** — when specifying an interface, name the existing deep module (stdlib/dep) that should sit behind the seam, so fathom:code doesn't reinvent it.

## The signal

The spine can measure this one (unlike raw YAGNI, which leaves no trace): **`bulky-impl`** fires when a module carries large implementation mass for little leverage — `size` ≥ 2× the median module while `depth` stays low (< 0.5). `size` is a **measured** fact: `archmap_ingest` counts each actual-plane module's non-blank LOC from its files and normalizes it (median == 1.0; intended modules keep their estimate), the same pipeline that measures `churn` and `coverage`. LOC is a deliberately boring proxy — empirically it tracks implementation complexity at least as well as cyclomatic complexity, which only sees control flow — so the signal reads "a lot of *real* hand-written code earning little depth": climb the ladder behind the seam, or deepen it. Surfaced by `archmap_scan_signals`.
