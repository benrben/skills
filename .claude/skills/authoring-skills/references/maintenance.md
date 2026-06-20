# Maintaining Skills Over Time

Skills rot: APIs move, descriptions drift, references go stale, libraries grow inconsistent. Read this when changing or reviewing skills that already exist.

## Contents
- Updating a skill safely
- Versioning
- Deprecation & avoiding time-bombs
- Dependency drift
- Re-testing after changes
- Auditing a library
- Refactoring signals

## Updating a skill safely

- **Preserve identity.** Keep the directory name and the `name` frontmatter field unchanged. Don't ship `foo-v2` — it breaks references, the open-standard name==dir rule, and MCP identification. Track the change in `metadata.version` instead.
- **Edit a writeable copy of read-only installs.** Installed skill paths are often read-only. Copy to a writeable location (e.g. `/tmp/<name>/`), edit there, validate, then place the result back.
- **Make minimal, reasoned edits.** Read the existing body first and work from what's there. When something isn't working, prefer reframing and explaining *why* over piling on rigid MUSTs.
- **Re-validate** after every change: `python scripts/validate_skill.py <path>`.

## Versioning

- Use semantic versioning in `metadata.version` (`MAJOR.MINOR.PATCH`).
- Bump **PATCH** for wording/clarity fixes, **MINOR** for new capabilities or reference files, **MAJOR** for changed behavior, removed capabilities, or renamed/removed bundled files that consumers may depend on.
- The manifest's SHA256 hashes (when served over MCP) let consumers detect content changes regardless of the version string — but still bump the version so humans can reason about it.

## Deprecation & avoiding time-bombs

- **Never write dated conditionals** ("before August 2025 do X; after, do Y") — they silently become wrong. Instead keep a **Current method** section and a collapsed **Old patterns** block:

  ```markdown
  ## Current method
  Use the v2 endpoint: `api.example.com/v2/messages`

  <details><summary>Legacy v1 (deprecated)</summary>
  v1 used `api.example.com/v1/messages` — no longer supported.
  </details>
  ```

- When removing a capability, leave a one-line pointer to its replacement rather than deleting silently.

## Dependency drift

For skills that wrap a fast-moving library or API, **don't freeze specifics you can't keep current.** Instead:

- State the canonical source ("verify against <docs URL> for the installed version") and have the skill confirm a key API before relying on it.
- Add a short detection/compat note ("if you see the old `get_x()` form, you're on vN — here's the new equivalent").
- Prefer behavior-level guidance over copy-pasted signatures where the API churns.

## Re-testing after changes

- Re-run the skill against its existing test prompts; a fix for one case shouldn't regress others.
- Read the *transcripts*, not just final outputs — if the skill is making the model waste steps, cut the parts causing it.
- For rigorous before/after measurement (baseline vs new version, grading, benchmark, and automated description optimization), hand off to the bundled **`skill-creator`** skill, which owns that loop.
- After meaningful edits, **re-optimize the description** for triggering — it's the field most likely to need tuning as scope shifts.

## Auditing a library

- This repo ships an **`audit-extension`** skill that checks SKILL.md / plugin.json / marketplace.json / .mcp.json against current best practices and emits a prioritized, copy-pasteable fix list. Use it for structural review instead of re-deriving the rules here.
- For a quick pass across many skills, run `scripts/validate_skill.py` on each and triage the mechanical failures first (frontmatter, line count, nested refs, dead links, Windows paths).
- Watch for **library-level inconsistency:** mixed naming styles, overlapping descriptions that cause two skills to compete, and duplicated reference content that should be shared.

## Refactoring signals

Restructure when you see:

- **Body creeping past ~500 lines** → move detail into `references/` with one-level pointers.
- **The same helper script reinvented** across runs → bundle it once in `scripts/`.
- **A reference file only ever partially read** → it may be too long (add a ToC) or buried under a nested link (raise it to one level deep).
- **A bundled file never accessed** → it's unnecessary or poorly signposted in SKILL.md.
- **Under-triggering** in real use → the description needs more concrete triggers, not the body.
- **Over-triggering / false positives** → the description over-claims; narrow the "when".
