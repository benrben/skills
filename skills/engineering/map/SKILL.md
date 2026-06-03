---
name: map
description: Build or refresh an accurate architecture map of a codebase — what its modules are, how deep each is, what they depend on, where they leak, and how well they're tested at the interface. Use when onboarding a repo into the arch-map spine, running a periodic architecture health check, reconciling drift after a big merge, or when asked "what does this codebase actually look like / is the map still accurate." This skill only models what EXISTS — it never proposes deepenings (that's fathom:deepen), designs intended structure (fathom:plan), or edits source (fathom:code). Do NOT use for "improve/refactor/clean up" requests, or for "design the new X" — route those to fathom:deepen and fathom:plan respectively.
---

# Map

Build and maintain an accurate living model of what a codebase **is** — seed it from a repo by depth, inspect it, and reconcile drift on demand — without proposing refactors or editing source.

This is the suite's surveyor. It turns a repository into an accurate, persistent arch-map **model** and keeps that model honest over time. Every other Fathom skill reads the map this one writes: [fathom:deepen](../deepen/SKILL.md) finds friction in genuinely shallow modules, [fathom:plan](../plan/SKILL.md) designs intended structure against the real baseline, and [fathom:code](../code/SKILL.md) targets a refactor at the right node. If the map is wrong, all of them are wrong — so accuracy is the whole job.

## Glossary

Speak only this vocabulary — never "component," "service," "API," or "boundary." Full definitions in [../fathom/LANGUAGE.md](../fathom/LANGUAGE.md).

- **Module** — anything with an interface and an implementation (function, class, package, tier-spanning slice). Scale-agnostic: a single deep function and a whole slice can each be one node.
- **Interface** — everything a caller must know to use the module: types, invariants, ordering, error modes, required config. Not just the type signature.
- **Implementation** — the code inside.
- **Depth** — leverage at the interface: a lot of behaviour behind a small interface. **Deep** = high leverage. **Shallow** = interface nearly as complex as the implementation.
- **Seam** — where an interface lives; a place behaviour can be altered without editing in place. (Use this, not "boundary.")
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Leverage** — what callers get from depth. **Locality** — what maintainers get from depth: change, bugs, knowledge concentrated in one place.

Key principles:

- **Deletion test.** Imagine deleting the module. If complexity vanishes, it was a pass-through (shallow). If complexity reappears across N callers, it was earning its keep (deep). Every `depth` score is the recorded answer to this question.
- **The interface is the test surface.** `coverage` is how much of the interface tests cross — not a line-count from a coverage tool.
- **One adapter = hypothetical seam. Two adapters = real seam.**

The map records these as **facts**. Modelling a module as shallow (low `depth`) is a measurement, not a recommendation to fix it — fixing is fathom:deepen's job, not this skill's.

## What this skill writes — and what it must not touch

fathom:map has a sharp, single-purpose seam against the shared spine. It writes only the **modules** slice and a module's depth / coverage / edges / files / iface / seam / tests / updated state. It reads everything else.

It MUST NOT:

- **Propose deepenings or attach candidates** — no `flag_deepening`, no grilling, no candidate queue. That lifecycle is owned by [fathom:deepen](../deepen/SKILL.md). The map models shallowness as a fact via the `depth` score; it never recommends fixing it.
- **Design intended/aspirational structure** — it records the module graph that EXISTS today, never the one you want. Intended-plane modules and Plans are [fathom:plan](../plan/SKILL.md)'s territory.
- **Edit, refactor, move, or merge source, or change interfaces** — it is read-only against the repo. [fathom:code](../code/SKILL.md) is the only skill that edits source.
- **Decide on, accept, defer, or resolve candidates** — it never touches the decisions slice (`decide` / `resolve` / `start_grilling` / `grilling_done`).
- **Author ADRs** — it reads ADRs as facts about what is; it defers decision-recording to [adr-writer](../adr-writer/SKILL.md).
- **Run, build, or test the app, or import a coverage report** — `coverage` is a judgement about the interface test surface, not a numeric report.

## The shared map

The arch-map spine is a **shared, file-backed** set of named maps — typically one map per project. There are no hooks and no git-based drift detection: persistence is skill-driven. You bootstrap by resolving the map id and thread that `map` id through every single tool call.

```
list_maps()                       # what maps already exist? (the resume-vs-create decision)
create_project("My Repo") -> {map: "my-repo", ...}   # capture the returned id
show_map("my-repo")               # render the network for inspection
```

Reconcile is **run explicitly** — when a maintainer asks for a health check, after a big merge, or when someone asks "is the map still accurate." Nothing reconciles the map for you in the background.

## Process

### 1. Resolve the target map

Call `list_maps()` and decide **resume vs create**:

- **A map for this repo already exists** → resume it (this run is a health check / drift reconcile). Capture its `map` id.
- **No map exists** → `create_project("<human repo name>")` and capture the returned `map` id (e.g. `"my-repo"`). Every later call passes it.

Then read the repo's `CONTEXT.md` / `CONTEXT-MAP.md` so module domains and labels use the project's domain language ([../fathom/CONTEXT-FORMAT.md](../fathom/CONTEXT-FORMAT.md)), and skim `docs/adr/` so you treat recorded decisions as **facts about what is** — never as things to challenge or re-suggest ([../fathom/ADR-FORMAT.md](../fathom/ADR-FORMAT.md)).

If the map already exists, skip to **step 6 (Reconcile)**. A fresh map runs steps 2–5.

### 2. Seed — walk the real code (empty map only)

Dispatch **Explore subagents** (Agent tool, `subagent_type=Explore`) to walk the codebase organically — by directory, by domain from `CONTEXT.md`, or by entry interfaces — not by rigid metrics. Brief each subagent in [../fathom/LANGUAGE.md](../fathom/LANGUAGE.md) + `CONTEXT.md` vocabulary and ask it to report, per candidate module:

- the **files** that compose it,
- its **interface** — everything a caller must know: types, invariants, ordering, error modes, required config,
- where the **seam** sits,
- the real **dependsOn** edges (actual imports/calls, not vibes),
- any **leaksTo** (internals visible across the seam — a seam violation),
- existing **tests**.

### 3. Derive each module's fields by judgement, not formula

- **depth** (0 = shallow … 1 = deep) — apply the **deletion test**: would deleting this module concentrate complexity behind a small interface (deep, → 1.0) or just shuffle a pass-through around (shallow, → 0.0)?
- **coverage** (0..1) — how much of the **interface** is exercised by tests (the test surface), not raw line coverage.
- **size** — relative implementation mass.
- **dependsOn** — real edges only, resolved by module id.
- **leaksTo** — a judgement call about seam violations (rendered as a red edge).
- **iface / seam / files / tests** — prose plus the file list. Use [../fathom/DEEPENING.md](../fathom/DEEPENING.md)'s dependency-category vocabulary only to **describe an edge accurately** (in-process, local-substitutable, ports & adapters, true external) — never to propose a fix.

Record modules at the granularity that **earns its keep** — a module is scale-agnostic, so a tier-spanning slice and a single deep function can both be nodes. Name domains and labels with `CONTEXT.md` terms.

### 4. Commit the model in bulk

Call `add_modules(map, [...])` with the full module list. `id` / `label` / `domain` are required; fill `depth` / `size` / `seam` / `iface` / `coverage` / `files` / `dependsOn` / `leaksTo` / `tests`. Prefer one or a few bulk calls over many `add_module` calls. Edges resolve by id, so **add all nodes before** relying on `dependsOn` / `leaksTo` to render.

```
add_modules("my-repo", [
  {"id": "order-intake", "label": "Order Intake", "domain": "orders",
   "depth": 0.8, "coverage": 0.7, "size": 1.4,
   "seam": "OrderIntake.submit(cart) -> OrderId",
   "iface": "validates cart invariants, idempotent on retry, raises OutOfStock",
   "files": ["src/orders/intake.py", "src/orders/validate.py"],
   "dependsOn": ["inventory", "pricing"], "leaksTo": [],
   "tests": "tests/orders/test_intake.py exercises the submit interface"},
  ...
])
```

### 5. Inspect and sanity-check

Render the network and the diagnostic cuts:

```
show_map("my-repo")                                                   # the full network graph
render_view("my-repo", {"kind": "table", "of": "orphans"})            # nodes with no edges
render_view("my-repo", {"kind": "table", "of": "low-coverage"})       # interfaces tests don't cross
render_view("my-repo", {"kind": "table", "of": "leaks"})              # seam violations
render_view("my-repo", {"kind": "bar", "metric": "depth", "groupBy": "domain"})  # which domains are shallow
```

Walk the orphans and leaks with the maintainer. An **orphan is almost always a real edge you missed** — fix its `dependsOn` rather than leave it floating; only rarely is it genuinely dead code. The map should match how the maintainer describes the system; **where it doesn't, the map is wrong** — correct it with `update_module` / `set_depth` / `set_coverage`.

### 6. Reconcile drift (resumed map)

A reconcile is an explicit re-walk of the parts of the repo that may have changed — you decide the scope (a recent merge's files, a domain the maintainer flags, or the whole repo for a periodic health check). There is no background drift signal to consult; you re-derive against the real code.

- **For each module in the reconcile scope**, pull its current record (`get_module` / `get_modules`), re-walk its `files` (an Explore subagent if the change is large), and re-derive depth / coverage / dependsOn / leaksTo / iface / seam / tests via `update_module` or `update_modules`. A refactor can deepen a module (raise `depth`); a new caller can change its edges. Use `set_depth` / `set_coverage` for targeted single-field corrections.
- **For files that belong to no module**, decide: do they extend an existing module (add to that module's `files`), or are they a newly-discovered module (`add_module`)?
- **For modules whose files no longer exist**, `delete_modules(map, [...])` — this prunes dangling edges. If a file merely **moved**, prefer updating `files` over deleting, so hand-curated iface/seam prose isn't lost.
- **Clear the halos.** Once a module's model matches reality again, `mark_updated(map, module, False)` so it stops showing the "changed since last scan" halo.

```
get_modules("my-repo", ["order-intake", "pricing"])
update_modules("my-repo", [{"id": "order-intake", "depth": 0.9, "dependsOn": ["inventory", "pricing", "promotions"]}])
delete_modules("my-repo", ["legacy-coupon"])     # its files are gone
mark_updated("my-repo", "order-intake", False)
```

### 7. Maintain the domain language as a side effect

If seeding or reconciling surfaces a **load-bearing concept** that `CONTEXT.md` doesn't name, add the term ([../fathom/CONTEXT-FORMAT.md](../fathom/CONTEXT-FORMAT.md) discipline; create the file lazily if it doesn't exist). Do **not** invent ADRs here — fathom:map records facts, not decisions. If reconciling reveals a decision worth recording, note it and hand off to [adr-writer](../adr-writer/SKILL.md).

### 8. Close out and hand off

Re-run `show_map(map)` so the maintainer sees the reconciled graph, and state the headline shape: deepest and shallowest domains, the low-coverage and leak hot-spots, any orphans resolved. Then point to siblings **without doing their jobs**:

- **Shallow clusters that need fixing** → [fathom:deepen](../deepen/SKILL.md) (it proposes candidates and grills the chosen one).
- **New or changing work that needs intended structure** → [fathom:plan](../plan/SKILL.md) (it designs the intended deep-module graph).
- **Executing any refactor or build** → [fathom:code](../code/SKILL.md) (the only source editor; it reconciles the map for what it changes).
- **A load-bearing decision surfaced while mapping** → [adr-writer](../adr-writer/SKILL.md).

fathom:map stops at an **accurate picture of what is**. It does not recommend, design, decide, or build.

## Why this is a deep module

fathom:map *is* the deletion test applied at repo scale: every node's `depth` is the recorded answer to "if this module vanished, would complexity concentrate behind a small interface or just scatter?" The map itself is a deep module — the whole codebase's structure (modules, depth, edges, coverage, leaks) sits behind one small, shared interface (the spine's tools). Callers — humans **and** the sibling skills — get **leverage** (read the map instead of re-walking the repo) and **locality** (one place to learn or correct the architecture).

Its seam is sharp and single-purpose: it writes only the modules / depth / coverage / edges / updated slices and reads everything else, so it composes with fathom:deepen (candidates), adr-writer (decisions), and fathom:code (source) without overlap. `coverage` is deliberately modelled at the interface, not imported as a line count, because **the interface is the test surface** — the same principle the whole suite tests by. Delete fathom:map and accuracy of the model becomes nobody's job: every sibling would re-derive structure ad hoc and drift would never be reconciled. It earns its keep by concentrating "keep the picture of what is true" in exactly one place.
