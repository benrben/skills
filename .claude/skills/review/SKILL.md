---
name: review
description: Review a diff, PR, or branch THROUGH the architecture map — which modules the change touches, whether it crosses a seam it shouldn't (new edges not on the map), whether it touches a danger-zone module without adding tests, and whether it erodes a deep module's interface. Use when asked to review a change, check a PR against the architecture, gate a merge, or answer "is this change safe / does it respect the seams." Strictly read-only against both the spine and the source: it reports findings and routes them — stale-map findings to fathom:map, friction worth fixing to fathom:deepen, structural redesign to fathom:plan. Do NOT use to find general bugs or style issues (use a code-review tool), to reconcile the map (fathom:map), or to edit source (fathom:code).
---

# Review — the Change Gate

Review a change **through the map**: the arch-map spine knows where the seams are, which modules are deep and load-bearing, which are danger-zones, and what the recorded dependency graph allows. This skill holds a diff up against that knowledge and reports what the change *means architecturally* — before it merges.

This is what turns the map from a study aid into a working gate: every change gets checked against the structure the suite maintains, and map drift is caught at the moment it is created instead of at the next reconcile.

## Glossary

Speak the [../fathom/LANGUAGE.md](../fathom/LANGUAGE.md) vocabulary exactly — module / interface / implementation / depth / seam / adapter / leverage / locality. Never "component," "service," "API," or "boundary." Two terms this skill leans on:

- **Anchor** — a recorded reconcile event on the map (git sha + timestamp + per-module snapshot); the baseline drift is computed against.
- **Halo** — the `updated` marker on a module; this skill never sets or clears it (that is fathom:map's).

## Strictly read-only

review writes **nothing**: no spine writes, no source edits, no halos, no candidates, no ADRs. Its entire output is the report and the hand-offs. If you find yourself wanting to fix what you found, you have left this skill — route it (see [Hand-offs](#hand-offs)).

## Process

### 1. Resolve the map and the baseline

- `archmap_list_maps()` → this repo's map id. No map → STOP; hand to **fathom:map** to seed one (a review without a map is just a generic code review — say so).
- Identify the change under review: a PR (use `gh pr diff` / `gh pr view`), a branch (`git diff <base>...HEAD`), or the working tree (`git diff`). Establish the **base sha** the change builds on.

### 2. Which modules does this change touch?

```
archmap_drift(map, since_sha=<base sha>, root=<repo root>)
```

`modulesTouched` is the review's scope: each touched module with the changed files it owns. Two findings fall out immediately:

- **`unmappedFiles`** — changed files NO module owns. Either new structure the map doesn't know yet (a reconcile gap → fathom:map) or files that should belong to an existing module's `files` list. Name them; don't fix them.
- Pull each touched module's record (`archmap_modules(map, action="get", ids=[...])`) for its depth, coverage, seam, and iface — the facts the next steps read against.

### 3. Does the change cross a seam it shouldn't?

```
archmap_verify_edges(map, root=<repo root>)
```

Compare `undeclaredEdges` against the touched modules: an undeclared edge **from a touched module** is this change reaching across a seam the map does not sanction — a leak being born. Report it with both module names and what coupling it creates. (Undeclared edges from *untouched* modules are pre-existing drift — note them for fathom:map, separately, so the author isn't blamed for them.)

### 4. Does it touch a danger-zone without tests?

```
archmap_scan_signals(map)
```

Overlay the signals on the touched set:

- A touched module carrying `danger-zone`, `critical-path-untested`, or `test-first` **without test changes in the diff** is the highest-severity finding: the riskiest code changed with no new safety net. (Check the diff for changes under the module's recorded `tests` surface.)
- A touched `bottleneck` or high blast-radius module deserves a "wide blast radius" note even when tested.

### 5. Does it erode an interface?

For each touched module that is **deep** (high recorded depth), read the diff against its recorded `iface` text: does the change widen the interface (new required parameters, new error modes callers must handle, leaked internals)? A deep module's value is its small interface — flag erosion explicitly, quoting the recorded promise.

### 6. Report

Lead with the verdict shape: **clean** / **findings to discuss** / **architectural objection**. Then findings ordered by severity, each naming the module(s) in the map's own labels, the evidence (file, edge, signal), and the route:

1. Seam crossings born in this change (step 3)
2. Danger-zone touches without tests (step 4)
3. Interface erosion on deep modules (step 5)
4. Map gaps the change reveals — unmapped files, pre-existing undeclared edges (step 2/3) → fathom:map
5. Friction the change rubs against but didn't cause → fathom:deepen

Be honest about confidence: if the map's record looks stale for a touched module, say the finding is conditional on it and route the reconcile.

## Hand-offs

- **Map is missing / stale / has unmapped files** → **fathom:map** (the only actual-plane writer).
- **A finding is worth fixing structurally** (shallow cluster, recurring leak) → **fathom:deepen** to flag and grill a candidate.
- **The change needs new intended structure** → **fathom:plan**.
- **The fix itself** → **fathom:code**, only after deepen/plan has decided a target.
- **A load-bearing decision surfaced** (e.g. an accepted seam crossing) → **adr-writer**.

## What review does NOT do

- Does NOT write the spine (no halos, no candidates, no edges) or the source.
- Does NOT do generic code review (bugs, style, naming) — it reviews **against the map** only.
- Does NOT decide whether a flagged friction gets fixed — fathom:deepen grills, the user decides.
- Does NOT reconcile drift it discovers — it reports the gap and routes to fathom:map.
