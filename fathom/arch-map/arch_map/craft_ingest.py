"""craft-ingest — measure line-level craft facts from source and map them onto modules.

Mirrors coverage_ingest: a pure parser core (`scan_text`) plus an I/O aggregator
(`module_craft`). Heuristic and language-agnostic — a brace scanner for C-like
languages, an indent scanner for Python; anything it can't read degrades to zeros
rather than lying. Never mutates the model.

Interface (the test surface):
  scan_text(text, path) -> dict   per-file facts: maxFnLen, maxArgs, maxNesting,
                                  methodCount, magicNumbers, commentedOutBlocks
  module_craft(model, root) -> {module_id: dict}   facts aggregated per module via
                                  the model's file ownership. Unreadable files are
                                  skipped; modules with no readable files are omitted.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

_PY_EXT = {".py", ".pyi"}
_CTRL = {"if", "for", "while", "switch", "catch", "return", "sizeof", "synchronized",
         "with", "do", "else", "elif", "when", "using", "match", "lock"}
_DECL2 = re.compile(r'([A-Za-z_]\w*)\s*\(([^;{}]*)\)')
_DEF_PY = re.compile(r'^(\s*)(?:async\s+)?def\s+\w+\s*\(([^)]*)\)')
_NUM = re.compile(r'(?<![\w.])\d+(?:\.\d+)?(?![\w.])')
_KEEP_NUM = {"0", "1", "2", "3", "4", "8", "10", "12", "16", "24", "30", "32", "60",
             "64", "100", "127", "128", "200", "201", "204", "256", "301", "302",
             "400", "401", "403", "404", "500", "512", "1000", "1024", "3600", "8080"}
_CONSTLINE = re.compile(r'\b(const|final|enum|val)\b|#define|static\s+final')
_STR = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`')


def _denoise(text):
    """Blank string literals and comments (keeping line count) so brace/indent
    structure isn't fooled by `{` in a string or a comment."""
    out, in_block = [], False
    for line in text.splitlines():
        if in_block:
            j = line.find("*/")
            if j < 0:
                out.append("")
                continue
            line, in_block = line[j + 2:], False
        while True:
            a = line.find("/*")
            if a < 0:
                break
            b = line.find("*/", a + 2)
            if b < 0:
                line, in_block = line[:a], True
                break
            line = line[:a] + " " + line[b + 2:]
        line = _STR.sub('""', line)
        for c in ("//", "#"):
            k = line.find(c)
            if k >= 0:
                line = line[:k]
        out.append(line)
    return out


def _args(s: str) -> int:
    s = s.strip()
    if not s:
        return 0
    return len([a for a in s.split(",") if a.strip() and a.strip() not in ("self", "cls")])


def _magic(lines) -> int:
    n = 0
    for raw in lines:
        code = raw.split("//")[0].split("#")[0]
        if _CONSTLINE.search(code):
            continue
        for num in _NUM.findall(code):
            if num not in _KEEP_NUM:
                n += 1
    return n


def _commented_out(lines) -> int:
    blocks, inblock = 0, False
    for raw in lines:
        s = raw.strip()
        is_comment = s.startswith(("//", "#", "*", "/*"))
        body = s.lstrip("/#* ")
        looks_code = bool(re.search(r'[;{}]\s*$|\)\s*;?\s*$|==|=>|\b(if|for|while|return)\s*\(', body))
        if is_comment and looks_code:
            if not inblock:
                blocks += 1
                inblock = True
        else:
            inblock = False
    return blocks


def _scan_py(lines):
    maxLen = maxArgs = maxNest = methods = 0
    stack = []
    for i, raw in enumerate(lines):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        ind = len(raw) - len(raw.lstrip(" \t"))
        while stack and ind <= stack[-1][1]:
            s, _ = stack.pop()
            maxLen = max(maxLen, i - s)
        m = _DEF_PY.match(raw)
        if m:
            methods += 1
            maxArgs = max(maxArgs, _args(m.group(2)))
            stack.append((i, ind))
        maxNest = max(maxNest, ind // 4)
    for s, _ in stack:
        maxLen = max(maxLen, len(lines) - s)
    return maxLen, maxArgs, maxNest, methods


def _scan_brace(lines):
    maxLen = maxArgs = maxNest = methods = 0
    depth = 0
    open_fns = []
    for i, raw in enumerate(lines):
        code = raw.split("//")[0]
        for m in _DECL2.finditer(code):
            if m.group(1) in _CTRL:
                continue
            after = code[m.end():]
            if "{" in after or (i + 1 < len(lines) and lines[i + 1].lstrip().startswith("{")):
                methods += 1
                maxArgs = max(maxArgs, _args(m.group(2)))
                open_fns.append((i, depth))
                break
        depth += code.count("{") - code.count("}")
        if depth < 0:
            depth = 0
        maxNest = max(maxNest, depth)
        while open_fns and depth <= open_fns[-1][1]:
            s, _ = open_fns.pop()
            maxLen = max(maxLen, i - s + 1)
    for s, _ in open_fns:
        maxLen = max(maxLen, len(lines) - s)
    return maxLen, maxArgs, maxNest, methods


def _scan_uncached(text: str, path: str = "") -> dict:
    try:
        raw = text.splitlines()
        clean = _denoise(text)
        if Path(path).suffix.lower() in _PY_EXT:
            maxLen, maxArgs, maxNest, methods = _scan_py(clean)
        else:
            maxLen, maxArgs, maxNest, methods = _scan_brace(clean)
        return {"maxFnLen": maxLen, "maxArgs": maxArgs, "maxNesting": maxNest,
                "methodCount": methods, "magicNumbers": _magic(clean),
                "commentedOutBlocks": _commented_out(raw)}
    except Exception:
        return {"maxFnLen": 0, "maxArgs": 0, "maxNesting": 0,
                "methodCount": 0, "magicNumbers": 0, "commentedOutBlocks": 0}


def _norm(p) -> str:
    p = str(p).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


_CACHE: dict = {}


def scan_text(text: str, path: str = "") -> dict:
    """Memoized by (suffix, content) sha — re-scanning an unchanged file is free, so a
    re-ingest only pays for what actually changed."""
    key = hashlib.blake2b((Path(path).suffix.lower() + "\x00" + text).encode("utf-8", "replace"),
                          digest_size=16).hexdigest()
    hit = _CACHE.get(key)
    if hit is not None:
        return dict(hit)
    facts = _scan_uncached(text, path)
    _CACHE[key] = facts
    return dict(facts)


def module_craft(model, root: str = "") -> dict:
    """Per-module craft facts, aggregated over each actual-plane module's files
    (maxes for the maxes, sums for the counts). Pure; the model is never mutated."""
    base = Path(root or ".")
    out: dict[str, dict] = {}
    for mid, mod in getattr(model, "modules", {}).items():
        if getattr(mod, "plane", "actual") != "actual" or not getattr(mod, "files", None):
            continue
        agg = {"maxFnLen": 0, "maxArgs": 0, "maxNesting": 0,
               "methodCount": 0, "magicNumbers": 0, "commentedOutBlocks": 0}
        read_any = False
        for f in mod.files:
            try:
                text = (base / _norm(f)).read_text(encoding="utf-8", errors="ignore")
            except (OSError, ValueError):
                continue
            read_any = True
            facts = scan_text(text, f)
            for k in ("maxFnLen", "maxArgs", "maxNesting"):
                agg[k] = max(agg[k], facts[k])
            for k in ("methodCount", "magicNumbers", "commentedOutBlocks"):
                agg[k] += facts[k]
        if read_any:
            out[mid] = agg
    return out
