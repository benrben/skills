# Fathom

A suite of Claude Code skills built on one principle and one shared model: turn **shallow** modules (interface ≈ as complex as the implementation) into **deep** ones — a lot of behaviour behind a small interface — for the sake of testability and AI-navigability.

The skills don't just analyse; they share a **living architecture model** — the `arch-map` MCP **spine** — that each one reads and writes, so a codebase becomes something humans *and* agents can reason about by depth.

## The principle

Every skill speaks one vocabulary ([LANGUAGE.md](./skills/fathom/LANGUAGE.md)) — **module, interface, depth, seam, adapter, leverage, locality** — and obeys the same rules: the **deletion test** (if a module vanished, would complexity concentrate behind a small interface, or just scatter?), **the interface is the test surface**, and **one adapter = a hypothetical seam, two = a real one**. Architecture is reasoned about by *depth*, never by "components/services/APIs/boundaries."

## The suite

Seven skills, one lifecycle — **map → understand → deepen → plan → code**, with `review` gating changes and `adr-writer` recording decisions. All speak one vocabulary and share one model.

- [`map`](./skills/map/SKILL.md) — build and keep honest the **actual** model of what the codebase IS (seed via exploration; reconcile on demand). The only writer of the actual plane besides `code`.
- [`understand`](./skills/understand/SKILL.md) — a read-only guided tour of a map (entry interfaces, deepest modules, leak hot-spots). The front door; writes nothing.
- [`deepen`](./skills/deepen/SKILL.md) — find friction in **existing** shallow modules, present candidates, and **grill** the chosen one; records decisions and offers ADRs as they crystallize.
- [`plan`](./skills/plan/SKILL.md) — design the **intended** deep-module graph for new or changing work (seams, interfaces, sequenced build steps), before code.
- [`code`](./skills/code/SKILL.md) — execute a chosen deepening (refactor shallow→deep, build to a planned interface, or write interface tests for a test-first target). The **only** skill that edits source.
- [`review`](./skills/review/SKILL.md) — review a diff/PR **through the map**: modules touched, seams crossed, danger-zones touched without tests, interface erosion. Read-only; the change gate.
- [`adr-writer`](./skills/adr-writer/SKILL.md) — record load-bearing decisions as `docs/adr/NNNN-*.md` (general-purpose; the Fathom skills offer it).

## The spine: `arch-map`

The suite ships a [FastMCP](https://github.com/jlowin/fastmcp) server at [`arch-map/`](./skills/fathom/arch-map/) — the persistent model every skill reads and writes. The agent keeps it current with a small tool surface (`archmap_show_map`, `archmap_scan_signals`, and five action-dispatchers — `archmap_modules`, `archmap_suggestions`, `archmap_grilling`, `archmap_plans`, `archmap_docs` — e.g. `archmap_suggestions(action="flag", …)`, `archmap_modules(action="update", depth=…)`) and a UI-capable host renders it inline via [MCP Apps](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/): depth = node size, coverage = ring, suggestions = ⚠ ring, leaks = red edge, orphans = a "not connected" tray. Registered for this repo in [`.mcp.json`](./.mcp.json). See the [arch-map README](./skills/fathom/arch-map/README.md).

## Keep the map true: measured facts, drift, and the weekly pulse

The spine measures its own facts instead of trusting estimates. `archmap_ingest(map, root=…)` computes **churn** from git history and **coverage** from a real test report (coverage.py XML/JSON or lcov), and records a reconcile **anchor** (git sha + per-module health snapshot). From there:

- `archmap_drift(map)` — what changed since the last anchor; the map digest (`archmap_show_map`) opens with the same staleness line ("3 files changed, 2 modules touched since `a1b2c3d`").
- `archmap_history(map)` — health/depth/coverage trends across anchors, per module or per domain.
- `archmap_verify_edges(map)` — the recorded dependency edges checked against the code's real imports.

**Weekly health pulse** — schedule a recurring agent that keeps watch and reports, writing nothing:

```
/schedule weekly: run archmap_drift and archmap_scan_signals on the <map> map,
compare archmap_history against last week, and report: stale modules, signals
entered/left, and the health trend. Report only — do not write the spine.
```

(Locally, the same prompt works with `/loop` or any cron runner pointed at `claude -p`.) Routine reconciles stay with `/map`; the pulse only tells you when one is due.

## Install it in another project

This repo is a self-contained Claude Code **plugin + marketplace** (`fathom`). Installing it brings **all six skills _and_ the `arch-map` MCP spine** in one step.

**Prerequisite:** [`uv`](https://docs.astral.sh/uv/) on your `PATH` (the MCP server runs via `uv run`).

```bash
cd /path/to/your/other-project
/plugin marketplace add https://github.com/benrben/skills      # or a local clone: /path/to/skills
/plugin install fathom@fathom
```

That gives you:

- **The skills** — the slash commands `/map`, `/understand`, `/deepen`, `/plan`, `/code`, `/review`, `/adr-writer` (auto-registered from the plugin; `SKILL.md` edits hot-reload).
- **The spine** — the `arch-map` MCP server auto-registers from the plugin's [`.mcp.json`](./.mcp.json), which uses `${CLAUDE_PLUGIN_ROOT}` so it resolves to wherever the plugin is installed. Approve it when prompted. The first launch runs `uv`, which bootstraps the server's venv from its lockfile (needs network once; or pre-run `uv sync` in the installed `…/fathom/arch-map`). MCP/hook changes need `/reload-plugins` to take effect.

The spine is **multi-map**, so a single install serves *every* project — each gets its own map keyed by project name (stored under the plugin's `arch-map/maps/`).

**Just the living map (no skills):** register only the MCP, from any project, with an absolute path:

```bash
claude mcp add arch-map -- uv run --project /Users/benreich/skills/skills/fathom/arch-map arch-map
```

**Developing in *this* repo:** `${CLAUDE_PLUGIN_ROOT}` is only set when the plugin is installed, so the bundled `.mcp.json` won't auto-launch arch-map when this repo is opened directly. For local dev, run it explicitly — `uv run --project skills/fathom/arch-map arch-map` (stdio) or `… arch-map.web` (browser studio at `http://127.0.0.1:8800/`).

## Files (the `deepen` skill)

- [`SKILL.md`](./skills/deepen/SKILL.md) — the skill
- [`LANGUAGE.md`](./skills/fathom/LANGUAGE.md) — the shared vocabulary
- [`DEEPENING.md`](./skills/fathom/DEEPENING.md) — how to deepen a cluster safely, by dependency category
- [`INTERFACE-DESIGN.md`](./skills/fathom/INTERFACE-DESIGN.md) — exploring alternative interfaces for a deepened module
- [`HTML-REPORT.md`](./skills/fathom/HTML-REPORT.md) — the one-shot HTML report scaffold
- [`CONTEXT-FORMAT.md`](./skills/fathom/CONTEXT-FORMAT.md) — the `CONTEXT.md` domain-glossary format
- [`ADR-FORMAT.md`](./skills/fathom/ADR-FORMAT.md) — the ADR format
- [`arch-map/`](./skills/fathom/arch-map/) — the FastMCP spine + network-graph UI

Originally part of [mattpocock/skills](https://github.com/mattpocock/skills).
