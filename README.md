# Fathom

A suite of Claude Code skills built on one principle and one shared model: turn **shallow** modules (interface ≈ as complex as the implementation) into **deep** ones — a lot of behaviour behind a small interface — for the sake of testability and AI-navigability.

The skills don't just analyse; they share a **living architecture model** — the `arch-map` MCP **spine** — that each one reads and writes, so a codebase becomes something humans *and* agents can reason about by depth.

## The principle

Every skill speaks one vocabulary ([LANGUAGE.md](./skills/engineering/fathom/LANGUAGE.md)) — **module, interface, depth, seam, adapter, leverage, locality** — and obeys the same rules: the **deletion test** (if a module vanished, would complexity concentrate behind a small interface, or just scatter?), **the interface is the test surface**, and **one adapter = a hypothetical seam, two = a real one**. Architecture is reasoned about by *depth*, never by "components/services/APIs/boundaries."

## The suite

Six skills, one lifecycle — **map → understand → deepen → plan → code**, with `adr-writer` recording decisions. All speak one vocabulary and share one model.

- [`map`](./skills/engineering/map/SKILL.md) — build and keep honest the **actual** model of what the codebase IS (seed via exploration; reconcile on demand). The only writer of the actual plane besides `code`.
- [`understand`](./skills/engineering/understand/SKILL.md) — a read-only guided tour of a map (entry interfaces, deepest modules, leak hot-spots). The front door; writes nothing.
- [`deepen`](./skills/engineering/deepen/SKILL.md) — find friction in **existing** shallow modules, present candidates, and **grill** the chosen one; records decisions and offers ADRs as they crystallize.
- [`plan`](./skills/engineering/plan/SKILL.md) — design the **intended** deep-module graph for new or changing work (seams, interfaces, sequenced build steps), before code.
- [`code`](./skills/engineering/code/SKILL.md) — execute a chosen deepening (refactor shallow→deep, or build to a planned interface). The **only** skill that edits source.
- [`adr-writer`](./skills/engineering/adr-writer/SKILL.md) — record load-bearing decisions as `docs/adr/NNNN-*.md` (general-purpose; the Fathom skills offer it).

## The spine: `arch-map`

The suite ships a [FastMCP](https://github.com/jlowin/fastmcp) server at [`arch-map/`](./skills/engineering/fathom/arch-map/) — the persistent model every skill reads and writes. The agent keeps it current with tools (`show_map`, `flag_deepening`, `set_depth`, `set_coverage`, `decide`, `resolve`, …) and a UI-capable host renders it inline via [MCP Apps](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/): depth = node size, coverage = ring, suggestions = ⚠ ring, leaks = red edge, orphans = a "not connected" tray. Registered for this repo in [`.mcp.json`](./.mcp.json). See the [arch-map README](./skills/engineering/fathom/arch-map/README.md).

## Files (the `deepen` skill)

- [`SKILL.md`](./skills/engineering/deepen/SKILL.md) — the skill
- [`LANGUAGE.md`](./skills/engineering/fathom/LANGUAGE.md) — the shared vocabulary
- [`DEEPENING.md`](./skills/engineering/fathom/DEEPENING.md) — how to deepen a cluster safely, by dependency category
- [`INTERFACE-DESIGN.md`](./skills/engineering/fathom/INTERFACE-DESIGN.md) — exploring alternative interfaces for a deepened module
- [`HTML-REPORT.md`](./skills/engineering/fathom/HTML-REPORT.md) — the one-shot HTML report scaffold
- [`CONTEXT-FORMAT.md`](./skills/engineering/fathom/CONTEXT-FORMAT.md) — the `CONTEXT.md` domain-glossary format
- [`ADR-FORMAT.md`](./skills/engineering/fathom/ADR-FORMAT.md) — the ADR format
- [`arch-map/`](./skills/engineering/fathom/arch-map/) — the FastMCP spine + network-graph UI

Originally part of [mattpocock/skills](https://github.com/mattpocock/skills).
