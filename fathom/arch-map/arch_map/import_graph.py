"""import-graph — verify the map's recorded edges against the code's real imports.

Pure static analysis: source files in, a module-level edge diff out. In-process
seam (filesystem reads only); never mutates the model; never raises on broken
source — unparseable files are soft-skipped and LISTED, so a run always
completes. Dynamic imports are out of scope by contract.

Interface (the test surface):
  extract(root, files) -> {"edges": [(src, dst), ...], "unparseable": [files]}
      file-level import pairs among the given repo-relative files. Python via
      ast (absolute imports resolved best-effort against root and the source
      file's ancestors; relative imports against its package); JS/TS via
      import-statement lexing (only relative specifiers resolved).
  verify(model, root) -> {"confirmedEdges", "undeclaredEdges", "missingEdges",
                          "unparseable", "checkedModules", "filesAnalyzed"}
      observed module edges vs the recorded dependsOn/leaksTo graph. An edge is
      reported "missing" only when BOTH its modules own parsed source (so
      conceptual edges between prose modules are never false positives).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path, PurePosixPath

_PY = {".py"}
_JS = {".js", ".mjs", ".ts", ".tsx", ".jsx"}
SUFFIXES = _PY | _JS

_JS_IMPORT = re.compile(
    r"""(?:from\s+|import\s*\(\s*|require\s*\(\s*|^\s*import\s+)['"]([^'"]+)['"]""",
    re.MULTILINE)


def _norm(p: str) -> str:
    p = str(p).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def _py_file_candidates(root: Path, rel: PurePosixPath) -> set[str]:
    out = set()
    for cand in (f"{rel}.py", f"{rel}/__init__.py"):
        if (root / cand).is_file():
            out.add(_norm(cand))
    return out


def _py_targets(root: Path, src_rel: str, tree: ast.AST) -> set[str]:
    src_dir = PurePosixPath(src_rel).parent
    # absolute imports are tried against root AND every ancestor of the source
    # file (so in-repo packages resolve no matter where the repo root sits)
    bases = [PurePosixPath(".")] + [src_dir, *src_dir.parents]
    out: set[str] = set()

    def absolute(dotted: str) -> None:
        if not dotted:
            return
        rel = PurePosixPath(dotted.replace(".", "/"))
        for base in bases:
            joined = rel if str(base) == "." else base / rel
            out.update(_py_file_candidates(root, joined))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:                       # relative: from . / .. import x
                base = src_dir
                for _ in range(node.level - 1):
                    base = base.parent
                mod = PurePosixPath((node.module or "").replace(".", "/"))
                anchor = base / mod if node.module else base
                out.update(_py_file_candidates(root, anchor))
                for alias in node.names:
                    out.update(_py_file_candidates(root, anchor / alias.name))
            else:
                absolute(node.module or "")
                for alias in node.names:
                    absolute(f"{node.module}.{alias.name}" if node.module
                             else alias.name)
    return out


def _js_targets(root: Path, src_rel: str, text: str) -> set[str]:
    src_dir = PurePosixPath(src_rel).parent
    out: set[str] = set()
    for spec in _JS_IMPORT.findall(text):
        if not spec.startswith("."):             # bare specifiers = packages, skip
            continue
        target = PurePosixPath(_posix_normpath(src_dir / spec))
        for cand in (str(target),
                     *(f"{target}{ext}" for ext in (".js", ".mjs", ".ts", ".tsx", ".jsx")),
                     *(f"{target}/index{ext}" for ext in (".js", ".ts"))):
            if (root / cand).is_file():
                out.add(_norm(cand))
                break
    return out


def _posix_normpath(p: PurePosixPath) -> str:
    parts: list[str] = []
    for seg in p.parts:
        if seg == "..":
            if parts:
                parts.pop()
        elif seg != ".":
            parts.append(seg)
    return "/".join(parts)


def extract(root: str | Path, files: list[str]) -> dict:
    root = Path(root)
    edges: list[tuple[str, str]] = []
    unparseable: list[str] = []
    wanted = {_norm(f) for f in files}
    for rel in sorted(wanted):
        p = root / rel
        suffix = p.suffix
        if suffix not in SUFFIXES or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
            if suffix in _PY:
                targets = _py_targets(root, rel, ast.parse(text))
            else:
                targets = _js_targets(root, rel, text)
        except (SyntaxError, UnicodeDecodeError, OSError):
            unparseable.append(rel)
            continue
        edges.extend((rel, dst) for dst in sorted(targets) if dst != rel)
    return {"edges": edges, "unparseable": unparseable}


def verify(model, root: str | Path) -> dict:
    root = Path(root)
    source_files: set[str] = set()
    for m in model.modules.values():           # files OR directory entries
        for f in m.files:
            p = root / _norm(f)
            if p.is_file() and p.suffix in SUFFIXES:
                source_files.add(_norm(f))
            elif p.is_dir():
                source_files.update(
                    _norm(str(q.relative_to(root))) for q in p.rglob("*")
                    if q.is_file() and q.suffix in SUFFIXES)
    source_files = sorted(source_files)
    ex = extract(root, source_files)
    parsed = [f for f in source_files if f not in set(ex["unparseable"])]
    owner = model.owners_of(parsed)                     # mid -> files it owns
    file_owners: dict[str, list[str]] = {}
    for mid, fs in owner.items():
        for f in fs:
            file_owners.setdefault(f, []).append(mid)

    observed: set[tuple[str, str]] = set()
    for src, dst in ex["edges"]:
        for ms in file_owners.get(src, ()):
            for md in file_owners.get(dst, ()):
                if ms != md:
                    observed.add((ms, md))

    recorded: set[tuple[str, str]] = {
        (m.id, t) for m in model.modules.values()
        for t in (m.dependsOn + m.leaksTo)
        if t in model.modules and t != m.id}

    checkable = set(owner)                              # owns >= 1 parsed source file
    fmt = lambda pairs: sorted(f"{a}->{b}" for a, b in pairs)
    return {
        "confirmedEdges": fmt(recorded & observed),
        "undeclaredEdges": fmt(observed - recorded),
        "missingEdges": fmt((a, b) for a, b in recorded - observed
                            if a in checkable and b in checkable),
        "unparseable": ex["unparseable"],
        "checkedModules": sorted(checkable),
        "filesAnalyzed": len(parsed),
    }
