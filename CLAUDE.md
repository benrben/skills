This repo is the **Fathom** Claude Code plugin + marketplace. Each skill is a direct child of `skills/`, holding a `SKILL.md`. The shared substrate — the arch-map MCP spine + the format docs — lives in `fathom/` at the **repo root**, deliberately OUTSIDE `skills/`, because it is not a skill:

```
skills/
  <skill-name>/SKILL.md   # one folder per skill — auto-discovered by the plugin loader
  README.md               # index listing every skill, name linked to its SKILL.md
fathom/                   # shared substrate (arch-map MCP spine + format docs); NOT a skill, at the repo root
.mcp.json                 # registers the spine at ${CLAUDE_PLUGIN_ROOT}/fathom/arch-map
```

Plugin skills are auto-discovered **one level deep** — Claude Code scans `skills/*/SKILL.md`. Do **not** nest skills under bucket folders (e.g. `skills/engineering/map/`); the loader won't find them and `.claude-plugin/plugin.json` has no supported field to point at deeper paths. Keep all non-skill material (the `fathom/` substrate, the MCP server) at the repo root, OUT of `skills/`, so discovery never sees it. Skill bodies reference the substrate as `../../fathom/<doc>.md` (up from `skills/<name>/` to the repo root).

When adding or removing a skill:

- Add/remove its `skills/<name>/SKILL.md` folder.
- Reference it in the top-level `README.md`, with the skill name linked to its `SKILL.md`.
- List it in `skills/README.md` with a one-line description, name linked to its `SKILL.md`.

`.claude-plugin/plugin.json` needs no `skills` array — discovery is automatic.
