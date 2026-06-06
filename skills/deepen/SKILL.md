---
name: deepen
description: Find friction in a codebase's EXISTING shallow modules, present deepening candidates, and grill the chosen one until it's accepted, deferred, or rejected — turning shallow modules (interface ≈ as complex as the implementation) into deep ones for testability and AI-navigability. Reads an existing arch-map; records decisions and offers ADRs as they crystallize. Use when the user wants to improve architecture, find refactoring opportunities, consolidate tightly-coupled modules, or make a codebase more testable. Do NOT use for: seeding or reconciling the map of what the code IS (use fathom:map), designing the intended structure for new/changing work from scratch (use fathom:plan), or editing source to carry out a deepening (use fathom:code) — deepen decides WHETHER and grills HOW, it never writes source.
---

# Deepen

Surface architectural friction in **existing** modules and propose **deepening opportunities** — refactors that turn shallow modules into deep ones. The aim is testability and AI-navigability. `deepen` is the friction-finder of the Fathom suite: it reads the map of what the code *is*, flags candidates, and grills the chosen one to a decision. It does not build the map (that's **fathom:map**), design new structure (that's **fathom:plan**), or edit source (that's **fathom:code**).

## Glossary

Use these terms exactly in every suggestion. Consistent language is the point — don't drift into "component," "service," "API," or "boundary." Full definitions in [LANGUAGE.md](../fathom/LANGUAGE.md).

- **Module** — anything with an interface and an implementation (function, class, package, slice).
- **Interface** — everything a caller must know to use the module: types, invariants, error modes, ordering, config. Not just the type signature.
- **Implementation** — the code inside.
- **Depth** — leverage at the interface: a lot of behaviour behind a small interface. **Deep** = high leverage. **Shallow** = interface nearly as complex as the implementation.
- **Seam** — where an interface lives; a place behaviour can be altered without editing in place. (Use this, not "boundary.")
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Leverage** — what callers get from depth.
- **Locality** — what maintainers get from depth: change, bugs, knowledge concentrated in one place.

Key principles (see [LANGUAGE.md](../fathom/LANGUAGE.md) for the full list):

- **Deletion test**: imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.**
- **One adapter = hypothetical seam. Two adapters = real seam.**

This skill is _informed_ by the project's domain model. The domain language gives names to good seams; ADRs record decisions the skill should not re-litigate.

## Process

### 1. Explore

Read the project's domain glossary (`CONTEXT.md`) and any ADRs in the area you're touching first, so you name modules the way the project does and don't re-litigate settled decisions.

`deepen` reads an **existing** map of the actual codebase — it does not build one. So before exploring, check whether a map already exists with `list_maps()`:

- **A map exists for this project** → resume it (reuse that `map` id). That map is the actual-plane model of what the code *is*; start from its shallow nodes, leak edges, and low-coverage rings rather than re-walking everything cold.
- **No map exists** → there's nothing to deepen against yet. Hand baseline-seeding to **fathom:map**, which walks the codebase with Explore subagents and populates the actual plane (`create_project` → `add_modules` → `set_depth`/`set_coverage`). Once it returns the seeded `map` id, come back here and resume it. (Do **not** seed the map yourself — keeping the actual plane is fathom:map's job, and grilling against a model someone else built honest is the whole point of the shared spine.)

If you are working without the map at all (no MCP host, one-shot review), use the Agent tool with `subagent_type=Explore` to walk the codebase directly. Don't follow rigid heuristics — explore organically and note where you experience friction:

- Where does understanding one concept require bouncing between many small modules?
- Where are modules **shallow** — interface nearly as complex as the implementation?
- Where have pure functions been extracted just for testability, but the real bugs hide in how they're called (no **locality**)?
- Where do tightly-coupled modules leak across their seams?
- Which parts of the codebase are untested, or hard to test through their current interface?

Apply the **deletion test** to anything you suspect is shallow: would deleting it concentrate complexity, or just move it? A "yes, concentrates" is the signal you want.

### 2. Present candidates as an HTML report

If you're driving a living map (step 2a), flag candidates onto the map instead of (or alongside) writing this report; the studio renders them. Use the report when there's no map and you want a one-shot artifact.

Write a self-contained HTML file to the OS temp directory so nothing lands in the repo. Resolve the temp dir from `$TMPDIR`, falling back to `/tmp` (or `%TEMP%` on Windows), and write to `<tmpdir>/architecture-review-<timestamp>.html` so each run gets a fresh file. Open it for the user — `xdg-open <path>` on Linux, `open <path>` on macOS, `start <path>` on Windows — and tell them the absolute path.

The report uses **Tailwind via CDN** for layout and styling, and **Mermaid via CDN** for diagrams where a graph/flow/sequence reliably communicates the structure. Mix Mermaid with hand-crafted CSS/SVG visuals — use Mermaid when relationships are graph-shaped (call graphs, dependencies, sequences), and hand-built divs/SVG when you want something more editorial (mass diagrams, cross-sections, collapse animations). Each candidate gets a **before/after visualisation**. Be visual.

For each candidate, render a card with:

- **Files** — which files/modules are involved
- **Problem** — why the current architecture is causing friction
- **Solution** — plain English description of what would change
- **Benefits** — explained in terms of locality and leverage, and how tests would improve
- **Before / After diagram** — side-by-side, custom-drawn, illustrating the shallowness and the deepening
- **Recommendation strength** — one of `Strong`, `Worth exploring`, `Speculative`, rendered as a badge

End the report with a **Top recommendation** section: which candidate you'd tackle first and why.

**Use CONTEXT.md vocabulary for the domain, and [LANGUAGE.md](../fathom/LANGUAGE.md) vocabulary for the architecture.** If `CONTEXT.md` defines "Order," talk about "the Order intake module" — not "the FooBarHandler," and not "the Order service."

**ADR conflicts**: if a candidate contradicts an existing ADR, only surface it when the friction is real enough to warrant revisiting the ADR. Mark it clearly in the card (e.g. a warning callout: _"contradicts ADR-0007 — but worth reopening because…"_). Don't list every theoretical refactor an ADR forbids.

See [HTML-REPORT.md](../fathom/HTML-REPORT.md) for the full HTML scaffold, diagram patterns, and styling guidance.

Do NOT propose interfaces yet. After the candidates are presented, ask the user: "Which of these would you like to explore?"

### 2a. (Preferred) Flag candidates onto the living map

The suite ships a companion FastMCP server in [arch-map/](../fathom/arch-map/) — the shared, file-backed **spine** every Fathom skill reads and writes. When a UI-capable MCP host is connected (Claude desktop/web, VS Code Insiders, Goose), prefer it over the static HTML: the map renders the whole codebase as a graph and your candidates show up as ⚠ rings on the nodes they touch, where they survive across sessions and skills. It's registered for this repo in `.mcp.json` as `arch-map`.

Use the **same vocabulary as everywhere else** — module, interface, depth, seam, adapter, leverage, locality ([LANGUAGE.md](../fathom/LANGUAGE.md)) — and the **same domain names** from `CONTEXT.md`. A module's `domain` field is the `CONTEXT.md` context it belongs to; its `label` is the domain concept ("Order intake"), never "FooBarHandler".

**The map is shared and file-backed — there is no per-agent state, and every tool takes the map id as its first argument (`map`).** So you must name the map on every call.

#### Resume the map (don't seed it)

`deepen` operates on the **actual plane** that **fathom:map** built. You only ever *read* and *annotate* it here — you do not create modules or set their depth/coverage from scratch.

1. `list_maps()` — find the map for this project and reuse its `map` id. (If none exists, hand off to **fathom:map** to seed it first — see step 1.)
2. `show_map(map)` — render the network. Node size = depth, green ring = coverage, blue halo = updated, ⚠ ring = open suggestion (coloured by strength), red edge = leak, orphan tray = **not connected**. The shallow nodes, leak edges, and thin coverage rings are your candidate list.
3. `scan_signals(map)` — get the triage list: every module with a structural issue (danger-zone, critical-path-untested, needs-refactor, bottleneck, leaky-seam, …) sorted worst-first by health score. This is faster than eyeballing the graph when a map has many modules. Use `scan_signals(map, "test-first")` to find the highest blast-radius modules with the least test cover — those are the ones where a `flag_deepening` candidate is most urgent. The signal ids you'll use most: `danger-zone`, `needs-refactor`, `leaky-seam`, `test-first`, `bottleneck`.
4. `get_model(map)` (full model) or `get_module(map, module)` (one node) when you need the interface text, files, tests, and any existing suggestions back **in your context** — a tool result rendered into the studio does not reach you on its own (see "The tool result is invisible to the model" below).

#### Flag a candidate per friction you found

For each shallow/leaky module that survived the deletion test, attach a deepening candidate:

```
flag_deepening(
  map,                       # the resumed map id
  module,                    # the existing node it deepens
  title,                     # short headline, e.g. "Fold validation behind the Order intake seam"
  strength,                  # "Strong" | "Worth exploring" | "Speculative" — exact strings; the badge colour keys off them
  category,                  # the dependency category at the seam — see DEEPENING.md: in-process | local-substitutable | ports & adapters | true external
  problem,                   # the friction, in LANGUAGE.md terms (shallow, leak, no locality)
  solution,                  # the deepening, in plain English
  wins=[...],                # list of strings: the leverage/locality/testability wins
)
```

`flag_deepening` is the map equivalent of a report card — emit one for each candidate. It derives the suggestion id deterministically as `f"{module}-{strength}"` lower-cased with spaces dashed (e.g. module `order-intake`, strength `Strong` → `order-intake-strong`); that's the `suggestion_id` you pass to `decide`/`resolve`/`grilling_done` later. A module can hold several candidates at once.

You may sharpen the **annotations** as you go — `mark_updated(map, module)` to flag a node you re-examined; `update_module(map, module, {iface: "...", leaksTo: [...]})` to record a leak or tighten the interface text you now understand better. But do **not** invent new modules, re-baseline depth, or reconcile the plane — if the map is stale or wrong about what the code *is*, that's a fathom:map job; ask the user to re-run it.

#### The tool result is invisible to the model

In an MCP-App host, a tool result is delivered to the rendering **iframe** (it drives the studio's redraw) and resolves the call — it does **not** add anything to the conversation or to your context. So treat these tools as side effects plus optional data retrieval, and read state back with `get_model` / `show_map` / `get_module` when you need it in context. `render_view(map, spec)` draws an on-brand ad-hoc table/bar chart, e.g. `render_view(map, {"kind":"table","of":"shallow","columns":["id","domain","depth","coverage"],"sortBy":"depth","sortDir":"asc"})`.

#### The grill hand-off

Clicking **Grill this candidate →** on a node calls `start_grilling(map, module)`. It persists that node's first open candidate as `requested` (so any surface can pick it up) and returns the prompt that drops into step 3. What that does depends on the host:

- **MCP-App host (Claude desktop/web, VS Code Insiders, Goose):** the studio iframe handles the click. Per the MCP-Apps bridge, only `app.sendMessage` (`ui/message`) actually posts a conversation message **and triggers a follow-up agent turn** — it is the single trigger that starts the grilling loop. It is feature-gated on `app.getHostCapabilities()?.message`, and the message `role` is hardcoded to **`"user"`** (the only value the host accepts). `app.updateModelContext` (`ui/update-model-context`, gated on `?.updateModelContext`) stages the candidate's full body into your context **without** triggering a turn; `app.callServerTool` (gated on `?.serverTools`) runs side effects whose results stay in the iframe. So: stage context with `updateModelContext`, run side effects with `callServerTool`, and let `sendMessage` be the one thing that hands control to the agent.
- **Browser studio (HTTP):** a browser cannot trigger an agent turn, so the button only persists the candidate as `requested` and hands back the canonical prompt plus a `/deepen resume <map>` line for the user to paste into their agent.
- **Plain terminal (Claude Code):** you can call every tool, but the host can't render the iframe — there's no graph and no clickable button. Discover candidates a UI flagged with `grilling_queue(map)`, or just begin step 3 directly when the user picks one.

See [arch-map/README.md](../fathom/arch-map/README.md) for setup and the host caveat.

### 3. Grilling loop

If you're driving the living map, **resume it first**: `list_maps()` to find the `map`, then `grilling_queue(map)` to see candidates a studio/browser flagged but no agent has picked up, and `get_model(map)` (or `get_module(map, module)`) to pull the chosen candidate's full body — interface, depth, coverage, and the open suggestion's `problem`/`solution`/`wins` — back into your context (a tool result rendered into the studio doesn't reach you on its own). If you arrived via the **Grill this candidate →** button, `start_grilling(map, module)` already named the map and module in the hand-off prompt. As you begin, call `mark_grilling(map, suggestion_id)` so the candidate's status reflects that it's being grilled.

Now drop into a grilling conversation. Walk the design tree with the user — constraints, dependencies and their [DEEPENING.md](../fathom/DEEPENING.md) category, the shape of the deepened module, what sits behind the seam, what tests survive. Pressure the candidate: one adapter or two? Does the deletion test still hold once you see the call sites? Is the interface really the test surface, or are you testing past it?

Side effects happen inline as decisions crystallize:

- **Naming a deepened module after a concept not in `CONTEXT.md`?** Add the term to `CONTEXT.md`, following the discipline in [CONTEXT-FORMAT.md](../fathom/CONTEXT-FORMAT.md) (be opinionated, keep definitions tight, only project-specific terms). Create the file lazily if it doesn't exist. On a map, also nudge the node's text to match via `update_module(map, module, {label: "...", domain: "..."})` — but do not re-baseline its depth/coverage (that's fathom:map's plane to keep).
- **Sharpening a fuzzy term during the conversation?** Update `CONTEXT.md` right there.
- **User accepts or defers the candidate?** Record the verdict on the map. The simplest path is `decide(map, suggestion_id, "accepted", note="…")` or `decide(map, suggestion_id, "deferred", note="…")` — the decision and reason stick to the candidate and show in the studio's proposal queue; pass `""` as the decision to re-open one. If you grilled it through `start_grilling`/`mark_grilling`, close the loop atomically with `grilling_done(map, suggestion_id, "accepted", note="…")` instead, which marks it grilled and records the verdict in one call. **An accepted candidate is a hand-off to fathom:code** — `deepen` decides *whether* and grills *how*; carrying out the refactor (shallow→deep, then `realize_module` to reconcile the map) belongs to fathom:code, the only skill that edits source. Tell the user that's the next step.
- **User rejects the candidate with a load-bearing reason?** Two things, in this order:
  1. **Record the rejection on the map** with `decide(map, suggestion_id, "rejected", note=reason)` — **never `resolve()`**. `resolve(map, suggestion_id)` dismisses the candidate (status `done`) and is for the *never-load-bearing* case ("not worth it right now"); it keeps no reason a future reviewer can act on. `decide(... "rejected", note=…)` keeps the candidate as the durable record **with the reason attached**, so the next explorer — and the next scan — sees *why* it was rejected and doesn't re-suggest it.
  2. **Offer an ADR** when the reason qualifies, framed as: _"Want me to record this as an ADR so future architecture reviews don't re-suggest it?"_ Only offer when all three ADR tests hold — **hard to reverse, surprising without context, the result of a real trade-off** ([ADR-FORMAT.md](../fathom/ADR-FORMAT.md)). Skip ephemeral reasons ("not worth it right now") and self-evident ones. Writing the ADR file itself is **fathom:adr-writer's** job — it owns the `docs/adr/NNNN-slug.md` numbering and template; `deepen` only offers and hands off. Once written, point the rejection at it so the map and the ADR cross-reference each other: close via `grilling_done(map, suggestion_id, "rejected", note="…", adr="docs/adr/0007-keep-ordering-and-billing-decoupled.md")`, or set the note to reference the path if you used plain `decide`.
- **Want to explore alternative interfaces for the deepened module?** That's design-it-twice work on the **intended** structure — hand off to **fathom:plan** ([INTERFACE-DESIGN.md](../fathom/INTERFACE-DESIGN.md) describes the parallel-sub-agent pattern it uses). `deepen` grills the candidate to a decision; designing the new interface graph from scratch is fathom:plan's job, and building it is fathom:code's.

(There is no separate "mark grilled" tool to call by hand — `grilling_done(...)` records a grilled candidate's outcome, and `decide(...)` records a decision taken outside the grilling lifecycle.)
