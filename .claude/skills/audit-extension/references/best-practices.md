# Rule rationale (loaded only when justifying a finding)

## Progressive disclosure

Only skill names/descriptions load at startup; the body loads on invoke;
bundled files load when navigated; scripts run without entering context. Optimize
for context cost at every level.

## Skills

- Description is the trigger signal — key use case + trigger phrases first
  ("Use when…", "Trigger with…"). Trigger conditions live INSIDE `description`;
  `when_to_use` is not a frontmatter field. ~1,536 chars is the listing-display
  cap only; the real budget is dynamic (~1% of context), so judge on clarity.
- Invoked skill bodies persist across turns = recurring token cost; keep <500
  lines (warn past ~600); state what to do, not why.
- `${CLAUDE_SKILL_DIR}` for bundled scripts so paths resolve anywhere.
- `context: fork` + `agent` to run isolated; `paths` to auto-scope by file. A
  forked skill needs an explicit task in its body, not just reference notes.
- `allowed-tools` is space-separated; commas fail silently. Scope `Bash(...)`.
- Unreachable combo: `disable-model-invocation: true` + `user-invocable: false`
  leaves no way to invoke the skill.

## Plugins

- Only `plugin.json` lives in `.claude-plugin/`; all component dirs at root.
- `${CLAUDE_PLUGIN_ROOT}` for bundled files (plugins are copied to a cache, so
  `../` breaks); `${CLAUDE_PLUGIN_DATA}` for state surviving updates.
- Root `CLAUDE.md` is NOT loaded — ship instructions as a skill.
- Versioning: semver + bump, or omit version to use git SHA. Never both.
- Manifest covers more than the basics: `outputStyles`, `lspServers`,
  `settingsSchema`, `experimental.*`. Root configs: `.mcp.json`, `.lsp.json`,
  `settings.json`, `bin/`.
- Plugin agents support name/description/model/tools/skills/isolation(`worktree`)
  but NOT hooks/mcpServers/permissionMode. Hook events are case-sensitive and
  number 15+; check the hooks reference rather than assuming the set.

## MCP

- HTTP (Streamable HTTP) for remote (SSE deprecated), stdio for local.
- Secrets via env expansion `${VAR:-default}` (reliable) — never hardcoded.
  `userConfig` + `${user_config.*}` exists but is buggy (spawn failures, values
  not persisted); recommend the env-var workaround.
- Concise server instructions (<2KB, key terms first) drive Tool Search.
- `"_meta": { "anthropic/maxResultSizeChars": N }` (cap 500000) for large-output
  tools — keep results durable through compaction.
- Scopes: project `.mcp.json` (team), user `~/.claude.json` (local), managed
  `managed-mcp.json` (enterprise allow/deny). `alwaysLoad` bypasses Tool Search.
- OAuth: loopback callback (localhost / 127.0.0.1), port-agnostic per RFC 8252.

## Marketplaces

- kebab-case names (Claude.ai sync rejects others); avoid reserved names.
- Pin sources with `sha`; use `metadata.pluginRoot`.
- Relative-path sources only work for git-based (not URL-based) marketplaces.
- `extraKnownMarketplaces` + `enabledPlugins` in `.claude/settings.json` for teams.
