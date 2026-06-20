# arch-map

A **living codebase architecture map**, served as a [FastMCP](https://github.com/jlowin/fastmcp) server with an [MCP Apps](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/) network-graph UI. The companion runtime for the `/improve-codebase-architecture` skill: the agent keeps an architecture *model* current by calling tools; a UI-capable host renders it **inline in the conversation**.

## The idea

```
 PROJECT AGENT ──calls tools──►  arch-map (FastMCP)  ──ui:// resource──►  host renders
 (Claude in repo)                 holds the model       network graph        inline graph
        ▲                         + tools                                        │
        └──────────────── archmap_grilling(action="start")  ◄── app.callServerTool ◄── click in UI ┘
```

The agent never writes HTML. It calls `archmap_suggestions(action="flag", ...)`, `archmap_modules(action="update", depth=...)`, `archmap_modules(action="update", updated=...)`. The graph redraws from the model each time. Clicking a node's **Grill this candidate →** button calls back into the server.

## Two rendering lanes (hybrid)

- **Lane 1 — the studio, everywhere** ([`arch_map/ui/studio/`](arch_map/ui/studio/)): the *same* studio served in the browser is also inlined as the `ui://arch/network.html` MCP-App resource, so a UI-capable host renders it **inline** — driven by the tools. `archmap_show_map` names the map, `archmap_get_full_model` feeds the full model, and `archmap_modules` (action="update", depth=…)/`archmap_modules` (action="add")/`archmap_suggestions` (action="decide")/… mutate it (the studio routes these through `app.callServerTool`). Its `state.js` has two transports — HTTP for the browser, the [`@modelcontextprotocol/ext-apps`](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/) host bridge for MCP-App hosts — picked by a flag the server injects when inlining. (The old self-contained `network.html` is kept for history.)
- **Lane 2 — FastMCP Generative UI** (Prefab): `mcp.add_provider(GenerativeUI())` for ad-hoc charts/tables the model improvises. *Off by default* — it needs the `prefab-ui` extra and renders in Prefab's generic look (no arch-map design); the studio is the on-brand surface. See [FastMCP docs](https://gofastmcp.com/apps/generative).

## What the graph encodes

| Visual | Meaning |
|---|---|
| node **fill** | depth — dark = deep · slate = mid · amber = shallow (more behaviour behind a small interface) |
| green **ring** | test coverage at the interface (arc length = %) |
| blue pulsing **halo** | updated since the last scan |
| coloured **ring + ⚠** | open deepening suggestion (emerald = Strong, amber = Worth exploring, slate = Speculative) |
| red dashed **edge** | a leak across a seam |
| gray **edge** | dependency |
| **orphan tray** | modules with no edges — "not connected" |

Filter chips: **Suggestions · Updated · Leaks · Low coverage · Not connected**. Hover traces a node's connections; click opens its detail + suggestion card.

## Projects (named maps)

The server holds **many maps — one per project** — each its own JSON file under
[`maps/`](maps/) (e.g. `maps/mr-meeseeks.json`). Maps are **always shared**: there
is no per-agent access control, any client can read or write any of them. Every
tool and HTTP route takes an explicit **`map`** id to say which project it acts on.

Create one with `archmap_create_map("Mr. Meeseeks")` (slugs to the id `mr-meeseeks`)
or, for an explicit id, `archmap_create_map(name, map_id, repo)`. The studio's header has a project
switcher (pick a project, or type a name to create one); a browser deep-links a
project with `?map=<id>`. A pre-existing single `arch_state.json` is migrated into
`maps/<repo>.json` once, non-destructively.

| map tool | effect |
|---|---|
| `archmap_list_maps()` | list every project map (id, label, counts) |
| `archmap_create_map(name)` | create a project; returns its `map` id to use next |
| `archmap_create_map(name, map_id, repo)` | create a map with an explicit id |
| `archmap_rename_map(map, to, repo)` | rename / relabel a map |
| `archmap_delete_map(map)` | delete a map and its file |

## Tools the agent drives

All take `map` — the project map to act on (see above).

| tool | effect |
|---|---|
| `archmap_show_map(map)` | render that project's network (lightweight; names the map for the inline studio) |
| `archmap_get_full_model(map)` | full model (interfaces/files/tests/suggestion bodies) — what the inline studio renders |
| `archmap_suggestions(map, action="decide", suggestion_id=, decision=, note=)` | record accept/defer/reject (or `""` to re-open) |
| `archmap_suggestions(map, action="flag", module=, title=, strength=, category=, problem=, solution=, wins=)` | attach a suggestion |
| `archmap_modules(map, action="update", id=, depth=)` | update depth (0–1) |
| `archmap_modules(map, action="update", id=, coverage=)` | update coverage (0–1) |
| `archmap_modules(map, action="update", id=, updated=True)` | toggle the updated halo |
| `archmap_suggestions(map, action="dismiss", suggestion_id=)` | dismiss a suggestion |
| `archmap_modules` with `action="add"` / `"update"` / `"delete"` (+ bulk via `items=`/`ids=`) | module CRUD on `map` |
| `archmap_render_view(map, kind=, of=, ...)` | on-brand ad-hoc **view** — a table or bar chart of the map, drawn with the studio's design (the on-brand answer to "chart depth", "table of orphans"). Browser: `/view?map=…&kind=bar&metric=coverage&groupBy=domain` |
| `archmap_grilling(map, action="start", module=)` | UI callback → hands off to the grilling loop |

## Run

```bash
uv run arch-map          # or:  pip install -e . && python -m arch_map.server
```

Point a **UI-capable host** at the server to *see* the graph:
**Claude desktop & web · VS Code Insiders · Goose · ChatGPT**. A plain terminal Claude Code session can drive the tools but can't draw the iframe — use one of those hosts (or the standalone preview) to view it.

## Browser UI — the studio

Run the HTTP app and open it in any browser — no host needed:

```bash
python -m arch_map.web        # -> http://127.0.0.1:8800/
```

The studio (HTTP) runs on any FastMCP — it does **not** need the `fastmcp[apps]`
extra. The two inline-render lanes degrade independently: Lane 1 (the MCP-App
network graph) activates when `fastmcp.apps` is importable; Lane 2 (Prefab) when
the `prefab-ui` extra is also present. Missing either just disables that lane;
the browser studio is unaffected. (Use the project's `uv run` / `.venv` for the
pinned FastMCP 3.x if you want the MCP-App lane.)

`/` (and the `/map` alias) serve the **studio** — one workspace that merges what
used to be two pages (the network graph and the decisions board) around the loop
you actually run: *the agent proposes, you inspect against the live graph, you
decide.*

- **The graph is the canvas** — a deterministic dagre-layered DAG. Fill = depth
  tier, vertical position = dependency depth, bottom bar = coverage, ring + `!` =
  an open proposal, blue outline = updated. Hover a card to spotlight its
  neighbourhood; click to inspect. Level-of-detail collapses cards to pins when
  zoomed out. Pan/zoom/fit, filter chips, `/`-search (with `?q=` deep-link), an
  `⇢ all edges` toggle, and an orphan tray.
- **The rail is the agent** — three tabs: **Proposals** (the deepening queue;
  Accept / Defer / Reject record a decision, Dismiss resolves it, each with a
  reason), **Inspector** (interface, depth/coverage steppers, depends-on /
  used-by pills, files, tests, and the proposal in context), and **Modules** (a
  filterable list with add/delete).
- Two aesthetic directions × light/dark (top-right), keyboard shortcuts
  (`1/2/3` tabs, `/` search, `Esc` deselect), and a first-run intro + a `?`
  legend. Collapse the rail with **Hide agent** to go full-graph.

The studio is served from `arch_map/ui/studio/` (`index.html` + `/assets/*`). Its
data layer (`shared/state.js`) reads the full model from `GET /api/model` and
POSTs every triage/edit to `/api/act`, which mutates `arch_state.json` under a
lock. It polls `/api/model` every 2.5s, so a change from the agent (via MCP
tools), the desktop app, or another browser tab shows up without a reload — one
source of truth across every surface.

> The legacy single-purpose pages (`ui/network.html`, `ui/decisions.html`) are
> superseded by the studio on every surface — the studio is now both the browser
> page *and* the inline MCP-App resource (Lane 1). They're kept only for history.

## Status / caveats

- The tool→UI link goes through `fastmcp.apps.AppConfig` on **both** the tool (`resourceUri`) and the resource, which emits the `_meta.ui` block hosts read; a hand-rolled `meta` dict is silently ignored.
- The model is **file-backed** (`arch_state.json`) and **starts empty — no sample is seeded**. A real `scan_repo()` (parse the call graph → emit the model) is the obvious next step.
