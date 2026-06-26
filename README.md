# Fathom

A suite of Claude Code skills built on one principle and one shared model: turn **shallow** modules (interface ≈ as complex as the implementation) into **deep** ones — a lot of behaviour behind a small interface — for the sake of testability and AI-navigability.

The skills don't just analyse; they share a **living architecture model** — the `arch-map` MCP **spine** — that each one reads and writes, so a codebase becomes something humans *and* agents can reason about by depth.

## The principle

Every skill speaks one vocabulary ([LANGUAGE.md](./fathom/LANGUAGE.md)) — **module, interface, depth, seam, adapter, leverage, locality** — and obeys the same rules: the **deletion test** (if a module vanished, would complexity concentrate behind a small interface, or just scatter?), **the interface is the test surface**, and **one adapter = a hypothetical seam, two = a real one**. Architecture is reasoned about by *depth*, never by "components/services/APIs/boundaries."

## The suite

Five skills, one engineer cycle — **map → understand → design → code**, with `review` gating changes. The three writers (`map`, `design`, `code`) never share a slice; the two read-only skills (`understand`, `review`) bookend the loop. All speak one vocabulary and share one model — and all **docs live only on the spine** (no `docs/` files), in eleven types ([DOC-TYPES.md](./fathom/DOC-TYPES.md)). The **task board** ([BOARD.md](./fathom/BOARD.md)) makes that cycle trackable — one column per skill, one worktree per task.

- [`map`](./skills/map/SKILL.md) — observe & record what the codebase IS: modules, depth, edges, leaks, coverage, **all** signals — and capture the recorded truth around it as docs of every type (glossary, note, risk, runbook, postmortem, diagram, and the adr for a decision baked into the code). The doc **registrar** (absorbs the old `adr-writer`) and keeper of worktree truth.
- [`understand`](./skills/understand/SKILL.md) — a read-only guided tour of the map, **its docs**, and **the work in flight** on the board (entry interfaces, deepest modules, leak hot-spots, active tasks/agents/worktrees), ending with the named next action. The front door; writes nothing. Explains the **understand** column.
- [`design`](./skills/design/SKILL.md) — decide the deep structure, two modes by request: **improve** an existing shallow module (flag a candidate, grill it) or design **new** intended structure (seams, interfaces, sequenced steps). Writes candidates, intended modules, Plans, and rfc/spec/adr/diagram docs. Merges the old `deepen` + `plan`. Owns the **plan** column — sequences each step as a board task with its own worktree.
- [`code`](./skills/code/SKILL.md) — execute a chosen target (refactor shallow→deep, build to a planned interface, or write interface tests), following [MINIMALISM.md](./fathom/MINIMALISM.md), **inside the task's own git worktree**. The **only** skill that edits source. Owns the **in-progress** column.
- [`review`](./skills/review/SKILL.md) — review a diff/PR (often a task's worktree branch) **through the map**: modules touched, seams crossed, danger-zones touched without tests, interface erosion. Read-only (may record a `risk`/`postmortem` doc, and move the card); the change gate. Owns the **review** column.

## The spine: `arch-map`

The suite ships a [FastMCP](https://github.com/jlowin/fastmcp) server at [`arch-map/`](./fathom/arch-map/) — the persistent model every skill reads and writes. A UI-capable host renders it inline via [MCP Apps](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/): depth = node fill, coverage = ring, suggestions = ⚠ ring, leaks = red edge, orphans = a "not connected" tray — plus the **task board** (the Graph ↔ Board toggle). Registered for this repo in [`.mcp.json`](./.mcp.json). See the [arch-map README](./fathom/arch-map/README.md).

The spine has a strict split: **reads of stored state are MCP resources; writes and computed queries are tools.**

### Reading stored state — `archmap://` resources (YAML; docs as Markdown)

Every read of stored map state is an MCP **resource**, addressed by an `archmap://` URI. A structured resource returns **YAML** (`mime_type: application/yaml`) — not a JSON dict. A single doc returns **Markdown** (`mime_type: text/markdown`). The resources are the *only* way to read stored state:

| resource URI | returns |
|---|---|
| `archmap://maps{?q}` | every project map (id, label, repo, counts) |
| `archmap://{map}/model{?domain,plane,lifecycle,sort,dir,q,limit,offset}` | the full module model |
| `archmap://{map}/digest{?domain}` | the map digest + staleness line |
| `archmap://{map}/board` | the skill-cycle task board (Kanban) |
| `archmap://{map}/module/{id}` | one module's detail |
| `archmap://{map}/metrics{?sort,dir,limit,offset}` | per-module metrics (churn / coverage / size) |
| `archmap://{map}/metrics/{module}` | one module's metrics |
| `archmap://{map}/docs{?type,tag,status,domain,q}` | the doc summaries (YAML list) |
| `archmap://{map}/doc/{id}` | one doc, as **Markdown** (YAML frontmatter + raw body; a `diagram` body is fenced as `mermaid`) |
| `archmap://{map}/plans{?status}` | the Plans |
| `archmap://{map}/plan/{id}` | one Plan |
| `archmap://{map}/worktrees{?status}` | the per-task git worktrees |

**Query-param vocabulary** (RFC 6570 — all optional): `domain` · `plane` · `lifecycle` · `type` · `tag` · `status` are **exact match**; `q` is a **case-insensitive substring** search (over module id/label/interface, doc title/summary, or map id/repo); `sort` = a field name with `dir` = `asc|desc`; `limit` + `offset` page the result — the returned payload carries `total_count`, `has_more`, and `next_offset`. Two examples:

```
archmap://payments/model?domain=billing&sort=depth&dir=desc&limit=20
archmap://payments/docs?type=adr&status=accepted&q=retry
```

The first returns the 20 deepest modules in the `billing` domain; the second returns accepted ADRs whose title or summary contains "retry".

### The 16 tools — writes + computed queries only

Tools no longer read stored state. The remaining **16 tools** are **writes** and **computed queries** (a computed query derives a fresh answer from the code or the model rather than returning stored state): `archmap_create_map`, `archmap_rename_map`, `archmap_delete_map`, the dispatchers `archmap_modules` / `archmap_docs` / `archmap_plans` / `archmap_worktrees` / `archmap_suggestions` / `archmap_grilling` (now **write-only** — their read actions, e.g. modules `get`, docs `get`/`list`, plans `get`, worktrees `list`, were stripped and are resources instead), plus the computed queries `archmap_ingest`, `archmap_render_view`, `archmap_scan_signals`, `archmap_drift`, `archmap_verify_edges`, `archmap_whatif`, and `archmap_history`. One MCP **prompt** remains: `grill_candidate(map, suggestion_id)`. The five removed read tools (`archmap_list_maps`, `archmap_show_map`, `archmap_get_full_model`, `archmap_board`, `archmap_get_metrics`) are now the resources above. Tool results themselves are returned as **YAML** too (one text block, no JSON `structuredContent`), so the whole MCP surface is YAML/Markdown; only the studio `/api/*` routes stay JSON.

**Why YAML / Markdown:** YAML drops JSON's braces, quotes, and commas and leans on indentation for nesting, so a structured payload costs fewer tokens than the equivalent JSON. Returning a doc as Markdown (frontmatter + raw body) avoids JSON-escaping the prose entirely — the body is passed through verbatim. Lower token cost per read is the whole point.

**Tradeoff:** an MCP client that supports tools but **not** resources can no longer read the map at all — every read now lives behind an `archmap://` resource. Such clients can still *write* (the 16 tools) but are blind to stored state. Full MCP clients (resources + tools) are unaffected.

## The task board & per-task worktrees

The same spine projects every Plan's WorkSteps into a **task board** — a Kanban whose **columns are the skill cycle** (`todo · understand · plan · in-progress · review · done`, each column owned by a skill) and whose **rows are the agents** carrying each task. A card can be built in its own **git worktree** — an isolated branch — so several tasks (and the agents on them) run in parallel without colliding. The board is the cycle made *trackable*: a card flows left→right, its agent and worktree travelling with it. It's not a sixth skill — it's spine state + a studio surface the five skills drive (read it via the `archmap://{map}/board` resource; mutate it via the `archmap_worktrees` and `archmap_plans` step tools). In the studio a header **Graph ↔ Board** toggle (`b`) swaps the graph for the board; drag a card to move its stage, ＋ a worktree, ▶ dispatch an agent into it. Real `git worktree` work is ON by default and guarded like `/api/dispatch` (same-origin + `ARCH_MAP_ALLOW_WORKTREE`); see [BOARD.md](./fathom/BOARD.md).

## Keep the map true: measured facts, drift, and the weekly pulse

The spine measures its own facts instead of trusting estimates. `archmap_ingest(map, root=…)` computes **churn** from git history, **coverage** from a real test report (coverage.py XML/JSON or lcov), and **size** (implementation mass) from each module's measured LOC — normalized so 1.0 is the median module, which is what the `bulky-impl` signal reads — and records a reconcile **anchor** (git sha + per-module health snapshot). From there:

- `archmap_drift(map)` — what changed since the last anchor; the map digest (resource `archmap://{map}/digest`) opens with the same staleness line ("3 files changed, 2 modules touched since `a1b2c3d`").
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

This repo is a self-contained Claude Code **plugin + marketplace** (`fathom`). Installing it brings **all five skills _and_ the `arch-map` MCP spine** in one step.

**Prerequisite:** [`uv`](https://docs.astral.sh/uv/) on your `PATH` (the MCP server runs via `uv run`).

```bash
cd /path/to/your/other-project
/plugin marketplace add https://github.com/benrben/fathom      # or a local clone: /path/to/fathom
/plugin install fathom@benrben
```

That gives you:

- **The skills** — the slash commands `/map`, `/understand`, `/design`, `/code`, `/review` (auto-registered from the plugin; `SKILL.md` edits hot-reload).
- **The spine** — the `arch-map` MCP auto-registers from the plugin's [`.mcp.json`](./.mcp.json), which runs the bundled server over **STDIO** via `uv run --project ${CLAUDE_PLUGIN_ROOT}/fathom/arch-map arch-map` (no fixed host/port — the host launches the process and talks to it on stdin/stdout, and `${CLAUDE_PLUGIN_ROOT}` resolves to wherever the plugin is installed). Approve it when prompted. The first launch runs `uv`, which bootstraps the server's venv from its lockfile (needs network once; or pre-run `uv sync` in the installed `…/fathom/arch-map`). MCP/hook changes need `/reload-plugins` to take effect. The browser studio is a **separate, optional** command — `./run-mcp.sh web` — not part of the auto-registered MCP.

The spine is **multi-map**, so a single install serves *every* project — each gets its own map keyed by project name (stored under the plugin's `arch-map/maps/`).

**Just the living map (no skills):** register only the MCP, from any project, with an absolute path:

```bash
claude mcp add arch-map -- uv run --project /path/to/fathom/fathom/arch-map arch-map
```

**Developing in *this* repo:** `${CLAUDE_PLUGIN_ROOT}` is only set when the plugin is installed, so the bundled `.mcp.json` won't auto-launch arch-map when this repo is opened directly. For local dev, run it explicitly — `uv run --project fathom/arch-map arch-map` (stdio) or `… arch-map.web` (browser studio at `http://127.0.0.1:8800/`).

## The shared substrate (`fathom/`)

Fathom also carries a **craft layer** ([`fathom/craft/`](./fathom/craft/README.md)) — the line-level discipline from *Clean Code* (names, functions, errors, tests, structure, comments, smells), generalized to any language and wired into `code` (write it well behind the seam), `review` (the craft pass), and `design` (structural smells).

- [`LANGUAGE.md`](./fathom/LANGUAGE.md) — the shared vocabulary
- [`DOC-TYPES.md`](./fathom/DOC-TYPES.md) — the eleven spine doc types, their owners, lifecycles, and the ADR three-gate test
- [`DEEPENING.md`](./fathom/DEEPENING.md) — how to deepen a cluster safely, by dependency category
- [`MINIMALISM.md`](./fathom/MINIMALISM.md) — write less code without losing the seam (drive `size` down, hold `depth`)
- [`INTERFACE-DESIGN.md`](./fathom/INTERFACE-DESIGN.md) — exploring alternative interfaces for a module
- [`HTML-REPORT.md`](./fathom/HTML-REPORT.md) — the one-shot HTML report scaffold
- [`CONTEXT-FORMAT.md`](./fathom/CONTEXT-FORMAT.md) — the content discipline for a `glossary` doc
- [`BOARD.md`](./fathom/BOARD.md) — the skill-cycle task board + per-task worktree workflow
- [`arch-map/`](./fathom/arch-map/) — the FastMCP spine + network-graph UI

Originally part of [mattpocock/skills](https://github.com/mattpocock/skills).
