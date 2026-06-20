This repo is the **Fathom** Claude Code plugin + marketplace. Each skill is a direct child of `skills/`, holding a `SKILL.md`. The shared substrate — the arch-map MCP spine + the format docs — lives in `fathom/` at the **repo root**, deliberately OUTSIDE `skills/`, because it is not a skill:

```
skills/
  <skill-name>/SKILL.md   # one folder per skill — auto-discovered by the plugin loader
  README.md               # index listing every skill, name linked to its SKILL.md
fathom/                   # shared substrate (arch-map MCP spine + format docs); NOT a skill, at the repo root
.mcp.json                 # launches the bundled stdio spine: uv run --project ${CLAUDE_PLUGIN_ROOT}/fathom/arch-map arch-map
```

Plugin skills are auto-discovered **one level deep** — Claude Code scans `skills/*/SKILL.md`. Do **not** nest skills under bucket folders (e.g. `skills/engineering/map/`); the loader won't find them and `.claude-plugin/plugin.json` has no supported field to point at deeper paths. Keep all non-skill material (the `fathom/` substrate, the MCP server) at the repo root, OUT of `skills/`, so discovery never sees it. Skill bodies reference the substrate as `../../fathom/<doc>.md` (up from `skills/<name>/` to the repo root).

When adding or removing a skill:

- Add/remove its `skills/<name>/SKILL.md` folder.
- Reference it in the top-level `README.md`, with the skill name linked to its `SKILL.md`.
- List it in `skills/README.md` with a one-line description, name linked to its `SKILL.md`.

`.claude-plugin/plugin.json` needs no `skills` array — discovery is automatic.

## The spine's MCP surface: reads are resources, writes are tools

The `arch-map` spine splits its surface strictly: **reads of stored state are MCP resources** (returning **YAML**, `mime_type: application/yaml`; a single doc returns **Markdown**, `mime_type: text/markdown`), and **writes plus computed queries are tools**. When a skill needs to *read* stored map state, it reads an `archmap://` resource — never a tool. Tools are only for mutations and for computed/derived answers.

State-read resources (all optional query params are RFC 6570):

```
archmap://maps{?q}
archmap://{map}/model{?domain,plane,lifecycle,sort,dir,q,limit,offset}
archmap://{map}/digest{?domain}
archmap://{map}/board
archmap://{map}/module/{id}
archmap://{map}/metrics{?sort,dir,limit,offset}
archmap://{map}/metrics/{module}
archmap://{map}/docs{?type,tag,status,domain,q}
archmap://{map}/doc/{id}          # Markdown: YAML frontmatter + raw body
archmap://{map}/plans{?status}
archmap://{map}/plan/{id}
archmap://{map}/worktrees{?status}
```

Query vocabulary: `domain`/`plane`/`lifecycle`/`type`/`tag`/`status` = exact match; `q` = case-insensitive substring; `sort` + `dir` (`asc|desc`); `limit`/`offset` page with `total_count`/`has_more`/`next_offset` in the payload. Examples: `archmap://payments/model?domain=billing&sort=depth&dir=desc&limit=20` and `archmap://payments/docs?type=adr&status=accepted&q=retry`.

The **16 remaining tools** are writes + computed queries only: `archmap_create_map`, `archmap_rename_map`, `archmap_delete_map`, the now write-only dispatchers `archmap_modules`/`archmap_docs`/`archmap_plans`/`archmap_worktrees`/`archmap_suggestions`/`archmap_grilling`, and the computed queries `archmap_ingest`/`archmap_render_view`/`archmap_scan_signals`/`archmap_drift`/`archmap_verify_edges`/`archmap_whatif`/`archmap_history`. One prompt remains: `grill_candidate(map, suggestion_id)`. The old read tools (`archmap_list_maps`, `archmap_show_map`, `archmap_get_full_model`, `archmap_board`, `archmap_get_metrics`, and the read actions on the dispatchers) are gone — read the resources instead.

YAML/Markdown is a token-cost choice: YAML drops JSON braces/quotes/commas, and a doc's Markdown body is passed through verbatim instead of being JSON-escaped. **Tradeoff:** a tools-only MCP client (no resource support) can no longer read the map — only write it.
