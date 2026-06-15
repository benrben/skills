# Minimalism

How to write **less code without losing the seam**. Assumes the vocabulary in [LANGUAGE.md](LANGUAGE.md) — **module**, **interface**, **depth**, **seam**, **leverage**.

The deep-module principle says nothing about how much code sits behind an interface — `depth` is leverage at the seam, and a deep module is allowed to be large (LANGUAGE.md rejects depth-as-implementation-size precisely because it *rewards padding*). But "allowed to be large" is not "should be." Two distinct facts live on every module on the spine:

- **`depth`** — leverage at the interface (the seam). Keep it **high**.
- **`size`** — relative implementation mass, the code behind the seam. Drive it **down**.

They are different fields. "Write less code" means **lower `size`**; "keep the seam" means **hold `depth`**. They only conflict if you cut `size` by cutting the interface — so don't.

## The rule

> Minimize the implementation **behind** a seam. Never minimize by removing the seam.

For a module whose interface is fixed, the implementation should be the **smallest that still satisfies it**.

## The ladder — climb it behind the seam

For each piece of behaviour the interface promises, take the first rung that holds, *behind the fixed interface*:

1. **Does this need to exist?** Behaviour no caller requires is not deferred — it's not written (YAGNI).
2. **Standard library** — does stdlib already do it?
3. **Native platform feature** — is it already in the language/runtime/platform?
4. **An installed dependency** — does something already in the project do it?
5. **One line** — can the remaining logic be one expression?
6. **Only then** — write the minimum implementation that passes the interface tests.

Rungs 2–4 are the most Fathom-aligned move there is: **reaching for stdlib or a dependency is consuming someone else's deep module.** Hand-rolling what `tomllib`/`itertools`/the runtime already does is manufacturing a *shallow* module beside a deep one that already exists. `leverage` is the same word in both vocabularies.

## The guardrail — the seam is never the thing you cut

`size` must come down **without** touching `depth`:

- **Never inline a module away** to save a file. If `load_config` becomes three raw `tomllib.loads` calls at three call sites, the validation / ordering / error-mode knowledge it hid reappears across N callers — the **deletion test fails** (complexity scattered, didn't concentrate). You traded `depth` for `size`. That is the one ponytail-style move Fathom overrides.
- **"Fewer files" yields to "one small interface."** Prefer fewer files only among shapes that keep the same seam.
- The interface is still the test surface. Delegating to stdlib changes the implementation, not the contract — the existing interface tests must stay green untouched.

## The tie-break

When two implementations both satisfy the interface **and** pass its tests, choose the one with **less code** — boring over clever. This is the only place raw line-count decides anything, and it decides only ties.

## Where the suite applies this

- **fathom:code** — when building to a chosen interface, climb the ladder behind the seam and pick the smallest implementation that passes the interface tests. This is where less code actually gets written.
- **fathom:deepen** — a distinct candidate flavour: a module is shallow because it **hand-rolls what stdlib/a dependency already does**. The deepening is *delegate behind the seam*, not *merge modules*. Category is usually **in-process** (LANGUAGE.md / DEEPENING.md).
- **fathom:plan** — when specifying an interface, name the existing deep module (stdlib/dep) that should sit behind the seam, so fathom:code doesn't reinvent it.

## The signal

The spine can measure this one (unlike raw YAGNI, which leaves no trace): **`bulky-impl`** fires when a module carries large implementation mass for little leverage — `size` well above baseline while `depth` stays low. It reads "a lot of hand-written code earning little depth": climb the ladder behind the seam, or deepen it. Surfaced by `archmap_scan_signals`.
