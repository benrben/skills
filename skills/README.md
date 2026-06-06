# Skills

The **Fathom** suite — six skills on the deep-module principle, sharing the `arch-map` spine (see the [top-level README](../README.md)). Lifecycle order: map → understand → deepen → plan → code, with adr-writer recording decisions.

- [`map`](./map/SKILL.md) — build and keep honest the **actual** model of what a codebase IS (seed via exploration, reconcile on demand, inspect). The only writer of the actual plane besides `code`.
- [`understand`](./understand/SKILL.md) — read-only guided tour of a map (entry interfaces, deepest modules, leak hot-spots). The front door; writes nothing.
- [`deepen`](./deepen/SKILL.md) — find friction in **existing** shallow modules, present candidates, and grill the chosen one to a decision.
- [`plan`](./plan/SKILL.md) — design the **intended** deep-module graph for new/changing work (seams, interfaces, sequenced build steps) before code.
- [`code`](./code/SKILL.md) — execute a chosen deepening (refactor shallow→deep, or build to a planned interface). The only skill that edits source.
- [`adr-writer`](./adr-writer/SKILL.md) — record load-bearing decisions as `docs/adr/NNNN-*.md` (general-purpose; the Fathom skills offer it).

> `fathom/` holds the suite's **shared substrate** — the [`arch-map`](./fathom/arch-map/) MCP spine plus the vocabulary/format docs (`LANGUAGE.md`, `DEEPENING.md`, `INTERFACE-DESIGN.md`, `CONTEXT-FORMAT.md`, `ADR-FORMAT.md`, `HTML-REPORT.md`) every skill references. It is not a skill, so it isn't listed above.
