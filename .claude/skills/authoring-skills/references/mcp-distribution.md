# Distributing & Consuming Skills over MCP

How a `SKILL.md` directory becomes a protocol-standard resource any MCP client can discover, download, and use — via FastMCP's Skills Provider (v3.0+). Read when a skill must work over MCP or be shared across tools. Verify API specifics against gofastmcp.com for the installed FastMCP version, since FastMCP iterates quickly.

## Contents
- The key idea: skills are already portable
- Serving skills: SkillsDirectoryProvider / SkillProvider
- Vendor providers (Claude, Cursor, VS Code, …)
- The skill:// URI scheme and manifest
- Supporting-files modes and reload
- Consuming skills: client utilities
- Portability rules (write once, run local + MCP)

## The key idea

A skill authored to the core standard needs **no changes** to be served over MCP. The same directory works as a local `.claude/skills/<name>/` install *and* as an MCP resource. The difference is only *how it's delivered*: locally the host reads files from disk; over MCP a server exposes them as `skill://` resources that clients list, read, and download.

## Serving skills

FastMCP's Skills Provider turns a skills directory into MCP resources. Two layers:

```python
from pathlib import Path
from fastmcp import FastMCP
from fastmcp.server.providers.skills import SkillsDirectoryProvider, SkillProvider

mcp = FastMCP("Skills Server")

# Expose a whole directory (one SkillProvider per valid skill folder found):
mcp.add_provider(SkillsDirectoryProvider(roots=Path.home() / ".claude" / "skills"))

# Or expose exactly one skill:
mcp.add_provider(SkillProvider(Path.home() / ".claude" / "skills" / "authoring-skills"))
```

A folder counts as a skill if it contains the main file (default `SKILL.md`). Multiple roots are allowed — pass a list; the **first root wins** on name collisions:

```python
SkillsDirectoryProvider(roots=[
    Path.cwd() / ".claude" / "skills",     # project-level first
    Path.home() / ".claude" / "skills",    # user-level fallback
])
```

## Vendor providers

Presets that lock `roots` to a platform's default directory (all accept the same options except `roots`):

| Provider | Default directory |
|---|---|
| `ClaudeSkillsProvider` | `~/.claude/skills/` |
| `CursorSkillsProvider` | `~/.cursor/skills/` |
| `VSCodeSkillsProvider` | `~/.copilot/skills/` |
| `GeminiSkillsProvider` | `~/.gemini/skills/` |
| `CodexSkillsProvider` | `/etc/codex/skills/` + `~/.codex/skills/` (system wins) |
| `GooseSkillsProvider` | `~/.config/agents/skills/` |
| `OpenCodeSkillsProvider` | `~/.config/opencode/skills/` |

```python
from fastmcp.server.providers.skills import ClaudeSkillsProvider
mcp.add_provider(ClaudeSkillsProvider())  # uses ~/.claude/skills/
```

## The `skill://` URI scheme and manifest

Each skill exposes three kinds of resource:

- **Main file:** `skill://<name>/SKILL.md` — the primary content clients read to understand the skill.
- **Manifest:** `skill://<name>/_manifest` — a synthetic JSON listing every file with size and SHA256 hash; used to discover supporting files and verify integrity.
- **Supporting files:** `skill://<name>/<path>` — any other file (`references/x.md`, `assets/logo.png`, …).

Manifest shape:

```json
{
  "skill": "authoring-skills",
  "files": [
    {"path": "SKILL.md", "size": 1234, "hash": "sha256:abc..."},
    {"path": "references/structure.md", "size": 5678, "hash": "sha256:def..."}
  ]
}
```

If a skill's main file has **no frontmatter description**, the provider derives one from the first meaningful line — another reason to always write a real `description`.

## Supporting-files modes and reload

- `supporting_files="template"` (default) — only the main file and `_manifest` appear in `list_resources()`; clients read the manifest, then fetch specific files. Keeps the resource list compact.
- `supporting_files="resources"` — every file appears as its own resource. Use when clients need full enumeration without extra round-trips.
- `reload=True` — re-scans on every request so edits show up live. **Dev only**; it adds per-request overhead.

```python
SkillsDirectoryProvider(roots=..., supporting_files="resources", reload=True)
```

## Consuming skills

Standalone helpers in `fastmcp.utilities.skills` let any client discover and pull skills from a server that exposes them:

```python
from pathlib import Path
from fastmcp import Client
from fastmcp.utilities.skills import list_skills, download_skill, sync_skills, get_skill_manifest

async with Client("http://skills-server/mcp") as client:
    for s in await list_skills(client):
        print(s.name, s.description)

    manifest = await get_skill_manifest(client, "authoring-skills")   # inspect before downloading
    await download_skill(client, "authoring-skills", Path.home() / ".claude" / "skills")
    await sync_skills(client, Path.home() / ".claude" / "skills")     # pull everything
```

`download_skill`/`sync_skills` take `overwrite` (default `False` = skip existing).

## Portability rules — write once, run local + MCP

To keep a single source working in both worlds:

1. **Hit the open standard.** Required `name`+`description`; optional `license`/`tags`/`metadata`. The `name` must equal the directory name.
2. **Put the description in real frontmatter** — don't rely on the first-line fallback.
3. **Keep host-specific frontmatter additive.** `allowed-tools`, `disable-model-invocation`, `context: fork`, etc. are fine to include — MCP consumers ignore them — but the skill must still make sense without them.
4. **Don't assume a host's tools in the body.** If you must call MCP tools, use fully-qualified names (`ServerName:tool_name`) and state the dependency, so a different consumer can tell what's required.
5. **Keep paths relative and forward-slashed**, references one level deep — these are exactly the structural rules that also make manifests and downloads clean.
6. **Avoid host-only path variables in portable skills.** `${CLAUDE_PLUGIN_ROOT}` etc. are Claude Code plugin features; if a skill is meant to travel, prefer relative paths resolved from the skill directory.
