---
name: code
description: Execute an already-chosen deepening into source — refactor a shallow cluster into one deep module, build new code to a planned interface so it is deep from the start, or write interface tests for a test-first target the signal scan named. Use when the user says "refactor this into a deep module", "implement this interface", "merge these pass-throughs", "execute the accepted candidate", "build this work step", or "write the tests for this module". This is the ONLY Fathom skill that edits source; it reconciles the modules it touched on the arch-map spine. Do NOT use to decide WHETHER to deepen or to grill a candidate (that is fathom:deepen) or to design a target structure from scratch (that is fathom:plan) — code executes a target the spine already holds. Skip for read-only mapping (fathom:map) or pure ADR capture (adr-writer).
---

# Execute a Deepening

fathom:code is the suite's hands — the **only** skill that edits source. It takes a target that another skill already chose and makes the code match it, so the result is a **deep module**: a large amount of behaviour behind a small interface. It never invents what to build. The target comes from the arch-map spine — an accepted deepening **candidate** (`decision == "accepted"`) on an existing shallow module, or a planned WorkStep whose intended module already carries the interface and seam fathom:plan designed.

## Glossary

Speak these exactly — never "component," "service," "API," or "boundary." Full definitions in [../fathom/LANGUAGE.md](../fathom/LANGUAGE.md).

- **Module** — anything with an interface and an implementation (function, class, package, tier-spanning slice).
- **Interface** — everything a caller must know: types, invariants, ordering, error modes, required config, performance. Not just the type signature.
- **Depth** — leverage at the interface: a lot of behaviour behind a small interface. **Deep** = high leverage; **shallow** = interface nearly as complex as the implementation.
- **Seam** — where an interface lives; a place you can alter behaviour without editing in place.
- **Adapter** — a concrete thing satisfying an interface at a seam.

Principles this skill enforces while it works:

- **The interface is the test surface.** The chosen interface is both what you build to and the only place your tests assert. A test that must reach *past* the interface is the signal the seam is wrong — hand back rather than paper over it.
- **One adapter = hypothetical seam. Two adapters = real seam.** Only introduce a port where two adapters are actually justified (production + test). A single-adapter seam is mere indirection — don't add it.
- **Replace, don't layer.** Tests that exercised the absorbed pass-throughs become waste once the interface is tested. Delete them; write tests at the new interface.

## The candidate is the only word that matters

"Candidate" is the user-facing word for a Suggestion on the spine. fathom:code does **not** create candidates and does **not** decide whether one is worth doing — it executes one that is already accepted (or a WorkStep that fathom:plan already sequenced). The spine is the handoff medium: every tool takes the named `map` as its first argument, and the map is shared and file-backed, so what you write is what the next session reads.

## Process

### 1. Bootstrap the map and pick up the marching order

The map is shared and file-backed. Resolve it before anything else:

- `archmap_list_maps()` → find this repo's map id. If there is none, the repo isn't mapped — STOP and hand to **fathom:map** to seed it; fathom:code does not seed. (If you truly need a fresh project: `archmap_create_map(name)` returns the `map` id.)
- Thread the returned `map` id through every later call.

Then read the target the spine holds — never invent one:

- `archmap_get_full_model(map)` to see the whole picture, then `archmap_modules(map, action="get", id=module)` for the specific target.
- **Mode (a) REFACTOR** — an accepted candidate: a Suggestion with `decision == "accepted"` on a shallow module. Read its `category`, `problem`, `solution`, `wins`. The `category` drives the seam strategy in step 4.
- **Mode (b) BUILD** — a planned WorkStep: `archmap_plans(map, action="get", plan_id=)` for the ordered steps; the step names its `targets` (intended module ids, `plane == "intended"`, `lifecycle == "planned"`), its `interface` (the test surface), `dependsOnSteps`, and `adapters` (the dependency category + which adapters). Take the **next** step whose dependencies are `done`.
- **Mode (c) TEST-FIRST** — a module the signal scan names and the user asks to see tested: `archmap_scan_signals(map, "test-first")` returns them worst-first. The target is the module's recorded `iface` — write interface tests ONLY, no refactor in the same pass (a refactor needs its own grilled candidate). The recorded interface is the contract to assert: types, invariants, ordering, error modes. If the interface prose is too thin to test against, that is itself the finding — hand to **fathom:map** to sharpen the record first.

If there is **no** accepted candidate, **no** planned WorkStep, and **no** explicit test-first ask, STOP. Hand back to **fathom:deepen** (to grill and accept a candidate) or **fathom:plan** (to design and sequence one). fathom:code chooses nothing.

### 2. Read the constraints that bound the execution

- Skim the relevant entries in `docs/adr/` for the area, and the project's domain terms in `CONTEXT.md` / `CONTEXT-MAP.md` (so the module you produce is named in domain vocabulary, not "FooBarHandler").
- If the chosen target **contradicts an accepted ADR**, STOP and surface the conflict. Offer **adr-writer** to revisit the decision. Do not quietly override an ADR.

### 3. Confirm the interface and seam — do not redesign

The target already carries them: for an accepted candidate the `solution` text names the interface and where the seam sits; for a WorkStep the intended module's `iface` and `seam` carry them. Restate the interface in [../fathom/LANGUAGE.md](../fathom/LANGUAGE.md) terms — the full contract: types, invariants, ordering, error modes, config, performance — so it is testable.

If the interface is genuinely underspecified or wrong, do **not** design a new one here. Hand back: **fathom:plan** for system-level redesign, **fathom:deepen** for alternative-interface exploration (its INTERFACE-DESIGN loop). fathom:code executes a chosen interface; it does not run design-it-twice.

### 4. Establish the safety net before moving any code

Tests describe behaviour, not the current shape, so they survive the refactor and define "done."

- **Mode (a):** confirm characterization tests exist for the cluster's current observable behaviour. **If the shallow cluster is untested, writing those characterization tests is in scope** — fathom:code is the only skill that can, and a refactor without a net is unsafe. Write them at the cluster's *current* observable behaviour, run them green, then refactor under them.
- **Mode (b):** write the interface tests **first**, against the planned contract. They fail until the module exists; that is the spec.

Run the net green before touching implementation (mode a) or use it red→green to drive the build (mode b).

### 5. Execute by dependency category

Place the seam by the candidate's / WorkStep's category. Use the four [../fathom/DEEPENING.md](../fathom/DEEPENING.md) categories verbatim:

- **In-process** — pure computation, in-memory state, no I/O. Merge the modules and test through the new interface directly. **No adapter.**
- **Local-substitutable** — dependencies with a local test stand-in (PGLite for Postgres, in-memory filesystem). Keep the seam **internal**; run the stand-in in the test suite. No port at the module's external interface.
- **Remote but owned (Ports & Adapters)** — your own services across a network. Define a **port** at the seam; the deep module owns the logic, the transport is an injected **adapter**. Implement an HTTP/gRPC/queue adapter for production and an in-memory adapter for tests — two adapters, so the seam is real.
- **True external (Mock)** — third-party services you don't control (Stripe, Twilio). Take the dependency as an injected port; tests supply a mock adapter.

Move complexity behind the small interface; merge the pass-throughs; keep observable behaviour identical at every step. Only introduce a port where two adapters are genuinely justified — otherwise it is indirection, not a seam.

### 6. Migrate the tests: replace, don't layer

- **Delete** the unit tests that exercised the now-absorbed pass-throughs. They are waste once the interface is tested.
- Keep/add tests that assert observable outcomes **across the new interface** — the interface is the test surface.
- If a test has to reach *past* the interface to assert, the module is the wrong shape. Re-examine the seam before continuing; if the seam genuinely leaks, hand back to fathom:plan or fathom:deepen rather than forcing it.

### 7. Verify through the interface

Run the full suite at the interface. For mode (a), confirm behaviour is unchanged; for mode (b), confirm the planned contract holds. The interface tests passing **is** the verification — there is no separate "does it still work" check past the seam.

### 8. Reconcile ONLY what you touched

fathom:code persists what *it* changed; it does not re-derive the whole graph. The broad sweep — orphan recomputation, re-deriving modules you didn't touch, the periodic honesty pass — belongs to **fathom:map**. Reconcile the directly-touched modules and their immediate edges, then stop.

**Mode (a) — refactor:**
- `archmap_modules(map, action="update", id=module, depth=<new higher score>)` on the survivor — complexity now sits behind a small interface, so it is deeper.
- `archmap_modules(map, action="update", id=module, coverage=<fraction>)` to record interface coverage after the test migration.
- Collapse the absorbed pass-throughs: `archmap_modules(map, action="update", id=module, files=[...], dependsOn=[...], iface="...", tests="...")` on the survivor, and `archmap_modules(map, action="delete", id=<pass-through id>)` for each absorbed node (this prunes dangling edges). Re-point any `dependsOn` that referenced the old nodes to the survivor.
- `archmap_suggestions(map, action="decide", suggestion_id=, decision="accepted", note=)` then `archmap_suggestions(map, action="dismiss", suggestion_id=)` to close the executed candidate. Both keep the candidate as the durable record (the `archmap_suggestions` tool with `action="dismiss"` sets status `done`, it does not delete it).

**Mode (b) — build:**
- `archmap_modules(map, action="realize", id=module, depth=<achieved>, coverage=<fraction>, files=[...])` — flips the intended module from `plane="intended"`/`lifecycle="planned"` to `plane="actual"`/`lifecycle="built"` and records what landed. This is the single legible "it's real now" transition; fathom:code owns it.
- `archmap_plans(map, action="set_step_status", plan_id=, step_id=, step_status="done")` to close the WorkStep (use `"in-progress"` when you start, `"blocked"` if it can't proceed).

**Mode (c) — test-first:**
- `archmap_modules(map, action="update", id=module, coverage=<fraction>, tests="<where the new interface tests live>")` on the tested module — and nothing else. Depth, edges, and files are untouched; only the coverage fact changed.

**All modes:** `archmap_modules(map, action="update", id=module, updated=true)` so the survivor/built node shows as changed since the last scan. Add the new/changed source files to the module's `files` list so the spine reflects what exists. Then stop — leave the rest to fathom:map.

### 9. Keep domain language honest

- If the deepened/new module is named after a concept **not** in `CONTEXT.md`, add the term (same discipline as [../fathom/CONTEXT-FORMAT.md](../fathom/CONTEXT-FORMAT.md); create the file lazily). If execution sharpened a fuzzy term, update it there.
- If execution surfaced a **load-bearing, hard-to-reverse** decision (a chosen seam placement that locks in a technology, an integration shape), **offer adr-writer** — framed as: _"Want me to record this as an ADR so future reviews don't re-litigate it?"_ Do not write the ADR inline; adr-writer is the sole writer of `docs/adr/NNNN`. Use the [../fathom/ADR-FORMAT.md](../fathom/ADR-FORMAT.md) three tests (hard to reverse, surprising, real trade-off); skip ephemeral and self-evident reasons.

### 10. Hand off

Report what landed: the files changed, the new depth/coverage on the map, and which candidate or WorkStep is now resolved.

- After a large change, point to **fathom:map** to re-verify the whole model is still accurate (you reconciled only your nodes; the broad sweep is its job).
- If verification revealed the **chosen target was wrong** — the seam leaks, the interface forces tests past it — hand back to **fathom:plan** (system-level redesign) or **fathom:deepen** (re-grill / explore alternative interfaces) rather than redesigning here.
- If a load-bearing decision wants recording, hand to **adr-writer**.

## Boundaries

fathom:code MUST NOT:

- **Decide whether to deepen, or grill/accept a candidate** — that is fathom:deepen. It executes a candidate already `accepted`.
- **Design the target module graph, seams, or interfaces from scratch** — that is fathom:plan. design-it-twice / INTERFACE-DESIGN belongs to fathom:plan and fathom:deepen; code only recognises "interface underspecified" and hands back.
- **Seed or reconcile the whole model of what exists** — that is fathom:map. code reconciles only the modules it directly touched.
- **Author ADRs inline** — it offers adr-writer.
- **Override an accepted ADR** — on conflict it stops and surfaces it.
- **Proceed without a chosen target** — with no accepted candidate and no WorkStep it hands back rather than inventing one.
- **Test past the interface** — if a test must reach behind the seam, that is the signal the target is wrong; hand back.
