# Improve Codebase Architecture

A single agent skill (slash command) for Claude Code: [`/improve-codebase-architecture`](./skills/engineering/improve-codebase-architecture/SKILL.md).

It surfaces architectural friction and proposes **deepening opportunities** — refactors that turn shallow modules into deep ones, for the sake of testability and AI-navigability.

## What it does

1. **Explore** — reads your project's `CONTEXT.md` and any ADRs, then walks the codebase looking for friction: shallow modules, tight coupling, and code that's hard to test through its current interface. It applies the **deletion test** to spot pass-throughs.
2. **Report** — writes a self-contained, visual HTML report (Tailwind + Mermaid via CDN) to your temp directory and opens it. Each candidate gets a before/after diagram and a recommendation strength badge (`Strong`, `Worth exploring`, `Speculative`), ending with a top recommendation. _Or_ drive the **living network map** via the companion MCP server (below) instead of a one-shot file.
3. **Grill** — once you pick a candidate, it walks the design tree with you, updating `CONTEXT.md` and offering ADRs as decisions crystallize.

## Companion: the `arch-map` MCP server

The skill ships a [FastMCP](https://github.com/jlowin/fastmcp) server at [`arch-map/`](./skills/engineering/improve-codebase-architecture/arch-map/) that turns the one-shot report into a **persistent, agent-maintained network graph** rendered inline via [MCP Apps](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/). The agent keeps the model current with tools (`show_map`, `flag_deepening`, `set_depth`, `set_coverage`, `mark_updated`, `resolve`); the graph encodes depth (node size), coverage (ring), updates (halo), suggestions (⚠ ring), leaks (red edge), and orphans (a "not connected" tray). It's registered for this repo in [`.mcp.json`](./.mcp.json). See the [arch-map README](./skills/engineering/improve-codebase-architecture/arch-map/README.md).

## Files

- [`SKILL.md`](./skills/engineering/improve-codebase-architecture/SKILL.md) — the skill itself
- [`LANGUAGE.md`](./skills/engineering/improve-codebase-architecture/LANGUAGE.md) — the shared vocabulary (module, interface, depth, seam, adapter, leverage, locality)
- [`DEEPENING.md`](./skills/engineering/improve-codebase-architecture/DEEPENING.md) — how to deepen a cluster of shallow modules safely, by dependency category
- [`INTERFACE-DESIGN.md`](./skills/engineering/improve-codebase-architecture/INTERFACE-DESIGN.md) — exploring alternative interfaces for a deepened module
- [`HTML-REPORT.md`](./skills/engineering/improve-codebase-architecture/HTML-REPORT.md) — the HTML scaffold, diagram patterns, and styling guidance
- [`CONTEXT-FORMAT.md`](./skills/engineering/improve-codebase-architecture/CONTEXT-FORMAT.md) — the `CONTEXT.md` domain-glossary format
- [`ADR-FORMAT.md`](./skills/engineering/improve-codebase-architecture/ADR-FORMAT.md) — the ADR format used when recording a rejected candidate
- [`arch-map/`](./skills/engineering/improve-codebase-architecture/arch-map/) — the companion FastMCP server + network-graph UI

Originally part of [mattpocock/skills](https://github.com/mattpocock/skills).
