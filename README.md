# Fathom

A suite of Claude Code skills built on one principle and one shared model: turn **shallow** modules (interface ≈ as complex as the implementation) into **deep** ones — a lot of behaviour behind a small interface — for the sake of testability and AI-navigability.

The skills don't just analyse; they share a **living architecture model** — the `arch-map` MCP **spine** — that each one reads and writes, so a codebase becomes something humans *and* agents can reason about by depth.

## The principle

Every skill speaks one vocabulary ([LANGUAGE.md](./skills/engineering/deepen/LANGUAGE.md)) — **module, interface, depth, seam, adapter, leverage, locality** — and obeys the same rules: the **deletion test** (if a module vanished, would complexity concentrate behind a small interface, or just scatter?), **the interface is the test surface**, and **one adapter = a hypothetical seam, two = a real one**. Architecture is reasoned about by *depth*, never by "components/services/APIs/boundaries."

## The suite

**Shipped:**

- [`deepen`](./skills/engineering/deepen/SKILL.md) — find friction in existing shallow modules, present candidates, and **grill** the chosen one; updates `CONTEXT.md` and offers ADRs as decisions crystallize.

**Designed, in progress** (see the design notes in this branch):

- `map` — build and keep honest the **actual** model of what the codebase IS (seed via exploration; reconcile on demand).
- `understand` — a read-only guided tour of a map (entry interfaces, deepest modules, hot-spots).
- `plan` — design the **intended** deep-module graph for new or changing work, before code.
- `code` — execute a chosen deepening (refactor shallow→deep, or build to a planned interface). The only skill that edits source.
- `adr-writer` — record load-bearing decisions as `docs/adr/NNNN-*.md`.

## The spine: `arch-map`

The suite ships a [FastMCP](https://github.com/jlowin/fastmcp) server at [`arch-map/`](./skills/engineering/deepen/arch-map/) — the persistent model every skill reads and writes. The agent keeps it current with tools (`show_map`, `flag_deepening`, `set_depth`, `set_coverage`, `decide`, `resolve`, …) and a UI-capable host renders it inline via [MCP Apps](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/): depth = node size, coverage = ring, suggestions = ⚠ ring, leaks = red edge, orphans = a "not connected" tray. Registered for this repo in [`.mcp.json`](./.mcp.json). See the [arch-map README](./skills/engineering/deepen/arch-map/README.md).

## Files (the `deepen` skill)

- [`SKILL.md`](./skills/engineering/deepen/SKILL.md) — the skill
- [`LANGUAGE.md`](./skills/engineering/deepen/LANGUAGE.md) — the shared vocabulary
- [`DEEPENING.md`](./skills/engineering/deepen/DEEPENING.md) — how to deepen a cluster safely, by dependency category
- [`INTERFACE-DESIGN.md`](./skills/engineering/deepen/INTERFACE-DESIGN.md) — exploring alternative interfaces for a deepened module
- [`HTML-REPORT.md`](./skills/engineering/deepen/HTML-REPORT.md) — the one-shot HTML report scaffold
- [`CONTEXT-FORMAT.md`](./skills/engineering/deepen/CONTEXT-FORMAT.md) — the `CONTEXT.md` domain-glossary format
- [`ADR-FORMAT.md`](./skills/engineering/deepen/ADR-FORMAT.md) — the ADR format
- [`arch-map/`](./skills/engineering/deepen/arch-map/) — the FastMCP spine + network-graph UI

Originally part of [mattpocock/skills](https://github.com/mattpocock/skills).
