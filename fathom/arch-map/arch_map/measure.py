"""measure — deterministic architecture indicators the map skill currently *judges*.

Pure and language-aware (Python via `ast`, JS/TS via regex); never mutates the model.
Turns "derive fields by judgement, not formula" into measured facts the agent curates:

  interface_surface(text, path) -> int          public/exported symbols (the seam width)
  module_proxies(model, root)   -> {mid: {...}}  depthProxy, ifaceSize, implLoc, cohesion
  observed_edges(model, root)   -> {mid: [..]}   module dependsOn implied by real imports
  seed_modules(root, files)     -> [dict]        candidate modules (dir clusters + edges)

depthProxy is leverage = implementation-mass / interface-surface, normalized so the
median module is 0.5 (deep -> 1, shallow -> 0) — a measured starting point for `depth`,
never a clobber of the agent's deletion-test judgement.
"""
from __future__ import annotations

import ast
import re
import statistics
import types
from pathlib import Path, PurePosixPath

from .import_graph import extract

_SRC_SUF = {".py", ".pyi", ".js", ".mjs", ".ts", ".tsx", ".jsx"}
_PY_SUF = {".py", ".pyi"}
_JS_EXPORT = re.compile(r'\bexport\s+(?:default\s+)?(?:async\s+)?'
                        r'(?:function|class|const|let|var|interface|type|enum)\b')
_JS_EXPORT_BRACE = re.compile(r'\bexport\s*\{([^}]*)\}')


def _norm(p) -> str:
    p = str(p).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def interface_surface(text: str, path: str = "") -> int:
    """Public/exported symbol count — the width of the seam callers must learn."""
    if Path(path).suffix.lower() in _PY_SUF:
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            return len(re.findall(r'^\s*(?:def|class)\s+(?!_)', text, re.M))
        return sum(1 for n in tree.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                   and not n.name.startswith("_"))
    cnt = len(_JS_EXPORT.findall(text))
    for grp in _JS_EXPORT_BRACE.findall(text):
        cnt += len([x for x in grp.split(",") if x.strip()])
    return cnt


def _impl_loc(text: str) -> int:
    return sum(1 for ln in text.splitlines()
               if ln.strip() and not ln.strip().startswith(("#", "//", "*", "/*")))


def _internal_cohesion(root: Path, files: list[str]) -> float:
    """How interconnected a module's own files are (do they belong together?)."""
    if len(files) < 2:
        return 1.0
    fileset = set(files)
    edges = extract(root, files)["edges"]
    internal = sum(1 for s, t in edges if s in fileset and t in fileset)
    pairs = len(files) * (len(files) - 1) / 2
    return round(min(1.0, internal / pairs), 3) if pairs else 1.0


def module_proxies(model, root: str = "") -> dict:
    base = Path(root or ".")
    raw_lev: dict[str, float] = {}
    info: dict[str, dict] = {}
    for mid, mod in getattr(model, "modules", {}).items():
        if getattr(mod, "plane", "actual") != "actual" or not getattr(mod, "files", None):
            continue
        impl = iface = 0
        owned = [_norm(f) for f in mod.files]
        for f in owned:
            try:
                t = (base / f).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            impl += _impl_loc(t)
            iface += interface_surface(t, f)
        if impl == 0:
            continue
        raw_lev[mid] = impl / max(1, iface)
        info[mid] = {"ifaceSize": max(1, iface), "implLoc": impl,
                     "cohesion": _internal_cohesion(base, owned)}
    if not raw_lev:
        return {}
    med = statistics.median(raw_lev.values()) or 1.0
    for mid, lev in raw_lev.items():
        info[mid]["depthProxy"] = round(lev / (lev + med), 3)
    return info


def observed_edges(model, root: str = "") -> dict:
    """Module-level dependsOn implied by the real import graph (the seedable truth)."""
    base = Path(root or ".")
    files = [_norm(f) for m in model.modules.values() for f in getattr(m, "files", [])]
    edges = extract(base, sorted(set(files)))["edges"]
    owner = model.owners_of(files)
    file_owner: dict[str, list[str]] = {}
    for mid, fs in owner.items():
        for f in fs:
            file_owner.setdefault(_norm(f), []).append(mid)
    deps: dict[str, set] = {}
    for s, t in edges:
        for ms in file_owner.get(s, ()):
            for md in file_owner.get(t, ()):
                if ms != md:
                    deps.setdefault(ms, set()).add(md)
    return {mid: sorted(v) for mid, v in deps.items()}


def _owners_of(mods: dict, paths) -> dict:
    pset = {_norm(p) for p in paths}
    out = {}
    for mid, m in mods.items():
        owned = [f for f in m["files"] if f in pset]
        if owned:
            out[mid] = owned
    return out


def seed_modules(root: str, files: list[str]) -> list[dict]:
    """A measured candidate map: cluster source files by package directory, with
    dependsOn from imports. The agent curates this skeleton instead of authoring it."""
    src = sorted({_norm(f) for f in files if Path(f).suffix.lower() in _SRC_SUF})
    groups: dict[str, list[str]] = {}
    for f in src:
        groups.setdefault(str(PurePosixPath(f).parent) or ".", []).append(f)
    mods: dict[str, dict] = {}
    for d, fs in groups.items():
        mid = d.replace("/", ".").strip(".") or "root"
        mods[mid] = {"id": mid, "label": PurePosixPath(d).name or "root",
                     "domain": (d.split("/")[0] or "root"), "files": sorted(fs)}
    fake = types.SimpleNamespace(
        modules={mid: types.SimpleNamespace(files=m["files"], plane="actual", id=mid)
                 for mid, m in mods.items()},
        owners_of=lambda paths: _owners_of(mods, paths))
    deps = observed_edges(fake, root)
    for mid, m in mods.items():
        m["dependsOn"] = deps.get(mid, [])
    return sorted(mods.values(), key=lambda m: m["id"])


# ---- dependency-category inference (DEEPENING.md) --------------------------------
_THIRD_PARTY = {"stripe", "twilio", "boto3", "sendgrid", "openai", "anthropic", "slack_sdk", "sentry_sdk"}
_NET_DB = {"requests", "httpx", "urllib", "urllib3", "aiohttp", "socket", "psycopg", "psycopg2",
           "sqlalchemy", "redis", "pymongo", "grpc", "kafka", "pika", "mysql", "asyncpg"}
_LOCAL_SUB = {"sqlite3", "tempfile", "shutil"}
_JS_IMP = re.compile(r'(?:require\(|from\s+)["\']([^"\']+)["\']')


def _py_imports(text: str) -> set:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module.split(".")[0])
    return out


def _js_imports(text: str) -> set:
    return {sp.split("/")[0] for sp in _JS_IMP.findall(text) if not sp.startswith(".")}


def _imports_of(root, files) -> set:
    base = Path(root or ".")
    imp = set()
    for f in files:
        try:
            t = (base / _norm(f)).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        imp |= _py_imports(t) if Path(f).suffix.lower() in _PY_SUF else _js_imports(t)
    return imp


def infer_category(root, files) -> str:
    """Best-guess DEEPENING dependency category from a module's external imports."""
    imp = _imports_of(root, files)
    if imp & _THIRD_PARTY:
        return "true-external (mock)"
    if imp & _NET_DB:
        return "remote-owned (ports & adapters)"
    if imp & _LOCAL_SUB:
        return "local-substitutable"
    return "in-process"


def _public_symbols(text: str, path: str) -> set:
    if Path(path).suffix.lower() in _PY_SUF:
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            return set(re.findall(r'^\s*(?:def|class)\s+([A-Za-z]\w*)', text, re.M))
        return {n.name for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and not n.name.startswith("_")}
    return set(re.findall(r'\bexport\s+(?:default\s+)?(?:async\s+)?'
                          r'(?:function|class|const|let|var|interface|type|enum)\s+([A-Za-z]\w*)', text))


def interface_coverage(model, root: str = "") -> dict:
    """Heuristic: fraction of each module's PUBLIC symbols referenced by any test file
    (does the suite assert at the interface, vs. just line coverage?)."""
    base = Path(root or ".")
    test_text, seen = [], set()
    for m in model.modules.values():
        for f in getattr(m, "files", []):
            nf = _norm(f)
            if nf in seen:
                continue
            seen.add(nf)
            if "test" in nf.lower():
                try:
                    test_text.append((base / nf).read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    pass
    blob = "\n".join(test_text)
    out = {}
    for mid, m in model.modules.items():
        if getattr(m, "plane", "actual") != "actual" or not getattr(m, "files", None):
            continue
        syms = set()
        for f in m.files:
            try:
                syms |= _public_symbols((base / _norm(f)).read_text(encoding="utf-8", errors="ignore"), f)
            except OSError:
                continue
        if not syms:
            continue
        hit = sum(1 for s in syms if re.search(r'\b' + re.escape(s) + r'\b', blob))
        out[mid] = round(hit / len(syms), 3)
    return out


def cluster_by_imports(root, files) -> list:
    """Group source files into clusters by import connectivity (connected components) —
    a smarter seed than directory layout when packages span dirs."""
    src = sorted({_norm(f) for f in files if Path(f).suffix.lower() in _SRC_SUF})
    parent = {f: f for f in src}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for s, t in extract(root, src)["edges"]:
        if s in parent and t in parent:
            parent[find(s)] = find(t)
    groups: dict = {}
    for f in src:
        groups.setdefault(find(f), []).append(f)
    return [sorted(v) for v in groups.values()]
