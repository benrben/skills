---
name: plan
description: Design the intended architecture for a new feature or a significant change BEFORE writing code — decide what deep modules should exist, where the seams go, and exactly what each interface must promise (types, invariants, error modes, ordering, config), then record that intended structure on the arch-map and sequence it into build steps. Use when starting a feature, a rewrite, or a non-trivial change and you want the module graph designed up front, want to "design it twice" / compare interface options, or want the intended structure on the map before building. Do NOT use to find or fix friction in EXISTING shallow modules (that is fathom:deepen — plan designs structure that does not exist yet). Do NOT use to seed or reconcile a map of what already IS (that is fathom:map). Do NOT use to write or refactor source (that is fathom:code) — plan stops at the design and the sequenced hand-off.
---

# Design Intended Architecture

Turn a feature or change request into an **intended deep-module graph** — which modules should exist, where the seams sit, and what each interface must promise — and record it on the shared arch-map *before any code is written*. The output is a design plus a build order, not source.

This skill makes **depth a design-time decision** instead of an after-the-fact rescue. Its job is to place seams and shape interfaces so each module is deep from birth — a lot of behaviour behind a small interface — rather than letting shallow modules accrete and waiting for `fathom:deepen` to consolidate them later. It treats the **interface as the test surface** up front, so the design it ships *is* the test plan `fathom:code` inherits.

## Vocabulary — speak it exactly

Use the shared architecture vocabulary in [../fathom/LANGUAGE.md](../fathom/LANGUAGE.md) and nothing else. Never say "component," "service," "API," or "boundary."

- **Module** — anything with an interface and an implementation; scale-agnostic (a function, a class, a package, a tier-spanning slice).
- **Interface** — *everything* a caller must know: type signature, invariants, ordering constraints, error modes, required configuration, performance characteristics. Not just the type signature.
- **Depth** — leverage at the interface: a lot of behaviour behind a small interface. **Deep** = high leverage; **shallow** = interface nearly as complex as the implementation.
- **Seam** — where an interface lives; a place behaviour can be altered without editing in place.
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Leverage** (what callers get) and **Locality** (what maintainers get) — both are products of depth.
- **Deletion test** — imagine deleting the module: if complexity *concentrates* behind a small interface it was deep; if it just moves a pass-through around, it was shallow.
- **The interface is the test surface.** **One adapter = hypothetical seam; two adapters = a real one.**

Name modules and seams in the project's **domain vocabulary** from `CONTEXT.md` (the "Order intake module," not the "FooBarHandler"). Domain names label good seams; `LANGUAGE.md` labels the architecture.

## The two planes

The arch-map holds two planes. `plan` writes only the **intended** plane.

- `plane = "actual"` — what the code IS today (seeded and reconciled by `fathom:map`; realized by `fathom:code`). **`plan` never writes the actual plane.**
- `plane = "intended"` — what you WANT to build. Every module `plan` records is `plane="intended"`, `lifecycle="planned"`, `coverage` 0, with `intendsToDependOn` edges and a `supersedes` list naming the actual modules it will replace.

`lifecycle` is the per-module build state: `"planned"` → `"building"` → `"built"`. `plan` seeds modules at `"planned"`; only `fathom:code` advances them (via `archmap_modules` with `action="realize"`). Leave `coverage` at 0 and never call `archmap_modules` with `action="update"` to mark an intended module updated — those are claims of *built* work, and tripping them would make a planned node look like real, drifting source.

## Process

### 1. Frame the change

Read the project's `CONTEXT.md` (or `CONTEXT-MAP.md` to pick the right context) and any ADRs in `docs/adr/` that touch the area. Restate the request as **what behaviour must exist** and **what must NOT change**. Name the relevant concepts in `CONTEXT.md` terms; if the work introduces a genuinely new domain concept, note it for a `CONTEXT.md` addition later ([../fathom/CONTEXT-FORMAT.md](../fathom/CONTEXT-FORMAT.md)). Treat recorded ADRs as **constraints**, not invitations to re-litigate — only reopen one with an explicit, surfaced reason.

### 2. Locate the change on the existing map

`plan` designs into a real codebase, not a vacuum — the intended graph must connect to what already IS. Resolve the project's map and load the actual structure the new work plugs into:

```
archmap_list_maps()                       # find this project's map (resume) — or archmap_create_map(<human name>) -> {map}
archmap_show_map(map)                     # the lightweight network view
archmap_get_full_model(map)              # the full model when you need every interface/seam
archmap_modules(map, action="get", id=<id>)   # inspect a specific actual module's interface you'll depend on
```

Thread the returned `map` id through *every* later call. Identify which **actual** modules the new work touches, depends on, or sits beside. If the repo isn't mapped yet, **stop and hand to `fathom:map`** to seed it — `plan` consumes an accurate map, it does not build one. (You may also read open candidates with `modules` (`action="get"`) to avoid designing around something `fathom:deepen` is about to reshape — but `plan` never creates or decides candidates.)

### 3. Design the module graph twice (system level)

Your first decomposition is unlikely to be the best. Sketch **at least two alternative decompositions** of the work into deep modules that differ in a load-bearing way:

- different **seam placement** (where the interface sits),
- different **module counts** (one deep module vs. several),
- different things **hidden behind each interface**.

Compare them in prose on:

- **depth** — how much behaviour each interface hides per unit a caller must learn;
- **leverage** — does one implementation pay back across many callers and tests;
- **locality** — where future change concentrates;
- **testability** — can each module be exercised entirely *through its interface*.

Apply the **deletion test** to every proposed module *on paper*, where pass-throughs are free to kill: would deleting it concentrate complexity, or just move it? **Reject any decomposition that produces shallow modules.** Make an opinionated call.

### 4. Specify each interface as a promise — and as the test surface

For every intended module, write down the full interface: type signature, invariants, ordering constraints, error modes, required configuration, performance characteristics. State explicitly that **this is the test surface** — the assertions `fathom:code` will write and the only place its tests cross. If a planned interface forces a test to reach *past* it to assert, the module is the wrong shape; revisit the seam now.

Where an existing deep module — stdlib, the platform, or an installed dependency — already does what sits behind a seam, **name it in the interface spec** so `fathom:code` delegates rather than hand-rolling it ([../fathom/MINIMALISM.md](../fathom/MINIMALISM.md)). Designing the seam to wrap a library you already have keeps `depth` high and the implementation small from line one.

For the **load-bearing module(s)** — the ones the rest of the design pivots on — run **design-it-twice at the interface level** by absorbing [../fathom/INTERFACE-DESIGN.md](../fathom/INTERFACE-DESIGN.md):

1. **Frame the problem space** for the user: the constraints any interface must satisfy, the dependencies it relies on and their category (step 5), and a rough illustrative sketch to ground the constraints (not a proposal).
2. **Spawn 3+ parallel sub-agents** (Agent tool), each producing a *radically different* interface for the same intended module — e.g. *minimise the interface* (1–3 entry points, maximise leverage each), *maximise flexibility/extension*, *optimise the common caller* (trivial default case), *ports & adapters* for cross-seam dependencies. Brief each in `LANGUAGE.md` + `CONTEXT.md` vocabulary. Each returns: the interface (types, invariants, ordering, error modes), a usage example, what's hidden behind the seam, the dependency strategy and adapters, and the trade-offs.
3. **Present sequentially, then compare in prose** by depth / locality / seam placement, and give an **opinionated recommendation** (or a hybrid). The user wants a strong read, not a menu.

### 5. Decide the seam strategy per dependency

Classify **each cross-seam dependency** by its [../fathom/DEEPENING.md](../fathom/DEEPENING.md) category, so the adapter story is settled before code. Use these four category names verbatim:

1. **In-process** — pure computation / in-memory state, no I/O. No adapter; the module is tested directly through its interface.
2. **Local-substitutable** — a local test stand-in exists (PGLite for Postgres, in-memory filesystem). The seam stays **internal**; no port on the module's external interface — the stand-in runs in the test suite.
3. **Remote but owned (Ports & Adapters)** — your own services across a network. Define a **port** at the seam; the deep module owns the logic, the transport is an injected adapter (HTTP/gRPC/queue in production, in-memory for tests).
4. **True external (Mock)** — third-party services you don't control. Inject a port; tests provide a mock adapter.

Apply seam discipline: **only introduce a port where at least two adapters are justified** (typically production + test). One adapter is a hypothetical seam — mere indirection. Keep internal seams internal; don't leak them through the chosen interface.

### 6. Record the chosen structure on the map as INTENDED

Add the picked modules as `plane="intended"`, `lifecycle="planned"`, `coverage=0`, `depth` set to the intended deep value, each `supersedes`-ing the actual module(s) it will replace, wired with `intendsToDependOn` edges (intended edges, distinct from the actual `dependsOn` graph). Use `archmap_modules` with `action="add"` so the intended-plane fields pass through `Module.from_dict`:

```
archmap_modules(map, action="add", items=[
  {"id": "order-intake", "label": "Order intake", "domain": "orders",
   "plane": "intended", "lifecycle": "planned", "depth": 0.8, "coverage": 0.0,
   "seam": "<where the interface lives>",
   "iface": "<the full promise: types, invariants, ordering, error modes, config — this is the test surface>",
   "tests": "<the intended test surface fathom:code inherits>",
   "supersedes": ["legacy-order-handler", "order-validator"],
   "intendsToDependOn": ["pricing-engine"]}
])
```

Then create the **Plan** and connect the intended modules to it:

```
archmap_plans(map, action="create", plan_id="orders-rework", title="Order intake rework",
            domain="orders",
            intent="<1–3 sentences naming the intended deep structure; record rejected decompositions here so later runs don't re-propose them>",
            moduleIds=["order-intake", ...])
```

Leave `coverage` 0 and never call `archmap_modules` with `action="update"` to mark these nodes updated — `fathom:code` sets real depth/coverage and advances `lifecycle` when it builds them. Do **not** touch the actual-plane `depth`/`coverage`/`dependsOn`/`leaksTo` of existing modules, and never write `leaksTo` on an intended node — a leak is an as-is defect, never a plan target.

### 7. Sequence the work into ordered build steps

Produce an ordered list where **each step hands ONE intended module** to `fathom:code` — its interface (test surface), seam, and dependency category — in dependency order: leaf/deepest modules first, callers after, **ports before their adapters**. Record the sequence on the map so `fathom:code` can resume it across sessions:

```
archmap_plans(map, action="add_steps", plan_id="orders-rework", steps=[
  {"id": "s1", "title": "Build pricing-engine port + adapters",
   "targets": ["pricing-engine"],
   "interface": "<the test surface to assert at>",
   "adapters": "Remote but owned — in-memory adapter for tests, HTTP adapter for production",
   "dependsOnSteps": [], "note": "<anything fathom:code must honour>"},
  {"id": "s2", "title": "Build order-intake on top of pricing-engine",
   "targets": ["order-intake"], "interface": "...",
   "dependsOnSteps": ["s1"]}
])
```

Each step must be self-contained enough that `fathom:code` can build it **deep from line one** and assert at its interface. Inspect the result with `archmap_plans(map, action="get", plan_id="orders-rework")` and `plans` (`action="set_step_status"`) only if you need to mark a step (status is otherwise `fathom:code`'s to advance: `todo` → `in-progress` → `done` | `blocked`).

### 8. Offer ADRs and hand off

For each structural choice that passes the three gates in [../fathom/ADR-FORMAT.md](../fathom/ADR-FORMAT.md) — **hard to reverse**, **surprising without context**, and the result of a **real trade-off** — offer to record an ADR (e.g. a chosen seam placement, a port-vs-direct-call decision, an event-vs-synchronous integration between contexts). Frame it as a hand-off; `plan` does **not** write the ADR itself — the sole writer of `docs/adr/NNNN-slug.md` is `adr-writer`, which also links the ADR back into the spine.

If you named a genuinely new domain concept, add the term to `CONTEXT.md` ([../fathom/CONTEXT-FORMAT.md](../fathom/CONTEXT-FORMAT.md) discipline; create the file lazily).

Then hand the sequenced plan to **`fathom:code`** to execute. State the headline: the intended modules, what each supersedes, the build order, and any ADRs offered. `plan` stops at the design and the hand-off — it never edits source.

## Spine interaction

| Call | Read / Write | Why |
| --- | --- | --- |
| `archmap_list_maps()` / `archmap_create_map(name)` | bootstrap | Find or create the project's shared map; thread the returned `map` id everywhere. |
| `archmap_show_map(map)` / `archmap_get_full_model(map)` / `archmap_modules(map, action="get", id=...)` / `archmap_modules(map, action="get", ids=[...])` | READ | Load the actual graph the new work plugs into; inspect interfaces it depends on. |
| `archmap_modules(map, action="add", items=[...])` (or `action="add"` with a single `id=`) | WRITE — intended modules | Seed `plane="intended"`, `lifecycle="planned"`, `coverage=0`, with `iface`/`seam`/`tests`, `supersedes`, `intendsToDependOn`. |
| `archmap_modules(map, action="update", id=...)` | WRITE — intended interface text | Patch `iface`/`seam`/`tests`/`intendsToDependOn` on an intended node as the design firms up. |
| `archmap_plans(map, action="create", plan_id, title, domain, intent, moduleIds)` | WRITE — Plan | Record the intended structure as a resumable Plan; capture rejected alternatives in `intent`. |
| `archmap_plans(map, action="add_steps", plan_id, steps)` | WRITE — WorkSteps | The ordered, dependency-respecting build sequence `fathom:code` executes. |
| `archmap_plans(map, action="get", plan_id)` | READ | Confirm the recorded plan + step order. |

**`plan` does NOT call:** `suggestions` (`action="flag"` / `action="decide"` / `action="dismiss"`) / `grilling` (`action="start"` / `action="finish"`) (the candidate lifecycle owned by `fathom:deepen`); `archmap_modules` with `action="update"` (to set `depth`/`coverage` or mark updated) or `action="realize"` on actual modules, and never advances `lifecycle` (those are `fathom:code`'s — `plan` leaves intended nodes at `planned`, `coverage` 0); `archmap_modules` with `action="delete"` / `action="update"` against the **actual** plane. It writes only the intended plane and the Plan/WorkStep entities.

## Hand-offs

**To:**

- **`fathom:code`** — the ordered build sequence; each WorkStep is one intended module with its interface (test surface), seam, and dependency category. `code` is the only source-editing skill and the only one that flips a module `planned → building → built`.
- **`adr-writer`** — load-bearing structural choices (seam placement, port-vs-direct, integration pattern) offered as ADRs.
- **`fathom:deepen`** — once intended modules are built, `deepen` takes over keeping their depth honest over time.
- **`fathom:map`** — back, when step 2 finds the repo isn't mapped (or the map is stale) and the design needs an accurate baseline first.

**From:**

- **`fathom:map`** — hands over an accurate actual-model so the intended graph designs into real structure.
- **`fathom:deepen`** — when deepening an existing cluster turns out to need genuinely *new* structure (a new module/seam, not just consolidation), `deepen` hands the design problem here.
- **`adr-writer`** — a recorded constraint or a decision to build something new can kick off a planning pass.

## What `plan` does NOT do

- **Does NOT find or fix friction in EXISTING shallow modules** — that is `fathom:deepen`. The tell: if every module in the discussion already has files on the actual plane, it's `deepen`; if any target module is to-be-built, it's `plan`.
- **Does NOT seed a repo into the map or reconcile drift** — that is `fathom:map`. `plan` consumes an accurate map; it doesn't build or correct one.
- **Does NOT edit, write, or refactor any source or test file** — the only skill that touches source is `fathom:code`. `plan` stops at the design and the sequenced hand-off.
- **Does NOT create deepening candidates (`archmap_suggestions` with `action="flag"`) or decide/resolve them** — that surface belongs to `fathom:deepen`.
- **Does NOT set real depth/coverage, mark modules updated, or realize a module** — it leaves intended modules at `coverage` 0 / `lifecycle="planned"` for `fathom:code`.
- **Does NOT write ADRs** — it *offers* them and hands to `adr-writer`, the sole writer of `docs/adr/`.
- **Does NOT re-litigate recorded ADRs** — it reads them as constraints and only reopens one with an explicit, surfaced reason.

## Reference docs

- [../fathom/LANGUAGE.md](../fathom/LANGUAGE.md) — the only vocabulary every step may use.
- [../fathom/INTERFACE-DESIGN.md](../fathom/INTERFACE-DESIGN.md) — the design-it-twice sub-routine absorbed in step 4 (parallel sub-agents → prose comparison → opinionated recommendation).
- [../fathom/DEEPENING.md](../fathom/DEEPENING.md) — the four dependency categories and seam discipline used to settle the adapter/port strategy before code.
- [../fathom/CONTEXT-FORMAT.md](../fathom/CONTEXT-FORMAT.md) — how to name intended modules in domain terms and add a new concept lazily.
- [../fathom/ADR-FORMAT.md](../fathom/ADR-FORMAT.md) — the three gates (hard to reverse, surprising, real trade-off) for offering an ADR.
- `../fathom/arch-map/README.md` + `arch-map/arch_map/server.py` — the spine tools and Module/Plan/WorkStep fields `plan` writes.
