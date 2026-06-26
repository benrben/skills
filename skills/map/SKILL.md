---
name: map
description: Build and keep honest the model of what a codebase IS — its modules, their depth, edges, leaks, and interface coverage — AND capture the recorded truth around it as spine docs of every type (glossary, note, risk, runbook, postmortem, diagram, and the adr for a decision baked into the code). Finds all structural indicators (signals). The doc REGISTRAR of the suite, and the keeper of worktree truth — it syncs the task board's per-task git worktrees against real git on every reconcile. Use when onboarding a repo, running an architecture health check, reconciling drift after a merge, capturing decisions/notes/diagrams, or asking "what does this codebase actually look like." This skill models what EXISTS and records the truth about it — it never proposes deepenings or designs intended structure (that is fathom:design), and never edits source (fathom:code).
allowed-tools: Read Grep Glob Bash ReadMcpResourceTool ListMcpResourcesTool mcp__arch-map__*
---

# Map — Observe & Record What Is

`map` is the suite's surveyor and **doc registrar**. It turns a repository into an accurate, persistent model — modules, depth, edges, leaks, coverage, and **all** structural signals — and keeps that model honest over time. It also owns the spine's docs: it captures the recorded truth *around* the code as typed, module-scoped docs (glossary, note, risk, runbook, postmortem, diagram) and records the `adr` for a decision already baked into the code. Every other skill reads what `map` writes; if the map is wrong, they are all wrong — so accuracy is the whole job.

This skill absorbs the old `adr-writer`: there is no `docs/adr/` folder any more. Decisions, notes, vocabulary, runbooks, and diagrams all live **only on the spine** ([../../fathom/DOC-TYPES.md](../../fathom/DOC-TYPES.md)).

## Glossary

Speak only this vocabulary — never "component," "service," "API," or "boundary." Full definitions in [../../fathom/LANGUAGE.md](../../fathom/LANGUAGE.md).

- **Module** — anything with an interface and an implementation. Scale-agnostic: a single deep function and a whole slice can each be one node.
- **Interface** — everything a caller must know: types, invariants, ordering, error modes, required config. Not just the type signature.
- **Depth** — leverage at the interface. **Deep** = high leverage; **shallow** = interface nearly as complex as the implementation.
- **Seam** — where an interface lives; a place behaviour can be altered without editing in place.
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Leverage** (callers) / **Locality** (maintainers) — both products of depth.

Key principles:

- **Deletion test.** Imagine deleting the module. If complexity vanishes, it was a pass-through (shallow). If it reappears across N callers, it was earning its keep (deep). Every `depth` score is the recorded answer.
- **The interface is the test surface.** `coverage` is how much of the interface tests cross — not a line-count from a coverage tool.
- **One adapter = hypothetical seam. Two adapters = real seam.**

Modelling a module as shallow (low `depth`) is a **measurement, not a recommendation** to fix it — fixing is `fathom:design`'s job.

## What this skill writes — and what it must not touch

`map` writes two slices: the **actual-plane modules** (depth / coverage / edges / files / iface / seam / tests / updated) and the **doc registry** (every doc type). It reads everything else.

It MUST NOT:

- **Propose deepenings, flag or grill candidates, or design intended structure** — that whole lifecycle is `fathom:design`. The map models shallowness as the `depth` fact; it never recommends or designs the fix.
- **Edit, refactor, move, merge source, or change interfaces** — read-only against the repo. `fathom:code` is the only source editor.
- **Decide or resolve candidates** — it never touches the candidate/decision lifecycle.
- **Gate a diff** — that is `fathom:review`.
- **Run, build, or test the app** — `coverage` is a judgement about the interface test surface (an `archmap_ingest` coverage report sets the *measured* number; the interface judgement is still yours).

It DOES (new in v2) write `adr` docs — but only for a decision **already embedded in the code** that it discovers while mapping (the three-gate test below). It does **not** make new decisions; making them is `fathom:design`'s job, and `design` writes its own adr.

## The shared map

The spine is a shared, file-backed set of named maps (one per project). Bootstrap by resolving the map id and thread that `map` id through every call.

**Reads of stored state are MCP resources, not tools.** Read them with the built-in `ReadMcpResourceTool` against server `arch-map` and an `archmap://` uri (`ListMcpResourcesTool` enumerates them). Resources return **YAML** (compact — indentation, no JSON braces/quotes), and `archmap://{map}/doc/{id}` returns a **Markdown file** (frontmatter + body) you can read directly. Writes and computed queries stay `archmap_*` tool calls.

```
ListMcpResourcesTool(server="arch-map")                  # enumerate the archmap:// uris
ReadMcpResourceTool(server="arch-map", uri="archmap://maps")           # resume vs create
archmap_create_map("My Repo") -> {map}                   # capture the id (write = tool)
ReadMcpResourceTool(server="arch-map", uri="archmap://{map}/digest")   # digest: counts, domains, orphans, worst health
```

Reconcile is run explicitly — on a health check, after a big merge, or when someone asks "is the map still accurate."

## Process

### 1. Resolve the target map

Read `archmap://maps`, then **resume vs create**. Capture the `map` id. Read the spine's `glossary` docs (`archmap://{map}/docs?type=glossary`, then `archmap://{map}/doc/{id}` for a body) so module domains and labels use the project's vocabulary, and skim its `adr` docs (`archmap://{map}/docs?type=adr`) so you treat recorded decisions as **facts about what is** — never as things to challenge. (If a repo carries a legacy `CONTEXT.md`, read it as bootstrap input, then write the canonical vocabulary as `glossary` docs in step 7.)

If the map already exists, skip to **step 6 (Reconcile)**. A fresh map runs steps 2–5.

### 2. Seed — walk the real code (empty map only)

Dispatch **Explore subagents** (`subagent_type=Explore`) to walk the codebase organically — by directory, by domain, or by entry interfaces. Brief each in [../../fathom/LANGUAGE.md](../../fathom/LANGUAGE.md) + domain vocabulary and ask, per candidate module: the **files** that compose it, its **interface** (types, invariants, ordering, error modes, config), where the **seam** sits, the real **dependsOn** edges, any **leaksTo**, and existing **tests**.

### 3. Derive each module's fields by judgement, not formula

- **depth** (0–1) — the **deletion test**.
- **coverage** (0–1) — how much of the **interface** tests exercise.
- **size** — rough estimate; `archmap_ingest` overwrites it with measured LOC (median == 1.0).
- **dependsOn** — real edges only, by module id.
- **leaksTo** — seam violations (red edges).
- **iface / seam / files / tests** — prose + the file list. Use [../../fathom/DEEPENING.md](../../fathom/DEEPENING.md)'s categories only to *describe* an edge, never to propose a fix.

Record modules at the granularity that earns its keep (scale-agnostic).

### 4. Commit the model in bulk

```
archmap_modules(map, action="add", items=[ {id,label,domain, depth,size,seam,iface,coverage,files,dependsOn,leaksTo,tests}, ... ])
```

`id`/`label`/`domain` required. Add all nodes before relying on edges to render.

### 5. Inspect and find every indicator
> **Craft —** the indicator scan also runs the **craft** signal family (`archmap_scan_signals(map, family="craft")`) — long functions, too many args, duplication, dead code, magic numbers, untested interfaces — fed by `craft_ingest`. See [`../../fathom/craft/SMELLS.md`](../../fathom/craft/SMELLS.md).

```
ReadMcpResourceTool(server="arch-map", uri="archmap://{map}/digest")    # digest + worst health (resource)
archmap_render_view(map, of="orphans" | "low-coverage" | "leaks")      # diagnostic cuts (computed query)
archmap_render_view(map, kind="bar", metric="depth", group_by="domain")
archmap_scan_signals(map)                                              # ALL structural signals, worst-first
```

`archmap_scan_signals` is the indicator pass — surface **every** signal (danger-zone, critical-path-untested, circular-dep, needs-refactor, god-module, bottleneck, test-first, unstable-api, split-candidate, bulky-impl, leaky-seam), worst-first. Walk orphans and leaks with the maintainer: **an orphan is almost always a real edge you missed** — fix its `dependsOn`. Where the map disagrees with how the maintainer describes the system, **the map is wrong** — correct it with `archmap_modules(action="update", …)`.

### 6. Reconcile drift (resumed map)

Start with the drift report: `archmap_drift(map, root=<repo>)` names changed files and the modules they belong to — that IS the scope. `unmappedFiles` is the step-from-below worklist. `archmap_verify_edges(map, root=<repo>)` cross-checks recorded edges against real imports.

- **Per module in scope** — pull its record (`archmap://{map}/module/{id}`; bulk via `archmap://{map}/model`), re-walk its `files` (an Explore subagent if large), re-derive depth/coverage/dependsOn/leaksTo/iface/seam/tests (`archmap_modules(action="update")`).
- **Unowned files** — extend a module's `files` or add a new module.
- **Vanished files** — `action="delete"` (prunes edges); if a file merely moved, update `files` so hand-curated prose survives.
- **Clear the halos** — `archmap_modules(map, action="update", ids=["*"], updated=False)` once the scope matches reality.
- **Sync the worktrees** — `archmap_worktrees(map, action="sync", root=<repo>)` reconciles the task board's per-task branches against real `git worktree list`: refreshes each worktree's HEAD, and marks a vanished/merged one `status="removed"`. A drift that came in from a merged task branch is reconciled like any other (the worktree's recorded `base` is the `since_sha`); then retire the worktree (`action="remove"` or `prune`). map is the keeper of worktree truth — see [../../fathom/BOARD.md](../../fathom/BOARD.md).
- **Measure and anchor** — finish with `archmap_ingest(map, root=<repo>, coverage_report=<path if available>)`: churn from git, size from LOC, optional coverage, and the reconcile **anchor** (HEAD sha + snapshot) that drift and history read against.

### 7. Capture the docs — the registrar's job
> **Craft —** seed the project's craft conventions as `rule` docs from [`../../fathom/craft/`](../../fathom/craft/README.md) (naming, comments, tests, simple-design), and route *domain* names into the `glossary` doc ([`../../fathom/CONTEXT-FORMAT.md`](../../fathom/CONTEXT-FORMAT.md)).

`map` keeps the spine's doc set complete and accurate. Reading the code surfaces durable truth that belongs in docs ([../../fathom/DOC-TYPES.md](../../fathom/DOC-TYPES.md)); write/refresh them, each scoped to the modules it covers:

```
archmap_docs(map, action="add", doc_id="glossary-orders", type="glossary",
             title="Orders vocabulary", body="...", scope_kind="domain", scope_domain="orders")
```

- **glossary** — the project's domain vocabulary (the canonical home; supersedes any CONTEXT.md file). Follow the content discipline in [../../fathom/CONTEXT-FORMAT.md](../../fathom/CONTEXT-FORMAT.md) — tight definitions, project-specific terms, one glossary doc per domain.
- **note** — an observation worth keeping ("validate.py hand-rolls what pydantic does").
- **risk** — a hazard + mitigation + trigger, paired with a `danger-zone` / `test-first` signal you found in step 5.
- **runbook** — how to build / run / test / operate a module or the system.
- **postmortem** — what broke and the durable lesson (when one is reported to you).
- **diagram** — a **Mermaid** picture of the actual structure or a flow the node-graph can't show (a sequence, a data flow, a state machine), scoped to the modules it covers.

Refresh stale docs in place (`action="update"`); `supersedes` links a replacement to the old doc. Keep docs scoped tightly so they travel with their nodes in the studio.

### 7a. ADR mode — record a decision found in the code

When mapping surfaces a **decision already embedded in the code** — a seam placement that locks in a technology, an integration shape, a deliberate deviation from the obvious — record it as an `adr` doc **only if all three gates hold**: **hard to reverse**, **surprising without context**, **the result of a real trade-off** ([../../fathom/DOC-TYPES.md](../../fathom/DOC-TYPES.md)). Write a tight one-paragraph body — context, the decision, the alternative rejected and why it lost — and scope it to the affected modules:

```
archmap_docs(map, action="add", doc_id="adr-events-not-http", type="adr",
             title="Ordering and Billing talk via events, not HTTP",
             body="<one paragraph: context · decision · rejected alternative + why>",
             scope_kind="domain", scope_domain="orders")
```

Then point the affected modules at it via their `adrRef` (the doc id). If a gate fails, write nothing (or a plain `note`). **`map` records decisions it discovers; it does not make new ones** — a decision being *made now* (accepting a candidate, choosing a new design) is `fathom:design`'s adr to write.

### 8. Keep domain language honest, then hand off

If mapping surfaces a load-bearing concept the `glossary` docs don't name, add the term (step 7). Re-read `archmap://{map}/digest` and state the headline: deepest/shallowest domains, low-coverage and leak hot-spots, orphans resolved, docs captured. Then route — **without doing their jobs**:

- **Shallow clusters or new/changing work that need a target** → [fathom:design](../design/SKILL.md) (it proposes, grills, and designs).
- **Executing a refactor or build** → [fathom:code](../code/SKILL.md) (the only source editor).
- **Gating a diff** → [fathom:review](../review/SKILL.md).

`map` stops at an accurate picture of what is — plus the docs that record the truth around it. It does not recommend, design, decide-anew, or build.

## Why this is a deep module

`map` is the deletion test applied at repo scale, plus the single home of recorded truth. The whole codebase's structure *and* its docs (decisions, vocabulary, risks, runbooks, diagrams) sit behind one small interface — the spine's tools — so callers, human and skill, get **leverage** (read the map instead of re-deriving) and **locality** (one place to learn or correct the architecture and its rationale). Its seam is sharp: it writes the actual-plane modules and the doc registry, and reads everything else, composing with `fathom:design` (candidates, intended structure, decisions made now) and `fathom:code` (source) without overlap. Delete `map` and keeping the picture-of-what-is true becomes nobody's job — every sibling would re-derive structure ad hoc, drift would never reconcile, and the recorded truth would scatter back into stale files.

## Scripts — measure, don't guess

The map's measured fields and its initial skeleton come from bundled scripts, so the agent *curates facts* instead of authoring guesses. Run them; don't reason them.

- `scripts/seed.py <repo_root>` — cluster source into candidate modules with import-implied `dependsOn` (fast bootstrap of an empty map). Review, then commit keepers with `archmap_modules(action="add", items=[…])`.
- `scripts/measure.py <repo_root> <model.json>` — per-module **depthProxy** / **cohesion** / **ifaceSize** + the import-implied edges + a **depth-honesty diff** (judged `depth` vs the measured proxy). Feed the facts back with `archmap_modules(action="update")`; a large gap surfaces as the **`depth-overstated`** signal. (`<model.json>` = the `archmap://{map}/model` resource.)

These never replace the deletion-test judgement for `depth` — they give the agent a measured starting point and hold the judgement accountable.
