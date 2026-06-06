This repo is the **Fathom** Claude Code plugin + marketplace. Each skill is a direct child of `skills/`, holding a `SKILL.md`:

```
skills/
  <skill-name>/SKILL.md   # one folder per skill — auto-discovered by the plugin loader
  fathom/                 # shared substrate (arch-map MCP spine + format docs); NOT a skill (no SKILL.md)
  README.md               # index listing every skill, name linked to its SKILL.md
```

Plugin skills are auto-discovered **one level deep** — Claude Code scans `skills/*/SKILL.md`. Do **not** nest skills under bucket folders (e.g. `skills/engineering/map/`); the loader won't find them and `.claude-plugin/plugin.json` has no supported field to point at deeper paths. Anything under `skills/` without a `SKILL.md` (like `fathom/`) is ignored by discovery, which is how the shared substrate lives there safely.

When adding or removing a skill:

- Add/remove its `skills/<name>/SKILL.md` folder.
- Reference it in the top-level `README.md`, with the skill name linked to its `SKILL.md`.
- List it in `skills/README.md` with a one-line description, name linked to its `SKILL.md`.

`.claude-plugin/plugin.json` needs no `skills` array — discovery is automatic.
