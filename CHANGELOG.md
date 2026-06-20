# Changelog

## 0.3.0

- **Fixed plugin MCP wiring** — `.mcp.json` now launches the bundled `arch-map` server over **stdio** via `uv run --project ${CLAUDE_PLUGIN_ROOT}/fathom/arch-map arch-map` (plugin-root token), so it resolves wherever the plugin is installed. Dropped the stale `http` arch-map entry (no fixed host/port) and the bundled `playwright` server.
- **Added `archmap://` read resources** — the spine now exposes its model over MCP read resources, plus a `grill_candidate` MCP prompt.
- **Agent-friendlier tool responses** — `archmap_get_full_model` is now bounded; created-entity calls return acknowledgements; no silent map auto-create; uniform guarded errors; and paged results.
- **Skills** — gained parallel-worktree guidance, and the `code` skill got an `allowed-tools` line.
