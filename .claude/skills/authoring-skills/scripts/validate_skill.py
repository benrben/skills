#!/usr/bin/env python3
"""Mechanically validate an Agent Skill directory against the authoring rules.

Usage:
    python validate_skill.py <path-to-skill-dir> [<path-to-skill-dir> ...]

Checks (grounded in Anthropic's skill-authoring best practices + the
agentskills.io open standard):
  - SKILL.md exists and has YAML frontmatter
  - name: present, <=64 chars, lowercase/digits/hyphens, no reserved words,
          matches the directory name
  - description: present, non-empty, <=1024 chars, third-person-ish, no XML tags
  - unreachable-skill footgun (disable-model-invocation + user-invocable:false)
  - allowed-tools is space-separated (not comma-separated)
  - body length under ~500 lines (warn) / 600 (error-ish warn)
  - references are one level deep and the linked files exist (no dead links)
  - reference files > ~100 lines have a table of contents
  - no Windows-style backslash paths in markdown links

Exit code 0 if no ERRORs (warnings allowed), 1 otherwise. No third-party deps:
frontmatter is parsed with a minimal hand-rolled reader so this runs anywhere.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RESERVED_WORDS = ("anthropic", "claude")
NAME_RE = re.compile(r"^[a-z0-9-]+$")
MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
XML_TAG_RE = re.compile(r"<[a-zA-Z/][^>]*>")
BODY_WARN_LINES = 500
BODY_HARD_LINES = 600
TOC_HINT_LINES = 100


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def parse_frontmatter(text: str):
    """Return (frontmatter_dict, body_str) or (None, text) if no frontmatter.

    Minimal YAML: handles `key: value`, simple block scalars (`>-`, `|`),
    and nested one-level maps enough to find name/description/flags. Values are
    returned as strings; nested keys are flattened as 'parent.child'.
    """
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    raw = text[3:end].strip("\n")
    body = text[end + 4:]
    data: dict[str, str] = {}
    lines = raw.split("\n")
    i = 0
    cur_parent = None
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        indent = len(line) - len(line.lstrip())
        m = re.match(r"^(\s*)([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, val = m.group(2), m.group(3).strip()
        if indent == 0:
            cur_parent = None
        if val in (">", ">-", "|", "|-", ">+", "|+"):
            # block scalar: gather more-indented following lines
            collected = []
            j = i + 1
            base_indent = None
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    collected.append("")
                    j += 1
                    continue
                ni = len(nxt) - len(nxt.lstrip())
                if ni <= indent:
                    break
                if base_indent is None:
                    base_indent = ni
                collected.append(nxt[base_indent:])
                j += 1
            joined = " ".join(s.strip() for s in collected if s.strip())
            data[key] = joined
            i = j
            continue
        if val == "" and indent == 0:
            # possible nested map parent
            cur_parent = key
            i += 1
            continue
        full_key = f"{cur_parent}.{key}" if (indent > 0 and cur_parent) else key
        data[full_key] = val.strip().strip("'\"")
        i += 1
    return data, body


def check_skill(skill_dir: Path) -> Report:
    r = Report()
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        r.err(f"No SKILL.md found in {skill_dir}")
        return r

    text = skill_md.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    if fm is None:
        r.err("SKILL.md has no YAML frontmatter (must start with '---').")
        return r

    # name
    name = fm.get("name", "")
    if not name:
        r.err("frontmatter: 'name' is required.")
    else:
        if len(name) > 64:
            r.err(f"name '{name}' exceeds 64 chars ({len(name)}).")
        if not NAME_RE.match(name):
            r.err(f"name '{name}' must be lowercase letters, digits, hyphens only.")
        for w in RESERVED_WORDS:
            if w in name.lower():
                r.err(f"name '{name}' contains reserved word '{w}'.")
        if name != skill_dir.name:
            r.err(f"name '{name}' must match directory name '{skill_dir.name}'.")

    # description
    desc = fm.get("description", "")
    if not desc:
        r.err("frontmatter: 'description' is required and non-empty.")
    else:
        if len(desc) > 1024:
            r.err(f"description exceeds 1024 chars ({len(desc)}).")
        if XML_TAG_RE.search(desc):
            r.warn("description appears to contain XML/HTML tags (not allowed).")
        if re.search(r"\b(I can|I will|you can|you will|we can)\b", desc, re.I):
            r.warn("description seems first/second person; write in third person.")
        if not re.search(r"\b(use when|use this|trigger|when the user|whenever)\b", desc, re.I):
            r.warn("description has no explicit 'when to use' trigger language "
                   "(skills tend to under-trigger; add concrete triggers).")

    # unreachable footgun
    dmi = str(fm.get("disable-model-invocation", "")).lower() == "true"
    ui_false = str(fm.get("user-invocable", "")).lower() == "false"
    if dmi and ui_false:
        r.err("Unreachable skill: both 'disable-model-invocation: true' and "
              "'user-invocable: false' — neither model nor user can invoke it.")

    # allowed-tools comma check
    at = fm.get("allowed-tools", "")
    if at and "," in at:
        r.err("allowed-tools must be SPACE-separated, not comma-separated "
              "(commas fail silently).")

    # body length
    body_lines = body.count("\n") + 1
    if body_lines > BODY_HARD_LINES:
        r.warn(f"SKILL.md body is {body_lines} lines (>{BODY_HARD_LINES}); "
               "move detail into references/.")
    elif body_lines > BODY_WARN_LINES:
        r.warn(f"SKILL.md body is {body_lines} lines (>{BODY_WARN_LINES} ideal).")

    # reference links: one level deep + dead links + windows paths
    ref_targets: list[str] = []
    for target in MD_LINK_RE.findall(body):
        if "\\" in target:
            r.err(f"link uses Windows-style backslash path: '{target}'.")
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        clean = target.split("#")[0].strip()
        if not clean:
            continue
        ref_targets.append(clean)
        dest = (skill_dir / clean).resolve()
        if not dest.exists():
            r.err(f"dead link in SKILL.md: '{target}' -> file not found.")

    # check referenced markdown files: ToC for long ones + nested-ref depth
    for clean in ref_targets:
        dest = skill_dir / clean
        if dest.suffix.lower() != ".md" or not dest.is_file():
            continue
        rtext = dest.read_text(encoding="utf-8")
        rlines = rtext.count("\n") + 1
        if rlines > TOC_HINT_LINES and not re.search(r"^##?\s*Contents", rtext, re.M | re.I):
            r.warn(f"{clean} is {rlines} lines (>{TOC_HINT_LINES}) but has no "
                   "'## Contents' table of contents.")
        # one-level-deep: does this reference file link to other local md files?
        for sub in MD_LINK_RE.findall(rtext):
            if sub.startswith(("http", "#", "mailto:")):
                continue
            subclean = sub.split("#")[0].strip()
            if subclean.endswith(".md") and "/" in subclean or subclean.endswith(".md"):
                # only flag if it points to another bundled doc (heuristic)
                cand = (dest.parent / subclean)
                if cand.suffix.lower() == ".md" and cand.name != dest.name:
                    r.warn(f"nested reference: {clean} links to '{sub}' — keep "
                           "references one level deep from SKILL.md.")
                    break
    return r


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    overall_ok = True
    for arg in argv[1:]:
        skill_dir = Path(arg).expanduser().resolve()
        print(f"\n=== {skill_dir.name} ({skill_dir}) ===")
        rep = check_skill(skill_dir)
        for e in rep.errors:
            print(f"  ERROR:   {e}")
        for w in rep.warnings:
            print(f"  warning: {w}")
        if not rep.errors and not rep.warnings:
            print("  OK — no issues found.")
        elif not rep.errors:
            print(f"  PASS with {len(rep.warnings)} warning(s).")
        else:
            print(f"  FAIL — {len(rep.errors)} error(s), {len(rep.warnings)} warning(s).")
            overall_ok = False
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
