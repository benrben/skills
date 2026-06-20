---
name: audit-extension
description: Audit a Claude Code Skill, Plugin, Marketplace, or MCP project against current best practices and produce a prioritized list of concrete fixes. Use when the user asks to review, audit, lint, check, or fix the structure of a SKILL.md, plugin.json, marketplace.json, .mcp.json, or any Claude extension repo.
disable-model-invocation: true
argument-hint: [path-to-project]
allowed-tools: Read Grep Glob Bash(claude plugin validate *)
---

# Claude Extension Best-Practice Audit

Audit the Claude Code extension project at `$ARGUMENTS` (default: current
directory). Scan the repo, classify it, check it against best practices, and
report a prioritized change list. **Do not modify files** — report first, then
ask permission to apply.

## Step 1 — Detect project type

Inspect the tree and classify as one or more of: Skill, Plugin, Marketplace,
MCP server.

- `SKILL.md` anywhere → Skill
- `.claude-plugin/plugin.json` → Plugin
- `.claude-plugin/marketplace.json` → Marketplace
- `.mcp.json` or `mcpServers` config → MCP server

Report detected type(s), the top-level layout, and any Claude Code version
hints found in manifests.

## Step 2 — Structural checks (BLOCKING)

- Component dirs (`skills/`, `agents/`, `hooks/`, `commands/`, `output-styles/`,
  `themes/`, `monitors/`) inside `.claude-plugin/` — only `plugin.json` belongs
  there; everything else must be at the plugin root.
- Paths traversing outside the plugin/marketplace root (`../`).
- Plugin file refs not using `${CLAUDE_PLUGIN_ROOT}`; persistent state not using
  `${CLAUDE_PLUGIN_DATA}`; skill script refs not using `${CLAUDE_SKILL_DIR}`.
- Manifest component paths that aren't relative / don't start with `./`.
- Marketplace relative-path `source` used with URL-based distribution.
- Missing required fields: plugin `name`; marketplace `name`/`owner`/`plugins`;
  each plugin entry `name`/`source`.
- A root `CLAUDE.md` relied on for context (plugins don't load it — use a skill).
- Non-kebab-case plugin/marketplace names; reserved marketplace names.

## Step 3 — Skill quality (for every SKILL.md)

- `description` present and high-quality: leads with the key use case + natural
  trigger phrases ("Use when…", "Trigger with…"). Trigger conditions go INSIDE
  `description` — `when_to_use` is NOT a frontmatter field. (Note: ~1,536 chars
  is only the listing-display cap, not an authoring limit; the real budget is
  dynamic. Judge on clarity, not character count.)
- Body concise (<500 lines; warn past ~600); move long reference material to
  linked sibling files (progressive disclosure).
- Bundled files are actually referenced from SKILL.md.
- Side-effecting skills set `disable-model-invocation: true`; pure background
  knowledge sets `user-invocable: false`. BLOCKING: flag the unreachable combo —
  both `disable-model-invocation: true` AND `user-invocable: false` means neither
  user nor model can invoke the skill.
- `allowed-tools` is SPACE-separated, not comma-separated (commas fail silently).
  Bash scoped via patterns, e.g. `Bash(git:*)`. Scope tightly.
- If `context: fork` is set, the body must contain an explicit task/goal (not
  just reference material) and pair with an `agent`.
- If `model:` is set, verify it names a current, available model.
- `argument-hint` is a slash-command field; confirm it's actually supported on
  skills before recommending it.
- Multi-skill plugins use `skills/<name>/` layout (not bare root SKILL.md).
- Deterministic logic moved from prose into bundled scripts where sensible.

## Step 4 — Plugin manifest & components

- Validate `plugin.json` JSON; check version strategy (semver+bump OR omit for
  git SHA — never set version in both plugin.json and the marketplace entry).
- Check the full manifest schema, not just the common fields: also
  `outputStyles`, `lspServers`, `settingsSchema`, and `experimental.*` (themes,
  monitors) where present.
- Component dirs at root and discoverable. Root-level config files also count:
  `.mcp.json`, `.lsp.json`, `settings.json`, `bin/`.
- Plugin agents: flag UNSUPPORTED frontmatter (`hooks`/`mcpServers`/
  `permissionMode`); confirm SUPPORTED fields are used correctly (name,
  description, model, tools/disallowedTools, skills, isolation: `worktree`).
- Hooks: valid case-sensitive event names (the set is 15+ — PreToolUse,
  PostToolUse, SessionStart/End, UserPromptSubmit, PreCompact, SubagentStop,
  Notification, …; check the hooks reference rather than assuming), valid `type`,
  executable scripts with shebang, paths quoted with `${CLAUDE_PLUGIN_ROOT}`.
- Recommend `README.md`, `CHANGELOG.md`, `LICENSE` if missing.

## Step 5 — MCP checks

- No hardcoded secrets. Prefer env expansion `${VAR:-default}` as the reliable
  path. `userConfig` (`sensitive: true`) + `${user_config.*}` exists but has
  known bugs (servers can silently fail to spawn; sensitive values may not
  persist) — flag it and recommend the env-var workaround.
- HTTP (Streamable HTTP) for remote — SSE is deprecated; stdio for local.
- Concise server `instructions` (<2KB, key terms first) for Tool Search.
- Bundled-server paths use `${CLAUDE_PLUGIN_ROOT}`.
- Large-output tools declare `"_meta": { "anthropic/maxResultSizeChars": N }`
  (cap 500000), not a bare key.
- Appropriate scope (project `.mcp.json` for teams; user `~/.claude.json` for
  local; managed `managed-mcp.json` allow/deny lists for enterprise).
- Tool-count hygiene: many-tool servers should narrow what loads — check for
  `alwaysLoad` misuse and tool filtering; rely on Tool Search by default.
- OAuth servers: validate loopback callback config (localhost / 127.0.0.1).

## Step 6 — Marketplace checks

- kebab-case names, top-level `description`, valid `owner`.
- Sources pinned with `sha` where reproducibility matters.
- `metadata.pluginRoot` used to simplify paths.
- `extraKnownMarketplaces` + `enabledPlugins` for team auto-setup.

## Step 7 — Validate

If a manifest exists, run `claude plugin validate <path> --strict` and fold the
output into the report.

## Step 8 — Output

Report `references/report-template.md`. For each issue give the exact file path
and a copy-pasteable corrected snippet, grouped by file. Order by impact.
End by asking: "Want me to apply these changes?"

See `references/best-practices.md` for the full rule rationale when you need to
explain or justify a finding.

These rules drift as Claude Code evolves. When a finding is borderline or a
manifest field looks unfamiliar, verify against the current docs before
reporting: code.claude.com/docs/en/skills, /plugins-reference, /hooks,
/plugin-marketplaces, /mcp, /managed-mcp, and modelcontextprotocol.io.
