# Body Structure, Files & Scripts

How to write the body and organize bundled files so the right context loads at the right time. Read before drafting a non-trivial body or adding scripts.

## Contents
- Degrees of freedom (match specificity to fragility)
- Conciseness
- File organization & progressive disclosure
- The one-level-deep rule and ToC rule
- Workflows & checklists
- Feedback loops
- Authoring scripts
- Anti-patterns

## Degrees of freedom

Match how prescriptive you are to how fragile the task is. The analogy: the agent is a robot on a path.

- **High freedom — prose instructions.** *Open field, no hazards.* Many valid approaches; context decides. Example: a code-review process described as goals ("check for edge cases, suggest readability improvements, verify project conventions").
- **Medium freedom — pseudocode / parameterized scripts.** A preferred pattern exists, some variation is fine. Example: a `generate_report(data, format="markdown", include_charts=True)` template to customize.
- **Low freedom — exact scripts, few/no params.** *Narrow bridge with cliffs.* Fragile, consistency-critical, must-follow-sequence. Example: "Run exactly `python scripts/migrate.py --verify --backup`. Do not modify the command."

Reach for low freedom only when the task is genuinely fragile. Over-constraining open-ended work with rigid `ALWAYS`/`NEVER` makes skills brittle and is a yellow flag — prefer explaining *why* a step matters so a smart model can generalize.

## Conciseness

The context window is shared with the system prompt, history, every other skill's metadata, and the user's request. Once your body loads, every token competes. Challenge each line: does the model already know this? Cut explanations of common concepts; keep only what's specific to your task, domain, or house style.

## File organization & progressive disclosure

Standard layout:

```
skill-name/
├── SKILL.md            # overview + workflow; loaded on trigger
├── references/         # docs read into context as needed
│   ├── domain-a.md
│   └── domain-b.md
├── scripts/            # executable code; run, not read (usually)
└── assets/             # templates/icons/fonts used in output
```

- Keep `SKILL.md` **under ~500 lines.** When it grows past that, move detail into `references/` and link with a one-line "read this when…" pointer.
- **Organize by domain/variant** so irrelevant context never loads: `references/aws.md`, `references/gcp.md`, `references/azure.md` — the agent reads only the one it needs.
- **Descriptive filenames** that signal content (`form_validation_rules.md`, not `doc2.md`). Forward slashes only.
- **Bundle freely** — large reference docs, examples, datasets cost zero context until read. Scripts cost zero context when executed.

## The one-level-deep rule

Reference files must link **directly from SKILL.md**, never from each other:

- Good: `SKILL.md → references/forms.md`, `SKILL.md → references/api.md`.
- Bad: `SKILL.md → advanced.md → details.md`. The agent partial-reads nested files (e.g. `head -100`) and proceeds on incomplete information.

If two reference files are related, link both from SKILL.md rather than chaining them.

## The table-of-contents rule

Any reference file longer than ~100 lines gets a short ToC at the top, so a partial read still reveals the file's full scope. (This file has one.)

## Workflows & checklists

For multi-step tasks, give clear sequential steps. For *complex* ones, provide a checklist the agent can copy into its response and tick off — it prevents skipped steps:

```
Task Progress:
- [ ] Step 1: Analyze input (run analyze.py)
- [ ] Step 2: Create mapping (edit fields.json)
- [ ] Step 3: Validate mapping (run validate.py)
- [ ] Step 4: Execute (run apply.py)
- [ ] Step 5: Verify output
```

If a workflow gets large, push it into its own reference file and tell the agent to read it based on the task at hand.

## Feedback loops

Build self-correction into fragile or quality-critical work:

- **Validate → fix → repeat:** "Run the validator. If it fails, read the error, fix, re-run. Only proceed when it passes." The validator can be a script *or* a reference doc (e.g. a style guide the agent checks against).
- **Plan → validate → execute** for batch/destructive/high-stakes operations: have the agent emit a structured plan file, validate it with a script (with verbose, specific errors), then execute. Catches mistakes before they touch originals.

## Authoring scripts

Scripts are the deterministic, token-free layer. When you include them:

- **Solve, don't punt.** Handle errors *in the script* instead of failing into the agent's lap. A missing file should be created or substituted with a clear message, not raised as a bare traceback.
- **No voodoo constants.** Justify every magic number in a comment (Ousterhout's law): `REQUEST_TIMEOUT = 30  # HTTP usually completes < 30s; allows slow links`. "If you don't know the right value, how will the model?"
- **Prefer pre-made scripts over generated code** for anything repeated: more reliable, fewer tokens, consistent results. If three test runs all independently write the same helper, bundle it once.
- **Say whether to execute or read.** Default is execute ("Run `analyze.py` to extract fields") — context-free and reliable. Use "read as reference" only when the logic itself is the lesson.
- **Don't assume installs.** List dependencies; remember claude.ai can install from npm/PyPI while the raw API has no network/package install.
- Document each script's purpose, usage, and output shape in SKILL.md or the relevant reference file.

## Anti-patterns (avoid)

- **Time-sensitive info** ("after August 2025, use the new API"). Instead: a "Current method" section plus a collapsed `<details>` "Old patterns (deprecated)" block.
- **Too many options.** One default with an escape hatch beats "use pypdf or pdfplumber or PyMuPDF or…". Example: "Use pdfplumber for text; for scanned PDFs needing OCR, use pdf2image + pytesseract."
- **Inconsistent terminology.** Pick one term per concept (always "field," always "extract") — mixing synonyms confuses the model.
- **Deeply nested references** and **Windows-style paths** — covered above; both cause real failures.
