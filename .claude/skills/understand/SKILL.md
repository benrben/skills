---
name: understand
description: Read-only guided tour of an existing arch-map — entry interfaces, the deepest modules, and leak/drift hot-spots — so a newcomer (human or agent) can comprehend a codebase's deep structure before touching it. The front door of the Fathom suite. Do NOT use for changing the map (that is fathom:map, which seeds and reconciles), for proposing refactors (fathom:deepen), for designing new structure (fathom:plan), or for editing source (fathom:code) — understand writes NOTHING to the spine; its one permitted artifact is exporting the tour to docs/TOUR.md when the user explicitly asks to save it.
---

# Understand a Codebase Through Its Map

Give a guided tour of an existing architecture map: walk the **entry interfaces** a newcomer would meet first, the **deepest modules** where the leverage lives, and the **leak / not-connected** hot-spots that explain the friction. The aim is comprehension — letting a human or an agent build an accurate mental model of a codebase's deep structure before any of the other Fathom skills touch it.

This is the **front door** of the Fathom suite. It reads the shared spine the arch-map MCP maintains and narrates it. It is **strictly read-only**: it never seeds, reconciles, flags, decides, plans, or edits. (One artifact exception: on an explicit request it may save the finished tour to `docs/TOUR.md` — see step 5; the spine is still never written.) When you find yourself wanting to *change* the map or the code, you have left this skill — hand off (see [Hand-offs](#hand-offs)).

## Glossary

Speak these terms exactly, the same way every Fathom skill does — don't drift into "component," "service," "API," or "boundary." Full definitions in [../fathom/LANGUAGE.md](../fathom/LANGUAGE.md).

- **Module** — anything with an interface and an implementation (function, class, package, slice).
- **Interface** — everything a caller must know to use the module: types, invariants, error modes, ordering, required configuration. Not just the type signature.
- **Implementation** — the code inside.
- **Depth** — leverage at the interface: a lot of behaviour behind a small interface. **Deep** = high leverage. **Shallow** = the interface is nearly as complex as the implementation.
- **Seam** — where an interface lives; a place behaviour can be altered without editing in place. (Use this, not "boundary.")
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Leverage** — what callers get from depth.
- **Locality** — what maintainers get from depth: change, bugs, and knowledge concentrated in one place.

Two principles do most of the explaining on a tour (see [../fathom/LANGUAGE.md](../fathom/LANGUAGE.md) for the full set):

- **The interface is the test surface.** A module's interface is what callers *and* tests cross — so coverage at the interface tells you how trustworthy the module is to lean on.
- **The deletion test** explains *why* a deep module earns its keep: imagine deleting it and watch complexity reappear across N callers.

You may name what a leak or a shallow cluster *would* cost in those terms — but you do not propose the fix. That is [fathom:deepen](../deepen/SKILL.md)'s job.

## The map is the source of truth, not the code

You read the **map**, not the repository. The map is the spine the other Fathom skills built: [fathom:map](#hand-offs) seeded the **actual** plane (what the code IS), [fathom:plan](#hand-offs) staged **intended** modules beside it (what a design WANTS), and [fathom:code](#hand-offs) realized some of those into built ones. Your tour reflects that staged reality:

- **`plane`** is `"actual"` (what IS) or `"intended"` (what a plan WANTS). A newcomer's tour of "the codebase" is the **actual** plane; mention intended modules only to explain where the design is heading (and which actual modules they `supersede`).
- **`lifecycle`** is `"planned"`, `"building"`, or `"built"`. Tour the **built** structure; flag planned-but-unbuilt modules as "designed, not yet here."
- A **candidate** is the user-facing word for a Suggestion — an open deepening opportunity another run flagged. Surface candidates as *part of the map's story* ("this module already has a Strong candidate on it"); do not grill or decide them.

If the map looks stale or wrong while you tour it — depth scores that don't match the code, missing modules, edges that no longer exist — that is a **reconcile** job, and it belongs to [fathom:map](#hand-offs), not here. Say so and hand off; never "fix" the map yourself.

## Process

### 1. Find the map

A tour needs a named map. Maps are shared and file-backed, so the same map id threads through every call you make.

1. `archmap_list_maps()` → the available maps with their repo label and module / candidate counts. If the user named a project, match it; otherwise present the list and ask which one to tour.
2. If there is **no map for this codebase yet**, there is nothing to tour. Do not create or seed one — tell the user the codebase hasn't been mapped and hand off to [fathom:map](#hand-offs) to seed it, then come back.

Hold onto the chosen `map` id; pass it as the first argument to every read below.

### 2. Take the lay of the land

```
archmap_show_map(map)                 # digest: module/domain counts, orphans, open candidates,
                                      # and the ten worst-health modules
archmap_show_map(map, domain="<d>")   # full view records (edges, metrics) for one domain slice
```

Inside a UI-capable MCP host this renders the network graph inline (fill = depth, ring = coverage, halo = updated, ⚠ ring = open candidate, red edge = leak, orphan tray = **not connected**) and your narration rides alongside it. In a terminal you get the same data as structured text and you narrate from it. Either way, start with the shape of the whole before zooming in:

- How many modules, grouped into which **domains**? Read the domains aloud — they are the chapters of the tour.
- Which plane are you touring? Stay on `plane="actual"`, `lifecycle="built"` unless the user asks where the design is going.

For headcounts, distributions, or a sortable list, render an on-brand view instead of dumping raw JSON:

```
archmap_render_view(map, kind="bar", metric="depth", group_by="domain", agg="avg")
archmap_render_view(map, columns=["id","domain","depth","coverage"], sort_by="depth", sort_dir="desc")
```

`archmap_render_view` only *shapes and draws* what's already in the map — it is a read, not a write.

### 3. Walk the three lenses

A good tour is three passes over the same map, each answering a question a newcomer actually has. Pull full module records as you go — `archmap_show_map` gives the skeleton, but the interface text, files, and tests live in the full model:

```
archmap_get_full_model(map)                       # the FULL model: every iface, files, tests, candidate body
archmap_modules(map, action="get", id=X)          # one module's full record (read-only; does not redraw)
archmap_modules(map, action="get", ids=[...])     # several at once
```

**Lens A — Entry interfaces: "where do I come in?"**
The modules a caller or a newcomer meets first. Find them structurally: modules many others `dependsOn` but that depend on little themselves (the things the system is *used through*), plus the top of each domain. For each, narrate its **interface** — what a caller must know to use it (types, invariants, error modes, ordering, config), not just the signature. This is the map a newcomer most needs.

**Lens B — Deepest modules: "where does the leverage live?"**
Sort by `depth` (`archmap_render_view` with `sort_by="depth", sort_dir="desc"`, or read it off `archmap_get_full_model`). The deepest modules are where a lot of behaviour sits behind a small interface — the load-bearing parts worth understanding well. Use the **deletion test** to explain *why* each is deep: deleting it would scatter its complexity across N callers. Note their `coverage` — a deep module with high interface coverage is one you can lean on with confidence; a deep module with low coverage is the one to be careful around.

**Lens C — Hot-spots: "where is the friction?"**
The places that explain why the codebase feels harder than its size suggests. Start with `archmap_scan_signals(map)` — it returns every module carrying a structural signal sorted worst-first by health score, which is the fastest triage of the whole map. Then narrate what you find:

- **Structural signals** — the computed issues `archmap_scan_signals` surfaces. The ones worth narrating on a tour:
  - `danger-zone` (high churn + low coverage) — the module most likely to cause a production incident
  - `critical-path-untested` (high blast-radius + low coverage) — a bug here breaks the most
  - `needs-refactor` (high fan-out + low depth) — does too much, hides nothing
  - `bottleneck` (many dependents + shallow) — everyone relies on it but it's fragile
  - `leaky-seam` — reaches across seams it shouldn't
  - `test-first` — highest-priority for adding tests before any refactor
- **Leaks** (`leaksTo`, red edges) — where a module reaches across another's seam instead of through its interface. Narrate what coupling this creates and which two modules are now hard to change independently.
- **Not-connected** (`orphans`) — modules with no edge in any direction. Either dead, or connected through a path the map doesn't yet record (a reconcile question for [fathom:map](#hand-offs)).
- **Shallow clusters** — runs of low-`depth` modules in one domain, where understanding one concept means bouncing between many small modules with no **locality**. Name the friction; don't prescribe the merge.
- **Open candidates** — modules already carrying a deepening candidate (the ⚠ ring). Report the candidate's `title` and `strength` (`"Strong"` / `"Worth exploring"` / `"Speculative"`) and that someone has already noticed this friction — then move on.

You may also use `archmap_get_metrics(map, module)` to pull a single module's raw numbers (fanIn, fanOut, instability, blastRadius, health) when a user asks "how bad is this one specifically?" That gives you the numbers; `archmap_scan_signals` gives you the interpretation.

Scope each lens to what the user asked for. "Give me a tour" earns all three across all domains; "what does the billing area do?" earns all three filtered to that domain (`archmap_render_view(map, of="<domain>")` or `archmap_show_map(map, domain="<domain>")`, then `archmap_modules` with `action="get"` for the bodies).

### 4. Narrate the tour

Tell the story in the project's own domain vocabulary (the `domain` and `label` fields, set from CONTEXT.md) and the architecture vocabulary from [../fathom/LANGUAGE.md](../fathom/LANGUAGE.md). Talk about "the Order intake module," not "the OrderHandler" and not "the Order service."

Structure a full tour as:

1. **The shape** — domains as chapters, rough module counts, where the depth is concentrated and where it's thin.
2. **Come in here** — the entry interfaces (Lens A), each with the facts a caller must know.
3. **The deep core** — the highest-leverage modules (Lens B) and what each hides behind its interface, with a coverage read on how safely you can lean on it.
4. **Mind these** — the hot-spots (Lens C): leaks, not-connected modules, shallow clusters, and any candidates already flagged.
5. **Where you'd go next** — route the user to the right sibling skill for what they now want to do, without doing it yourself.

Be honest about confidence. If a module's `iface` text is thin or its `depth`/`coverage` look stale, say "the map records X here, but it may be out of date — [fathom:map](#hand-offs) can reconcile it." You are reporting the map's account of the codebase, not certifying it.

### 5. Export the tour (only when asked)

By default the tour lives in the conversation and nowhere else. On an **explicit user request** ("save the tour", "write this down for the team"), write it to `docs/TOUR.md` in the repo: overwrite the previous one, open with a dated header naming the map id and — if the map has anchors — the latest anchor's sha (`archmap_drift`'s `sinceSha`), so a reader knows exactly which state of the codebase the tour describes. This is the ONE write this skill may perform, and it is a repo artifact, never a spine write — the spine-read-only rule is unchanged. Never export unprompted.

### 6. Hand off

The tour ends by pointing at the door the user wants next. You never walk through it for them — that would mean writing to the spine or the source structure, which this skill must not do.

## Hand-offs

`understand` is the front door; every other Fathom skill is a room off it. Route by what the user wants to *do* now:

- **"This part of the map looks wrong / out of date / is missing modules"** → **fathom:map**. It is the only skill (besides code) that writes the actual plane: it seeds via Explore subagents and reconciles depth/coverage/edges to match reality. It writes; understand only explains. *(This is the distinction that keeps the two skills apart: map verifies accuracy by mutating; understand assumes the map and narrates it.)*
- **"This shallow cluster / leak is worth fixing"** → **fathom:deepen**. It finds friction in existing shallow modules, presents candidates, and grills the chosen one. You may have *pointed at* the friction on the tour; deepen decides whether to act and attaches the candidate.
- **"I want to design the new/changed structure here"** → **fathom:plan**. It designs the intended deep-module graph — seams, interfaces (design-it-twice), dependency categories, sequenced WorkSteps.
- **"Build it / execute this candidate or WorkStep"** → **fathom:code**. The only source editor: it refactors shallow→deep or builds to a planned interface (interface = test surface), then realizes the module and hands back to map to reconcile.
- **"Record why we decided this"** → **adr-writer**, offered by the sibling that made the decision (deepen / plan / code). understand surfaces existing `adrRef`s on candidates as part of the story, but it does not write ADRs.

If the tour was the whole request, stop after step 4 — a clean read needs no hand-off.
