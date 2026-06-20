# Skills

The **Fathom** suite — five skills on the deep-module principle, sharing the `arch-map` spine (see the [top-level README](../README.md)). Engineer cycle: map → understand → design → code, with review gating changes. All project docs live **only on the spine**, in eleven types ([DOC-TYPES.md](./fathom/DOC-TYPES.md)).

- [`map`](./map/SKILL.md) — observe & record what the codebase IS (modules, depth, edges, leaks, coverage, all signals) and capture the recorded truth as docs of every type. The doc registrar; absorbs the old `adr-writer`. A writer of the actual plane alongside `code`.
- [`understand`](./understand/SKILL.md) — read-only guided tour of the map **and its docs**, ending with the named next action. The front door; writes nothing.
- [`design`](./design/SKILL.md) — decide the deep structure, two modes by request: **improve** an existing shallow module (flag + grill a candidate) or design **new** intended structure (seams, interfaces, sequenced steps). Merges the old `deepen` + `plan`.
- [`code`](./code/SKILL.md) — execute a chosen target (refactor shallow→deep, build to a planned interface, or write interface tests), following `MINIMALISM.md`. The only skill that edits source.
- [`review`](./review/SKILL.md) — review a diff/PR through the map: modules touched, seams crossed, danger-zones touched without tests, interface erosion. Read-only (may record a `risk`/`postmortem` doc); the change gate.

> `fathom/` holds the suite's **shared substrate** — the [`arch-map`](./fathom/arch-map/) MCP spine plus the vocabulary/format docs (`LANGUAGE.md`, `DOC-TYPES.md`, `DEEPENING.md`, `MINIMALISM.md`, `INTERFACE-DESIGN.md`, `CONTEXT-FORMAT.md`, `HTML-REPORT.md`) every skill references. It is not a skill, so it isn't listed above.
