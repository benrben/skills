# Frontmatter & Description Reference

The frontmatter is what makes (or breaks) discovery. This file covers every field, the description formula, naming rules, and the footguns. Read before writing or fixing a skill's frontmatter.

## Contents
- The two required fields
- The description formula (with examples)
- Naming rules
- Open-standard optional fields (portability)
- Claude Code / plugin optional fields
- Footguns (including the unreachable-skill trap)

## The two required fields

Every skill needs exactly these, in YAML frontmatter at the very top of `SKILL.md`:

```yaml
---
name: processing-invoices
description: Extracts totals and line items from PDF/CSV invoices and reconciles them against a ledger. Use when the user uploads invoices, mentions accounts payable, or asks to reconcile bills, even if they don't say "invoice".
---
```

- **`name`** — max 64 chars; lowercase letters, numbers, hyphens only; no XML tags; **must not contain "anthropic" or "claude"**; must match the directory name.
- **`description`** — non-empty; max 1024 chars; no XML tags; written in **third person**; states **what it does AND when to use it**.

## The description formula

The description is injected into the system prompt for every installed skill and is the *only* thing the agent uses to decide whether to trigger yours (it may be choosing among 100+). Optimize it deliberately.

**Formula:** `<what it does, third person> + <when to use it: concrete triggers, phrases, file types, contexts> + <a pushy nudge against under-triggering>`.

Rules:

1. **Third person, always.** It's system-prompt text. First/second person hurts discovery.
   - Good: "Generates commit messages by analyzing git diffs."
   - Avoid: "I can help you write commit messages." / "You can use this to…"
2. **What + when.** Don't stop at what it does — name the situations that should fire it. There is no `when_to_use` field; the *when* goes here.
3. **Include key terms** a real user would type (formats, tool names, synonyms).
4. **Be a little pushy.** Agents measurably *under*-trigger skills. Add explicit trigger language so yours fires when relevant.
   - Weak: "How to build a fast dashboard for internal data."
   - Strong: "How to build a fast dashboard for internal data. Use this whenever the user mentions dashboards, data viz, internal metrics, or wants to display company data — even if they don't say 'dashboard'."
5. **Don't over-claim.** Pushy about *when it applies*, not dishonest about *what it does* — false positives waste context and erode trust.

**Good examples (from Anthropic's docs):**

```
description: Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction.
```
```
description: Analyze Excel spreadsheets, create pivot tables, generate charts. Use when analyzing Excel files, spreadsheets, tabular data, or .xlsx files.
```

**Bad (vague — will not trigger reliably):** `Helps with documents` · `Processes data` · `Does stuff with files`.

Note on length: some UIs show a ~1,536-char *listing* cap, but the authoring limit is 1024 chars and the real goal is clarity, not length. A focused 2–4 sentences usually beats a maxed-out paragraph.

## Naming rules

- **Gerund form preferred:** `processing-pdfs`, `analyzing-spreadsheets`, `writing-documentation`.
- Acceptable alternatives: noun phrases (`pdf-processing`) or action forms (`process-pdfs`). Pick one style across your library.
- **Avoid:** vague (`helper`, `utils`, `tools`), overly generic (`documents`, `data`, `files`), reserved words (`claude-*`, `anthropic-*`), and inconsistent patterns within a collection.
- The directory name **must equal** the `name` field (open-standard requirement; also how MCP derives the skill identifier).

## Open-standard optional fields (use these for portability)

The agentskills.io standard keeps `name`+`description` required and adds optional fields that travel across Claude, Cursor, Gemini, Codex, etc.:

```yaml
license: MIT                 # license name or reference to a bundled license file
metadata:                    # catch-all map; recommended home for version/extra info
  version: 1.2.0             # semver
  author: your-name
tags: [pdf, finance]         # categorization
agents: [claude, cursor]     # explicitly compatible agents (optional)
```

Prefer putting `version`/`author` under `metadata` (the standard's recommended catch-all) unless a target host reads a top-level `version`/`author` — staying minimal maximizes portability. These optional fields are ignored harmlessly by hosts that don't use them.

## Claude Code / plugin optional fields

Recognized by Claude Code; **additive** — keep them so the skill still works when consumed elsewhere:

- `disable-model-invocation: true` — skill runs only when explicitly invoked (good for side-effecting skills).
- `user-invocable: false` — pure background knowledge the model pulls in; user can't invoke it directly.
- `allowed-tools` — **space-separated**, not comma-separated (commas fail silently). Scope Bash tightly: `allowed-tools: Read Grep Glob Bash(git:*)`.
- `argument-hint: [path]` — slash-command-style hint (confirm support before relying on it for a pure skill).
- `model:` — pin a model; verify it names a currently available model.
- `context: fork` — runs in a forked context; **must** pair with an `agent` and a body that states an explicit task (not just reference material).

Plugin path variables (in bodies/scripts, not frontmatter): `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PLUGIN_DATA}`. Multi-skill plugins use `skills/<name>/SKILL.md`; only `plugin.json` belongs in `.claude-plugin/`.

## Footguns

- **The unreachable skill (BLOCKING):** setting **both** `disable-model-invocation: true` *and* `user-invocable: false` means neither the model nor the user can ever invoke it. Pick one.
- **Comma-separated `allowed-tools`** silently disables tools — use spaces.
- **Reserved words in `name`** ("claude"/"anthropic") are rejected.
- **`name` ≠ directory name** breaks the open standard and MCP identification.
- **XML tags** in `name`/`description` are invalid.
- **Description in the body instead of frontmatter** — the MCP Skills Provider falls back to the *first meaningful line* when frontmatter has no description, so an absent description yields a poor auto-derived one.
