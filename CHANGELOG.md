# Changelog

## 0.5.0

- **Craft dimension.** A line-level craft layer (Clean Code, generalized) beneath the architecture altitude: the `fathom/craft/` substrate (naming, functions, errors, tests, structure, comments, smells) referenced by the skills; a `craft_ingest` source measurer; seven craft signals (`long-function`, `too-many-args`, `deep-nesting`, `large-class`, `untested-interface`, `magic-number`, `comment-smell`) via `archmap_scan_signals(family="craft")`; `review` gained a craft pass (§4a).
- **Measured indicators (`measure.py`).** `depthProxy` (leverage = implementation ÷ interface-surface, median-normalized), `cohesion`, `ifaceSize`, and import-implied `dependsOn` — measured facts the map curates instead of judging. A `depth-overstated` signal holds judged `depth` accountable to the proxy. Plus `infer_category` (DEEPENING), `interface_coverage`, and `cluster_by_imports`.
- **Declarative signal registry.** `SIGNAL_REGISTRY` is the single source for every signal's id/family/why/how (was an if-ladder); exposed in `/api/model`, so the studio renders from it. Studio gains a **craft-lens** toggle + an `architecture|craft` issues filter; thresholds are tunable (`_T`); the craft parser strips strings/comments and memoizes by content sha.
- **Skill scripts.** `map/{seed,measure}`, `design/{propose,whatif_craft}`, `review/check_interface`, `code/scaffold_characterization` — the deterministic work runs as bundled scripts, not re-reasoning.
- **Tool surface unchanged (16).** All additive: new measured `Module` fields, signals via the registry, scripts (not tools). 20 new tests; full suite + ui-tests green.


## 0.4.0

- **Read → resource migration.** Reads of stored map state are now MCP **resources**, not tools. Removed the five read tools (`archmap_list_maps`, `archmap_show_map`, `archmap_get_full_model`, `archmap_board`, `archmap_get_metrics`) and stripped the read actions from the dispatchers (modules `get`; docs `get`/`list`; plans `get`; worktrees `list`), making those dispatchers write-only. The full `archmap://` resource surface (maps, model, digest, board, module, metrics, docs, doc, plans, plan, worktrees) carries RFC 6570 query params for filter (`domain`/`plane`/`lifecycle`/`type`/`tag`/`status` exact, `q` substring), `sort`/`dir`, and `limit`/`offset` paging (`total_count`/`has_more`/`next_offset` in the payload). **16 tools remain** — writes + computed queries (`ingest`/`render_view`/`scan_signals`/`drift`/`verify_edges`/`whatif`/`history`) — plus the `grill_candidate` prompt.
- **YAML / Markdown serialization.** Every structured resource returns **YAML** (`mime_type: application/yaml`) via a shared `_yaml()` helper (`pyyaml`), instead of a JSON dict — dropping JSON's braces/quotes/commas to cut token cost. A single doc returns **Markdown** (`mime_type: text/markdown`): YAML frontmatter + the raw body verbatim (a `diagram` body fenced as `mermaid`), avoiding JSON-escaping of prose.
- **Tool responses are YAML too.** Every MCP tool result (writes + computed queries) is now YAML text with no JSON `structuredContent`, via a `YamlToolOutput` middleware + output-schema stripping — so the entire MCP surface (tools *and* resources) is YAML/Markdown. The studio `/api/*` HTTP routes stay JSON (the browser UI needs them).
- **Tradeoff:** a tools-only MCP client (no resource support) can no longer read the map — only write it.

## 0.3.0

- **Fixed plugin MCP wiring** — `.mcp.json` now launches the bundled `arch-map` server over **stdio** via `uv run --project ${CLAUDE_PLUGIN_ROOT}/fathom/arch-map arch-map` (plugin-root token), so it resolves wherever the plugin is installed. Dropped the stale `http` arch-map entry (no fixed host/port) and the bundled `playwright` server.
- **Added `archmap://` read resources** — the spine now exposes its model over MCP read resources, plus a `grill_candidate` MCP prompt.
- **Agent-friendlier tool responses** — `archmap_get_full_model` is now bounded; created-entity calls return acknowledgements; no silent map auto-create; uniform guarded errors; and paged results.
- **Skills** — gained parallel-worktree guidance, and the `code` skill got an `allowed-tools` line.
