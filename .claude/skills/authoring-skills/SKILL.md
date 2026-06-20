---
name: authoring-skills
description: >-
  Create, structure, review, maintain, and distribute Agent Skills (SKILL.md
  directories) that work both as local Claude Code / plugin skills and as
  skills served over MCP via FastMCP's Skills Provider. Use whenever the user
  wants to write a new skill, improve or refactor an existing skill, fix a
  skill that isn't triggering, design a skill's frontmatter or file layout,
  make a skill portable across Claude / Cursor / MCP clients, expose skills
  over MCP, or audit/maintain a skill library. Trigger even when the user says
  only "SKILL.md", "make a skill", "my skill won't fire", "turn this workflow
  into a skill", "skill description", or describes packaging procedural
  knowledge for an agent without naming skills explicitly. Prefer this skill
  over improvising, because the rules that decide whether a skill triggers and
  loads correctly are specific and easy to get subtly wrong.
license: MIT
metadata:
  version: 1.0.0
  author: benrben
---

# Authoring Skills

Build skills that an agent actually discovers and uses well — and that stay portable between a local `.claude/skills/` install and an MCP server. This skill encodes the two things authors get wrong most: **(1) writing the `description` so the skill triggers at the right time** and **(2) structuring the files so the right context loads at the right moment** — plus how to maintain and distribute skills over time.

The one idea under everything: **the agent never reads your whole skill up front.** At startup it sees only each skill's `name` + `description`. Everything else loads progressively. Design for that reader.

## The mental model: three levels of progressive disclosure

1. **Metadata** (`name` + `description`) — pre-loaded for *every* installed skill, always in context. This alone decides whether your skill triggers. Budget: a sentence or three.
2. **SKILL.md body** — loaded only once the skill triggers. Keep it **under ~500 lines**. This teaches the workflow.
3. **Bundled files** (`references/`, `scripts/`, `assets/`) — loaded or executed on demand, **one level deep** from SKILL.md. Effectively unbounded; scripts can run without ever entering context.

So: the description sells the skill, the body teaches it, bundled files hold the bulk. Put each fact at the cheapest level that still works.

## Decide first: is a skill even the right tool?

A skill is for **reusable procedural knowledge** — a workflow, a house style, domain rules, a fragile multi-step process the agent should repeat consistently. It is **not** the place for one-off task instructions, for things the model already knows (don't explain what a PDF is), or for a single tool call. If the knowledge won't be reused, skip the skill. Default assumption: **the model is already smart — only add what it lacks.**

## Workflow: building a skill from scratch

1. **Capture intent.** Nail three things before writing: *what* the skill should let the agent do, *when* it should trigger (the actual phrases/contexts/file types a user would use), and *what output* it should produce. If the current conversation already contains the workflow ("turn this into a skill"), mine it for the steps, tools, and corrections first.
2. **Find the gap (eval-first).** Run the task once *without* a skill and note where the agent struggles or where you keep supplying context. Those gaps — not your guesses — are what the skill must close. Write 2–3 realistic test prompts now; you'll judge the skill against them.
3. **Choose the name.** Gerund form preferred (`processing-invoices`). Lowercase/digits/hyphens, ≤64 chars, and **never contains "claude" or "anthropic"**. The directory name must match. See `references/frontmatter.md`.
4. **Write the description** — the highest-leverage step. Third person, what + when, key terms, and a little "pushy" to beat under-triggering. See `references/frontmatter.md` for the formula and worked examples.
5. **Draft the body** at the right *degree of freedom*: prose for open-ended judgment, parameterized scripts for a preferred pattern, exact "run this" steps for fragile operations. Keep it lean. See `references/structure.md`.
6. **Move bulk into bundled files** as the body grows past a screen or two: long reference material into `references/*.md` (one level deep, ToC if >~100 lines), deterministic/repeated logic into `scripts/`, output templates into `assets/`. See `references/structure.md`.
7. **Add feedback loops** for anything fragile or high-stakes: validate → fix → repeat, or plan → validate → execute. Prefer a script as the validator where the check is objective.
8. **Validate** the skill mechanically: `python scripts/validate_skill.py <path-to-skill>` (catches frontmatter, line-count, nested-reference, dead-link, and Windows-path problems). Fix everything it flags.
9. **Test against the prompts** from step 2. For rigorous iteration (baseline vs with-skill runs, grading, a review viewer, and automated description optimization), hand off to the bundled **`skill-creator`** skill — don't reinvent that loop here.
10. **Review** against `references/checklist.md` before calling it done.

If the user already has a draft, skip to the relevant step — usually 4 (description), 6 (restructure), or 8–10 (validate/test/review).

## The five rules that matter most (enforce these)

1. **Triggering lives in the description, in third person, and slightly pushy.** "Trigger conditions" is not a frontmatter field — bake the *when* into `description`. There is a real, measured tendency to *under*-trigger; explicit trigger phrasing fixes it. (`references/frontmatter.md`)
2. **Keep references one level deep.** `SKILL.md → reference.md` is fine; `SKILL.md → a.md → b.md` is not — the agent partial-reads nested files and gets incomplete info. Every bundled file links directly from SKILL.md.
3. **Match degrees of freedom to fragility.** Don't hand-cuff open-ended tasks with rigid MUSTs, and don't leave fragile operations under-specified. Explain *why* a step matters instead of shouting ALWAYS/NEVER.
4. **Be concise; the context window is shared.** Cut anything the model already knows. One default with an escape hatch beats a menu of five options.
5. **No time-bombs, consistent terms, forward slashes.** Avoid dated conditionals (use a collapsed "Old patterns" section), pick one term per concept, and never use Windows-style paths.

## Dual target: local skill *and* MCP-served skill

A skill written to the core standard is **automatically portable**. The same `SKILL.md` directory can be:

- **A local Claude Code / plugin skill** — dropped in `.claude/skills/<name>/`, optionally with host-specific frontmatter (`allowed-tools`, `disable-model-invocation`, …).
- **A skill served over MCP** — exposed by FastMCP's Skills Provider as `skill://<name>/SKILL.md` resources that any MCP client can discover and download.

To keep both paths working: stay close to the **open standard** (required `name`+`description`; optional `license`/`version`/`author`/`tags`/`metadata`), keep any host-specific frontmatter **additive** (harmless when ignored), put the description in real frontmatter (the MCP provider falls back to the first line otherwise), and never assume a specific host's tools exist in the body. Full details, provider setup, and `skill://` URI scheme in `references/mcp-distribution.md`.

## Maintaining a skill library

Skills rot: APIs change, descriptions drift, references go stale. For updating safely (preserve `name`/dir identity, edit a writeable copy of read-only installs), versioning, deprecation, avoiding time-bombs, re-running evals, and auditing an existing library, see `references/maintenance.md`. This repo already ships an **`audit-extension`** skill that audits SKILL.md / plugin.json / marketplace.json / .mcp.json against current best practices — invoke it for a structural review rather than duplicating its checks here.

## Security: principle of least surprise

A skill's behavior must match what its description promises. Never author skills that contain malware, exfiltrate data, or deceive the user, and audit untrusted skills (read every bundled file and watch for instructions to fetch untrusted external sources) before installing them. Creative "roleplay as X" skills are fine; covert capability is not.

## Reference files

- `references/frontmatter.md` — Every frontmatter field (core, Claude Code, open standard), the description formula with good/bad examples, naming rules, and the unreachable-skill footgun. Read before writing or fixing a description.
- `references/structure.md` — Progressive disclosure in practice: degrees of freedom, file organization, ToC rule, workflows/checklists, feedback loops, and script authoring (solve-don't-punt, no voodoo constants, execute-vs-read). Read before drafting a non-trivial body or adding scripts.
- `references/mcp-distribution.md` — Serving and consuming skills over MCP with FastMCP's Skills Provider: `skill://` URIs, manifests, vendor providers, supporting-files modes, client utilities, and the portability rules. Read when a skill must work over MCP or across tools.
- `references/maintenance.md` — Updating, versioning, deprecation, eval re-runs, auditing, and dependency-drift handling for an existing skill or library. Read when changing or reviewing skills that already exist.
- `references/checklist.md` — The pre-ship review checklist plus a short worked example (from gap to finished skill). Read at the end, before declaring a skill done.
- `scripts/validate_skill.py` — Mechanical validator (frontmatter rules, body length, one-level references, dead links, Windows paths). Run it on every skill; fix what it reports.
