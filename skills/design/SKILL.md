---
name: design
description: Decide the deep-module structure for a change — in ONE skill, two modes by request. IMPROVE mode finds friction in EXISTING shallow modules, flags a deepening candidate, and grills it to accepted/deferred/rejected. NEW mode designs the intended deep-module graph for new or changing work (seams, interfaces design-it-twice, dependency categories) and sequences it into build steps. Records the decision on the spine as docs (rfc → adr · spec · diagram), candidates, intended modules, and Plans — all spine-only, no files. Use when the user wants to improve architecture, consolidate shallow modules, design a new feature's structure, or compare interface options before code. Do NOT use to seed or reconcile the map of what IS (fathom:map), to edit source (fathom:code), or to gate a diff (fathom:review). design decides WHAT should exist and grills HOW; it never writes source.
---

# Design — Decide the Deep Structure

`design` is the suite's decider. It turns a request into a **target**: either a deepening of existing shallow modules, or an intended deep-module graph for new work — then records that target on the spine for `fathom:code` to build. It is the merge of the old `deepen` (improve what is) and `plan` (design what will be): same output (a target + sequenced steps + the decision docs that justify it), one grilling rigor, two entry modes. It does not seed or reconcile the actual plane (that is `fathom:map`), edit source (`fathom:code`), or gate a diff (`fathom:review`).

## Glossary

Speak these exactly — never "component," "service," "API," or "boundary." Full definitions in [../../fathom/LANGUAGE.md](../../fathom/LANGUAGE.md).

- **Module** — anything with an interface and an implementation; scale-agnostic (function, class, package, tier-spanning slice).
- **Interface** — everything a caller must know: types, invariants, ordering, error modes, required config, performance. Not just the signature.
- **Depth** — leverage at the interface: a lot of behaviour behind a small interface. **Deep** = high leverage; **shallow** = interface nearly as complex as the implementation.
- **Seam** — where an interface lives; a place behaviour can be altered without editing in place.
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Leverage** (what callers get) and **Locality** (what maintainers get) — both products of depth.

Principles this skill enforces:

- **Deletion test** — imagine deleting the module: complexity *concentrates* behind a small interface (deep) or just moves a pass-through around (shallow). A "concentrates" is the signal to act.
- **The interface is the test surface.** The interface you choose is the only place `fathom:code` will assert.
- **One adapter = hypothetical seam. Two adapters = real seam.**

## The two planes and the docs

The spine holds two planes; `design` writes only the **intended** plane (and candidates against the actual plane), never the actual modules themselves.

- `plane="actual"` — what the code IS (owned by `fathom:map`; realized by `fathom:code`).
- `plane="intended"` — what you WANT: `lifecycle="planned"`, `coverage` 0, `intendsToDependOn` edges, `supersedes` naming the actual modules it replaces.

Docs are **spine-only** (no files — see [../../fathom/DOC-TYPES.md](../../fathom/DOC-TYPES.md)). `design` is the writer of the decision and contract docs:

- **rfc** — a proposal still open ("should we?"). Optional, for a genuinely contested decision.
- **adr** — the decision made: choice + why + rejected alternative, gated by the three tests (hard to reverse · surprising without context · real trade-off).
- **spec** — a module's interface contract in prose: types, invariants, errors, ordering, config, acceptance. The persisted design→code hand-off.
- **diagram** — a Mermaid picture of the intended structure or flow, scoped to the modules it covers.

`design` does not author `glossary`/`note`/`risk`/`runbook`/`postmortem` (that is `fathom:map`, the doc registrar) — though it may attach a `note` to a candidate.

## Resolve the map first

The map is shared and file-backed; thread its `map` id through every call.

```
archmap_list_maps()                    # find this project's map (resume) — capture its id
archmap_show_map(map)                  # the network digest; shallow nodes, leaks, thin coverage
archmap_get_full_model(map)            # full interfaces/seams/tests/candidates when you need them
```

If the repo isn't mapped, **STOP and hand to `fathom:map`** to seed it — `design` consumes an accurate baseline, it never builds one. Read the project's `glossary` docs (domain vocabulary) and any `adr` docs in the area off the spine, so you name modules in domain terms and treat recorded decisions as **constraints**, not invitations to re-litigate.

## Branch on the request

- The discussion is about modules that **already exist** and feel shallow / leaky / hard to test → **IMPROVE mode**.
- The work is **to-be-built** (a new feature, a rewrite, a new seam) → **NEW mode**.

Both modes end the same way: a target on the spine + sequenced build steps + the decision docs, handed to `fathom:code`.

---

## IMPROVE mode — deepen what exists

### 1. Find the friction

Start from the map's shallow nodes, leak edges, and thin-coverage rings, and the signal triage:

```
archmap_scan_signals(map)              # every module with a structural issue, worst-health first
archmap_scan_signals(map, "test-first")  # high blast-radius + low coverage — flag here first
```

Explore organically (Agent tool, `subagent_type=Explore`, if you need the code). Note where understanding one concept means bouncing between many small modules; where a module is shallow; where pure functions were extracted for testability but the bugs hide in how they're called (no locality); where seams leak; and where a module **hand-rolls what stdlib or a dependency already does** — large `size` for little `depth` (the `bulky-impl` signal; the deepening is *delegate behind the seam*, not merge — [../../fathom/MINIMALISM.md](../../fathom/MINIMALISM.md)). Apply the **deletion test** to each suspect.

### 2. Flag a candidate per real friction

```
archmap_suggestions(map, action="flag", module, title, strength,   # Strong | Worth exploring | Speculative
                    category,            # in-process | local-substitutable | ports & adapters | true external (DEEPENING.md)
                    problem, solution, wins=[...])
```

The id is derived as `f"{module}-{strength}"` (lower-cased, spaces dashed). Present the candidates, then ask which to grill. Do **not** propose interfaces yet, and do **not** re-baseline the actual plane's depth/coverage — if the map is stale about what IS, that's a `fathom:map` job.

### 3. Grill the chosen candidate

`archmap_grilling(map, action="mark", suggestion_id=…)`, then walk the design tree with the user: constraints, dependency category, the shape of the deepened module, what sits behind the seam, what tests survive. Pressure it — one adapter or two? Does the deletion test still hold at the call sites? Is the interface the test surface, or are you testing past it? Record the verdict:

- **Accepted / deferred** — `archmap_grilling(map, action="finish", suggestion_id=…, decision="accepted"|"deferred", note="…")`. An accepted candidate is the hand-off to `fathom:code`. A **deferred** candidate with a ceiling becomes a `ceiling` doc (the pre-registered deepening) — `fathom:code` writes that when it stops at a rung; here just note the trigger.
- **Rejected with a load-bearing reason** — `archmap_grilling(map, action="finish", suggestion_id=…, decision="rejected", note=reason, adr=<adr doc id>)`. Use `decision="rejected"` (keeps the durable "don't re-suggest" record), never a bare dismiss. If the reason passes the three gates, write an **adr doc** (step below) and pass its id as `adr=`.
- **Needs genuinely new structure** (not just consolidation) → switch to NEW mode for that piece.

---

## NEW mode — design what will be

### 1. Frame the change

Restate the request as **what behaviour must exist** and **what must NOT change**, in domain terms. Locate it on the map: which actual modules the work touches, depends on, or sits beside (`archmap_modules(map, action="get", id=…)` for interfaces you'll build on).

### 2. Design the module graph twice (system level)

Sketch **at least two** decompositions that differ in a load-bearing way — seam placement, module count, what each interface hides. Compare in prose on depth / leverage / locality / testability, run the **deletion test** on every proposed module on paper, and **reject any decomposition that produces shallow modules.** Make an opinionated call. A `diagram` doc of the chosen graph is the natural artifact here.

### 3. Specify each interface as a promise — and the test surface

For every intended module write the full interface: types, invariants, ordering, error modes, config, performance. State that **this is the test surface**; if it forces a test past the seam, the module is the wrong shape — revisit. Where an existing deep module (stdlib / platform / installed dep) already does what sits behind a seam, **name it** so `fathom:code` delegates rather than hand-rolls ([../../fathom/MINIMALISM.md](../../fathom/MINIMALISM.md)). Persist each interface as a **spec doc** scoped to its module.

For the **load-bearing** module(s), run design-it-twice at the interface level ([../../fathom/INTERFACE-DESIGN.md](../../fathom/INTERFACE-DESIGN.md)): frame the problem space, spawn 3+ parallel sub-agents each producing a *radically different* interface (minimise the interface / maximise flexibility / optimise the common caller / ports & adapters), then compare in prose and recommend opinionatedly.

### 4. Decide the seam strategy per dependency

Classify each cross-seam dependency by its [../../fathom/DEEPENING.md](../../fathom/DEEPENING.md) category — **in-process** (no adapter) · **local-substitutable** (internal seam, stand-in in tests) · **remote but owned / ports & adapters** (port + two adapters) · **true external / mock** (injected port, mock in tests). Only introduce a port where **two adapters** are genuinely justified; one adapter is indirection.

### 5. Record the intended structure on the map

```
archmap_modules(map, action="add", items=[
  {"id": "order-intake", "label": "Order intake", "domain": "orders",
   "plane": "intended", "lifecycle": "planned", "depth": 0.8, "coverage": 0.0,
   "seam": "<where the interface lives>",
   "iface": "<the full promise — the test surface>",
   "supersedes": ["legacy-order-handler"], "intendsToDependOn": ["pricing-engine"]}
])
archmap_plans(map, action="create", plan_id="orders-rework", title="Order intake rework",
              domain="orders", intent="<intended structure; record rejected decompositions here>",
              moduleIds=["order-intake", ...])
```

Leave `coverage` 0 and never mark an intended node `updated` — those are claims of *built* work that `fathom:code` makes. Never write `leaksTo` on an intended node (a leak is an as-is defect, never a plan target).

---

## Both modes — sequence, record the decision, hand off

### Sequence the work into ordered steps

Each step hands **one** target module to `fathom:code` — its interface (test surface), seam, dependency category — in dependency order (leaf/deepest first, ports before adapters):

```
archmap_plans(map, action="add_steps", plan_id="orders-rework", steps=[
  {"id": "s1", "title": "Build pricing-engine port + adapters", "targets": ["pricing-engine"],
   "interface": "<test surface>", "adapters": "ports & adapters — in-memory for tests, HTTP for prod",
   "dependsOnSteps": []},
  {"id": "s2", "title": "Build order-intake on pricing-engine", "targets": ["order-intake"],
   "interface": "...", "dependsOnSteps": ["s1"]}
])
```

(For IMPROVE mode a single accepted candidate is often the whole step — the `module`, its grilled interface, and category are the hand-off.)

### Record the decision as docs (spine-only)

When a choice passes the three gates — **hard to reverse · surprising without context · real trade-off** ([../../fathom/DOC-TYPES.md](../../fathom/DOC-TYPES.md)) — write an **adr** doc and scope it to the affected modules:

```
archmap_docs(map, action="add", doc_id="adr-orders-decoupled", type="adr",
             title="Keep ordering and billing decoupled",
             body="<context · decision · the alternative rejected and why it lost>",
             scope_kind="domain", scope_domain="orders")
```

Then point the candidate / plan at it via `adr=<doc_id>` (grilling finish) or the plan's `intent`. Skip the file gate that the old `adr-writer` carried — there are no `docs/adr/` files; the **adr doc on the spine is the record.** Use an **rfc** doc while a decision is still open, and flip it to an `adr` once grilled. Keep new domain concepts honest by updating the **glossary** doc (or hand the term to `fathom:map`).

### Hand off

State the headline: the target(s), what each supersedes (NEW) or which candidate is accepted (IMPROVE), the build order, and the decision docs written. Then:

- **`fathom:code`** — execute the sequenced steps / accepted candidate (the only source editor).
- **`fathom:map`** — back, if the baseline was stale and the design needs an accurate map first.

## Boundaries

`design` MUST NOT:

- **Seed or reconcile the actual plane** — that is `fathom:map`. It reads the actual plane and writes only intended modules, candidates, Plans, and rfc/spec/adr/diagram docs.
- **Edit, write, or refactor source** — that is `fathom:code`. It stops at the target and the sequenced hand-off.
- **Gate a diff** — that is `fathom:review`.
- **Author knowledge docs** (`glossary`/`note`/`risk`/`runbook`/`postmortem`) as registrar — that is `fathom:map`; design only attaches a `note` to its own candidate.
- **Re-litigate a recorded `adr` doc** — it reads them as constraints and reopens one only with an explicit, surfaced reason (a fresh `rfc`).

## Why this is a deep module

`design` concentrates *every "what should exist?" decision* behind one small interface — "improve this" or "build this" in, a target + sequenced steps + the docs that justify it out. The old split (deepen vs plan) forced the caller to know in advance whether the answer was a refactor of existing code or new structure — but that's exactly the thing being decided. Merging them puts the branch where it belongs (inside the skill) and keeps one grilling rigor for both. Delete `design` and the decision scatters: `map` would start recommending, `code` would start inventing targets, and the spine would hold structure nobody grilled.
