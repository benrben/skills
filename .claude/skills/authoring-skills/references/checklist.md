# Pre-Ship Checklist & Worked Example

Run the checklist before declaring a skill done. The worked example shows the whole arc from gap to finished skill. Read at the end of authoring.

## Contents
- Pre-ship checklist
- Worked example

## Pre-ship checklist

### Discovery (the description)
- [ ] `description` is third person, states **what + when**, includes key terms.
- [ ] Slightly "pushy" with concrete triggers (beats under-triggering) without over-claiming.
- [ ] No `when_to_use` field invented; triggers live in `description`.

### Frontmatter validity
- [ ] `name`: ≤64 chars, lowercase/digits/hyphens, no "claude"/"anthropic", **matches directory name**.
- [ ] `description`: non-empty, ≤1024 chars, no XML tags.
- [ ] Optional fields (`license`, `metadata.version`, `tags`) used where helpful; host-specific fields are additive.
- [ ] Not unreachable: NOT both `disable-model-invocation: true` AND `user-invocable: false`.
- [ ] `allowed-tools` (if present) is **space-separated**; Bash scoped.

### Structure
- [ ] SKILL.md body under ~500 lines.
- [ ] References are **one level deep** from SKILL.md and actually linked.
- [ ] Reference files >~100 lines have a table of contents.
- [ ] Degrees of freedom match task fragility (prose vs script vs exact command).
- [ ] Forward slashes only; descriptive filenames; organized by domain where relevant.
- [ ] Concise — nothing the model already knows; one default, not a menu.
- [ ] No time-sensitive conditionals (use "Old patterns" instead); consistent terminology.

### Scripts (if any)
- [ ] Solve rather than punt; explicit error handling.
- [ ] No voodoo constants (every magic number justified).
- [ ] Clear whether to execute or read; dependencies listed.

### Portability (if dual-target)
- [ ] Hits the open standard; description in real frontmatter (not just first line).
- [ ] Body doesn't assume a specific host's tools; MCP tools fully-qualified if used.

### Verification
- [ ] `python scripts/validate_skill.py <path>` passes.
- [ ] Tested against 2–3 realistic prompts (hand off to `skill-creator` for rigorous eval/grading).
- [ ] Behavior matches the description (principle of least surprise).

## Worked example

**Gap (step 1–2):** A user keeps asking the agent to turn raw meeting transcripts into structured action-item lists, and keeps re-explaining the format, the "ignore chit-chat" rule, and that owners must be named. Running it once without a skill confirms the agent omits owners and includes filler. That's the gap.

**Name + description (step 3–4):**

```yaml
---
name: extracting-action-items
description: Turns meeting transcripts or notes into a structured action-item list with owner, due date, and priority, dropping chit-chat. Use whenever the user shares meeting notes, a transcript, or standup/sync text and wants action items, follow-ups, todos, or "who owns what" — even if they don't say "action items".
license: MIT
metadata:
  version: 1.0.0
---
```

Third person, what+when, pushy triggers ("follow-ups", "todos", "who owns what"), key terms.

**Body (step 5) — high freedom with a strict output template** (extraction is judgment; the *format* is fixed):

```markdown
# Extracting Action Items

Read the transcript, ignore social/chit-chat, and extract every commitment.

## Rules
- Every item MUST name an owner. If the transcript doesn't say who, mark `owner: UNASSIGNED` — never guess.
- Capture due dates only if stated; otherwise `due: —`.
- Priority is High/Med/Low based on stated urgency; default Med.

## Output (always this table)
| # | Action | Owner | Due | Priority |
|---|--------|-------|-----|----------|
```

The "MUST name an owner" rule is justified inline (it's the exact gap observed), not a blanket shout.

**Bundle (step 6):** none needed yet — it's a single-screen skill. If later it grows variants (Jira export, email digest), each becomes `references/<variant>.md`, one level deep.

**Validate + test (step 8–9):** run `validate_skill.py`; run the 2–3 saved prompts; confirm owners always appear and chit-chat is dropped.

**Review (step 10):** walk the checklist above. Ship.
