"""arch-map FastMCP server (hybrid UI).

Two rendering lanes, per the explored design:

  Lane 1 — the bespoke *studio* (ui://arch/network.html), inlined from ui/studio/.
           Tools link to it via AppConfig and stream the model into it
           (show_map/get_full_model -> app.ontoolresult); the studio
           routes edits back via app.callServerTool to the action-dispatch tools
           (archmap_modules / archmap_suggestions / archmap_grilling /
           archmap_plans / archmap_docs). The
           same studio is served over HTTP for the browser.
  Lane 2 — FastMCP's Generative UI (Prefab) for ad-hoc charts/tables the model
           improvises ("chart depth across the repo", "table of orphans").

Run:  uv run arch-map      (or)  python -m arch_map.server
Point a UI-capable host (Claude desktop/web, VS Code Insiders, Goose) at it to
*see* the graph; the agent can drive the tools from any MCP client.

Maps: the server holds MANY named maps (one JSON file each under maps/), not a
single model — typically one map per project. Maps are ALWAYS SHARED: there is
no per-agent access control, any client can read or write any map. Every tool
and HTTP route takes an explicit `map` id to say which one it operates on.

NOTE: rendering needs an `_meta.ui` block on BOTH sides, via fastmcp.apps.AppConfig:
the TOOL points at the UI with AppConfig(resourceUri=UI_URI), and the RESOURCE
declares itself the UI with AppConfig() (no resourceUri — it *is* the app). The
original code set the tool link but left the resource a plain @mcp.resource with
no `_meta.ui`, so supporting hosts (Claude desktop/web) fetched the HTML yet never
rendered it as an app — the graph showed up as narrated text. Lane 2 (Prefab)
always rendered because its resource already carries `_meta.ui`.
"""
from __future__ import annotations

from pathlib import Path

from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from typing import Literal
import asyncio
import fcntl
import json
import os
import re
import shutil

from fastmcp import FastMCP
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

try:  # Lane 1 — the custom MCP-App network-graph link — needs fastmcp.apps.AppConfig.
    from fastmcp.apps import AppConfig, ResourceCSP
    _HAS_APPS = True
except Exception:  # pragma: no cover - keeps the core server runnable without the extra
    _HAS_APPS = False

try:  # Lane 2 — Generative/Prefab UI — needs the prefab-ui extra ON TOP of apps, and
    from fastmcp.apps.generative import GenerativeUI  # is independent of Lane 1, so a
    _HAS_PREFAB = True                                # missing prefab must not disable Lane 1.
except Exception:  # pragma: no cover
    _HAS_PREFAB = False

from .model import ArchModel, Module, Suggestion, Plan, WorkStep, Doc
from . import ledger
from .coverage_ingest import module_coverage, read_report
from .git_facts import GitFacts
from .import_graph import verify as verify_imports
from .whatif import preview_merge

HERE = Path(__file__).parent
# The unified **studio** — one workspace combining the dependency graph (canvas)
# and the agent's proposal queue / inspector / module list (right rail) — is now
# BOTH surfaces: served over HTTP for the browser, and inlined as the MCP-App
# resource (Lane 1) so a UI-capable host renders the same thing inline. Its assets
# live under ui/studio/ and are read fresh per request (edit-and-reload, no
# restart). The legacy network.html / decisions.html it replaced are kept only for
# history.
STUDIO_DIR = (HERE / "ui" / "studio").resolve()
STUDIO_INDEX = STUDIO_DIR / "index.html"
VIEW_INDEX = STUDIO_DIR / "view.html"   # on-brand ad-hoc view renderer (tables / charts)
_ASSET_CT = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".map": "application/json; charset=utf-8",
}

mcp = FastMCP("arch-map")

# Persisted, file-backed state. Each *named map* is one JSON file under maps/, so
# many maps (one per project) coexist; every read loads the latest from disk and
# every write saves it back under a lock, so the stdio tools, the HTTP studio, and
# other processes share ONE source of truth per map and survive restarts. A map
# starts EMPTY — no sample is seeded; whatever you add is kept.
LEGACY_STATE = HERE.parent / "arch_state.json"   # pre-multi-map single state file
MAPS_DIR = (HERE.parent / "maps").resolve()


class Store:
    """File-backed ArchModel: load-before-read, save-after-write. Same method
    surface the tools already call, so store.<op>(...) works unchanged."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> ArchModel:
        return ArchModel.from_json(self.path) if self.path.exists() else ArchModel("arch-map", [])

    def _write(self, fn) -> None:
        # Serialize read-modify-write across processes (web app + desktop stdio
        # server share one file) so concurrent writers can't clobber each other.
        lock = self.path.with_name(self.path.name + ".lock")
        with open(lock, "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            m = self._load()
            fn(m)
            m.save(self.path)

    # reads
    def to_dict(self) -> dict: return self._load().to_dict()
    def to_view(self) -> dict: return self._load().to_view()
    def orphans(self): return self._load().orphans()
    def get_module(self, mid): return self._load().get_module(mid)
    def get_modules(self, ids): return self._load().get_modules(ids)
    def get_plan(self, pid): return self._load().get_plan(pid)
    def get_doc(self, did): return self._load().get_doc(did)
    def get_docs(self, ids): return self._load().get_docs(ids)
    def queued_for_grilling(self): return self._load().queued_for_grilling()
    @property
    def modules(self): return self._load().modules
    @property
    def plans(self): return self._load().plans
    @property
    def docs(self): return self._load().docs

    # writes (load -> mutate -> save)
    def set_depth(self, mid, s): self._write(lambda m: m.set_depth(mid, s))
    def set_coverage(self, mid, f): self._write(lambda m: m.set_coverage(mid, f))
    def mark_updated(self, mid, u=True): self._write(lambda m: m.mark_updated(mid, u))
    def set_plane(self, mid, p): self._write(lambda m: m.set_plane(mid, p))
    def set_lifecycle(self, mid, lc): self._write(lambda m: m.set_lifecycle(mid, lc))
    def realize_module(self, mid, depth=None, coverage=None, files=None):
        self._write(lambda m: m.realize_module(mid, depth, coverage, files))
    def add_suggestion(self, mid, s): self._write(lambda m: m.add_suggestion(mid, s))
    def resolve(self, sid): self._write(lambda m: m.resolve(sid))
    def decide(self, sid, d, n="", adr="", expect=None):
        self._write(lambda m: m.decide(sid, d, n, adr, expect))
    def request_grilling(self, sid): self._write(lambda m: m.request_grilling(sid))
    def mark_grilling(self, sid): self._write(lambda m: m.mark_grilling(sid))
    def mark_grilled(self, sid): self._write(lambda m: m.mark_grilled(sid))
    def add_module(self, mod): self._write(lambda m: m.add_module(mod))
    def update_module(self, mid, **ch): self._write(lambda m: m.update_module(mid, **ch))
    def delete_module(self, mid): self._write(lambda m: m.delete_module(mid))
    def add_modules(self, mods): self._write(lambda m: m.add_modules(mods))
    def update_modules(self, ups): self._write(lambda m: m.update_modules(ups))
    def delete_modules(self, ids): self._write(lambda m: m.delete_modules(ids))
    def create_plan(self, plan): self._write(lambda m: m.create_plan(plan))
    def update_plan(self, pid, **ch): self._write(lambda m: m.update_plan(pid, **ch))
    def add_work_steps(self, pid, steps): self._write(lambda m: m.add_work_steps(pid, steps))
    def set_step_status(self, pid, sid, st): self._write(lambda m: m.set_step_status(pid, sid, st))
    def delete_plan(self, pid): self._write(lambda m: m.delete_plan(pid))
    def add_doc(self, doc): self._write(lambda m: m.add_doc(doc))
    def update_doc(self, did, **ch): self._write(lambda m: m.update_doc(did, **ch))
    def delete_doc(self, did): self._write(lambda m: m.delete_doc(did))
    def record_anchor(self, sha, ts, keep=200):
        self._write(lambda m: ledger.record_anchor(m, sha, ts, keep))


_MAP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _slug(s: str) -> str:
    """Turn a free-text map name into a clean id: lowercase, alphanumeric runs
    joined by single dashes ('Mr. Meeseeks' -> 'mr-meeseeks')."""
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "default"


class MapRegistry:
    """A directory of named, file-backed maps (maps/<id>.json). Resolves a map id
    to a Store, lists summaries for the switcher, and creates/deletes maps. Map
    ids are slugs ([a-z0-9._-], no '/' and no leading dot) so a request can never
    read or write outside the maps directory."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy()

    def _migrate_legacy(self) -> None:
        # Fold a pre-existing single arch_state.json into maps/<repo>.json once, so
        # existing data shows up as a named map. Non-destructive (copy; keep original).
        if LEGACY_STATE.exists() and not any(self.root.glob("*.json")):
            try:
                mid = _slug(json.loads(LEGACY_STATE.read_text()).get("repo") or "default")
            except Exception:
                mid = "default"
            (self.root / f"{mid}.json").write_text(LEGACY_STATE.read_text(encoding="utf-8"), encoding="utf-8")

    def path(self, map_id: str) -> Path:
        if not _MAP_ID_RE.match(map_id or ""):
            raise ValueError(f"invalid map id '{map_id}' (use lowercase a-z, 0-9, . _ -)")
        p = (self.root / f"{map_id}.json").resolve()
        if self.root not in p.parents:           # belt-and-suspenders vs traversal
            raise ValueError(f"invalid map id '{map_id}'")
        return p

    def exists(self, map_id: str) -> bool:
        try:
            return self.path(map_id).exists()
        except ValueError:
            return False

    def store(self, map_id: str) -> Store:
        p = self.path(map_id)
        if not p.exists():
            raise KeyError(f"no map '{map_id}' (create it with create_project, "
                           f"or call list_maps to see existing map ids)")
        return Store(p)

    def create(self, map_id: str, repo: str = "") -> Store:
        p = self.path(map_id)
        if p.exists():
            raise KeyError(f"map '{map_id}' already exists")
        ArchModel(repo or map_id, []).save(p)
        return Store(p)

    def ensure(self, map_id: str, repo: str = "") -> Store:
        """Get the map, creating an empty one if it doesn't exist yet."""
        try:
            return self.store(map_id)
        except KeyError:
            return self.create(map_id, repo)

    def delete(self, map_id: str) -> None:
        p = self.path(map_id)
        if not p.exists():
            raise KeyError(f"no map '{map_id}'")
        p.unlink()
        lock = p.with_name(p.name + ".lock")
        if lock.exists():
            lock.unlink()

    def rename(self, old_id: str, new_id: str, repo: str | None = None) -> Store:
        """Rename a map (move maps/<old>.json -> <new>.json) and/or relabel its
        repo. Pass new_id == old_id to only change the repo label."""
        src = self.path(old_id)
        if not src.exists():
            raise KeyError(f"no map '{old_id}'")
        dst = self.path(new_id)
        if dst.exists() and dst != src:
            raise KeyError(f"map '{new_id}' already exists")
        data = json.loads(src.read_text())
        if repo is not None:
            data["repo"] = repo
        dst.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if dst != src:
            src.unlink()
            lock = src.with_name(src.name + ".lock")
            if lock.exists():
                lock.unlink()
        return Store(dst)

    def list(self) -> list[dict]:
        out = []
        for f in sorted(self.root.glob("*.json")):
            try:
                v = ArchModel.from_json(f).to_view()
                out.append({"id": f.stem, "repo": v["repo"], "modules": len(v["modules"]),
                            "openSuggestions": len(v["openSuggestions"]), "orphans": len(v["orphans"])})
            except Exception:
                out.append({"id": f.stem, "repo": "", "modules": 0,
                            "openSuggestions": 0, "orphans": 0, "broken": True})
        return out

    def default_id(self) -> str:
        files = sorted(self.root.glob("*.json"))
        return files[0].stem if files else "default"

    def resolve(self, map_id: str | None) -> Store:
        """HTTP convenience: an explicit id must exist; no id falls back to the
        default map (bootstrapping an empty one on a fresh install)."""
        if map_id:
            return self.store(map_id)            # raises KeyError -> 404/400
        mid = self.default_id()
        return self.store(mid) if self.exists(mid) else self.create(mid)


REGISTRY = MapRegistry(MAPS_DIR)

# --- Lane 2: generative Prefab UI for ad-hoc charts/tables -------------------
if _HAS_PREFAB:
    mcp.add_provider(GenerativeUI())

# --- Lane 1: the bespoke network-graph UI as a pre-declared MCP Apps resource -
# A host renders this only when BOTH sides carry an `_meta.ui` block (via AppConfig):
#   * tools point at the UI     -> AppConfig(resourceUri=UI_URI)
#   * the resource *is* the UI   -> AppConfig()  (no resourceUri)
# The UI's <script> imports the @modelcontextprotocol/ext-apps client from jsDelivr
# to run the host handshake (App.connect()), so the sandbox CSP whitelists that
# origin. None-guarded so the server still imports/runs without the fastmcp[apps]
# extra — it just won't carry the UI link, and the host falls back to text.
UI_URI = "ui://arch/network.html"  # every working MCP-App example ends the URI in .html
_UI_CSP = (
    ResourceCSP(
        resourceDomains=[
            "https://cdn.jsdelivr.net",       # @modelcontextprotocol/ext-apps (host bridge)
            "https://cdnjs.cloudflare.com",   # elkjs (graph layout)
            "https://fonts.googleapis.com",   # studio fonts (stylesheet)
            "https://fonts.gstatic.com",      # studio fonts (font files)
        ],
        connectDomains=["https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com"],
    )
    if _HAS_APPS else None
)
UI_APP = AppConfig(resourceUri=UI_URI, csp=_UI_CSP) if _HAS_APPS else None  # studio tools -> point at the studio UI
UI_RESOURCE_APP = AppConfig(csp=_UI_CSP) if _HAS_APPS else None             # resource -> is a UI (shared by both)
# The ad-hoc view renderer is a second UI: render_view points at it; it shares the CSP.
VIEW_URI = "ui://arch/view.html"
VIEW_APP = AppConfig(resourceUri=VIEW_URI, csp=_UI_CSP) if _HAS_APPS else None
# Spread these into the decorators instead of hard-coding `app=...`: without the
# fastmcp[apps] extra there's no MCP-App link (the host falls back to text), and a
# FastMCP that predates the `app=` kwarg would otherwise raise on import. The HTTP
# studio (custom routes + /api) doesn't need apps and works either way.
_APP = {"app": UI_APP} if _HAS_APPS else {}
_VIEW_APP = {"app": VIEW_APP} if _HAS_APPS else {}
_RES_APP = {"app": UI_RESOURCE_APP} if _HAS_APPS else {}


def _inline_app(index_path: Path) -> str:
    """Inline a ui/studio page for the MCP-App sandbox.

    A host renders the resource in a sandboxed iframe that can't reach the HTTP
    server, so we inline its `/assets/*` CSS/JS (read fresh, so edits propagate)
    and set window.__ARCH_APP__ before any script runs. That flag flips the page's
    data layer into **host mode** — it connects via @modelcontextprotocol/ext-apps
    and drives everything through tools instead of /api. The elkjs + ext-apps CDN
    tags stay (whitelisted by _UI_CSP). Same files the browser serves, so the inline
    render mirrors the browser exactly."""
    html = index_path.read_text(encoding="utf-8")

    def _rel(p: str) -> str:                       # "/assets/shared/ui.css" -> "shared/ui.css"
        return p.lstrip("/").removeprefix("assets/")

    def _css(m) -> str:
        return f"<style>\n{(STUDIO_DIR / _rel(m.group(1))).read_text(encoding='utf-8')}\n</style>"

    def _js(m) -> str:
        return f"<script>\n{(STUDIO_DIR / _rel(m.group(1))).read_text(encoding='utf-8')}\n</script>"

    html = re.sub(r'<link rel="stylesheet" href="(/assets/[^"]+)">', _css, html)
    html = re.sub(r'<script src="(/assets/[^"]+)"></script>', _js, html)
    # flip into host mode before any script runs (works for pages with or without state.js)
    return html.replace("</head>", "<script>window.__ARCH_APP__ = true;</script>\n</head>", 1)


@mcp.resource(UI_URI, mime_type="text/html;profile=mcp-app", **_RES_APP)
def studio_ui() -> str:
    """The unified studio, inlined for the MCP-App sandbox. A host renders this in a
    sandboxed iframe and drives it through the tools: show_map names the
    map, get_full_model feeds the full model, and the action-dispatch tools
    (modules / suggestions / grilling / plans / docs) mutate it — every change
    re-rendered with the studio's own components."""
    return _inline_app(STUDIO_INDEX)


@mcp.resource(VIEW_URI, mime_type="text/html;profile=mcp-app", **_RES_APP)
def view_ui() -> str:
    """The on-brand ad-hoc view renderer (tables / bar charts), inlined for the
    MCP-App sandbox. render_view pushes a prepared view into it; it draws with the
    studio's design tokens, so generative views match the studio."""
    return _inline_app(VIEW_INDEX)


# --- Ad-hoc views: shape a map's data into an on-brand table / bar chart --------
# Both the render_view tool (MCP-App hosts) and GET /api/view (browser) call this,
# so the model picks WHAT to show (a declarative spec) and the view renderer draws
# it with the studio's design tokens — the "generative" lane, but on-brand.
_STRENGTH_KEY = {"Strong": "strong", "Worth exploring": "worth", "Speculative": "speculative"}
_VIEW_COLS = ("id", "label", "domain", "depth", "coverage", "tests", "files", "suggestion")


def _has_tests(prose) -> bool:
    """The `tests` field is prose; "none — browser-only" is a recorded FACT of no
    tests, not a test reference, so it must not render as a checkmark."""
    t = (prose or "").strip()
    return bool(t) and not t.lower().startswith(("none", "n/a", "no "))

_VALID_METRICS = frozenset({"depth", "coverage"})
_VALID_GROUP_BY = frozenset({"module", "domain"})
_VALID_AGG = frozenset({"avg", "count"})


@dataclass
class TableSpec:
    of: str = "all"
    columns: list = field(default_factory=lambda: ["id", "domain", "depth", "coverage"])
    sortBy: str | None = None
    sortDir: str = "asc"
    title: str = ""


@dataclass
class BarSpec:
    metric: str = "depth"
    groupBy: str = "module"
    agg: str = "avg"
    of: str = "all"
    title: str = ""


def _parse_view_spec(spec: dict) -> TableSpec | BarSpec:
    """Parse a freeform spec dict into a typed TableSpec or BarSpec.
    Resolves aliases (filter->of, group->groupBy, sort->sortBy).
    Raises ValueError on invalid kind, metric, groupBy, or agg.
    """
    raw = spec or {}
    kind = (raw.get("kind") or "table").lower()
    if kind not in ("table", "bar"):
        raise ValueError(f"invalid view kind {kind!r}; expected 'table' or 'bar'")
    of = raw.get("of") or raw.get("filter") or "all"
    title = raw.get("title") or ""
    if kind == "bar":
        metric = (raw.get("metric") or "depth").lower()
        if metric not in _VALID_METRICS:
            raise ValueError(f"invalid metric {metric!r}; expected one of {sorted(_VALID_METRICS)}")
        groupBy = (raw.get("groupBy") or raw.get("group") or "module").lower()
        if groupBy not in _VALID_GROUP_BY:
            raise ValueError(f"invalid groupBy {groupBy!r}; expected one of {sorted(_VALID_GROUP_BY)}")
        agg = (raw.get("agg") or "avg").lower()
        if agg not in _VALID_AGG:
            raise ValueError(f"invalid agg {agg!r}; expected one of {sorted(_VALID_AGG)}")
        return BarSpec(metric=metric, groupBy=groupBy, agg=agg, of=of, title=title)
    sortRaw = raw.get("sortBy") or raw.get("sort")
    if isinstance(sortRaw, dict):
        sortDir = sortRaw.get("dir", "asc")
        sortBy = sortRaw.get("by")
    else:
        sortBy = sortRaw
        sortDir = raw.get("sortDir", "asc")
    columns = list(raw.get("columns") or ["id", "domain", "depth", "coverage"])
    return TableSpec(of=of, columns=columns, sortBy=sortBy, sortDir=sortDir, title=title)


def _view_filter(modules: list[dict], of: str, model: dict) -> list[dict]:
    """Select modules by a simple predicate keyword (or a domain name)."""
    of = (of or "all").lower()
    orphans = set(model.get("orphans", []))

    def keep(m: dict) -> bool:
        d, c = (m.get("depth") or 0), (m.get("coverage") or 0)
        if of in ("", "all"): return True
        if of in ("orphans", "orphan", "not-connected"): return m["id"] in orphans
        if of == "leaks": return bool(m.get("leaksTo"))
        if of in ("suggestions", "proposals", "open"): return bool(m.get("suggestion"))
        if of == "updated": return bool(m.get("updated"))
        if of in ("low-coverage", "low"): return c < 0.4
        if of == "shallow": return d < 0.34
        if of == "mid": return 0.34 <= d < 0.67
        if of == "deep": return d >= 0.67
        return m.get("domain") == of           # otherwise treat as a domain name
    return [m for m in modules if keep(m)]


def _build_view(model: dict, spec: TableSpec | BarSpec) -> dict:
    """Turn a typed view spec + a full model into a prepared view payload the
    renderer draws verbatim (numbers already scaled to 0..100 for display)."""
    of = spec.of
    sel = _view_filter(model.get("modules", []), of, model)
    label = "all modules" if str(of).lower() in ("", "all") else of
    kind = "bar" if isinstance(spec, BarSpec) else "table"
    out = {"kind": kind, "title": spec.title or f"{kind} · {label}",
           "repo": model.get("repo", ""), "count": len(sel)}

    if isinstance(spec, BarSpec):
        out["metric"], out["groupBy"] = spec.metric, spec.groupBy
        if spec.groupBy == "domain":
            buckets: dict[str, list[float]] = {}
            for m in sel:
                buckets.setdefault(m.get("domain", "—"), []).append(m.get(spec.metric) or 0)
            if spec.agg == "count":
                mx = max((len(v) for v in buckets.values()), default=1) or 1
                bars = [{"label": d, "value": str(len(v)), "pct": round(len(v) / mx * 100)} for d, v in buckets.items()]
            else:
                bars = [{"label": d, "value": f"{round(sum(v) / len(v) * 100)}%", "pct": round(sum(v) / len(v) * 100)} for d, v in buckets.items()]
        else:
            bars = [{"label": m["id"], "value": f"{round((m.get(spec.metric) or 0) * 100)}%", "pct": round((m.get(spec.metric) or 0) * 100)} for m in sel]
        bars.sort(key=lambda b: b["pct"], reverse=True)
        out["bars"] = bars
    else:
        cols = [c for c in spec.columns if c in _VIEW_COLS]
        cols = cols or ["id", "domain", "depth", "coverage"]
        rows = []
        for m in sel:
            row = {}
            for c in cols:
                if c in ("depth", "coverage"): row[c] = round((m.get(c) or 0) * 100)
                elif c == "suggestion":
                    s = m.get("suggestion")
                    row[c] = {"strength": _STRENGTH_KEY.get(s["strength"], "speculative"), "label": s["strength"]} if s else None
                elif c == "files": row[c] = len(m.get("files") or [])
                elif c == "tests": row[c] = "✓" if _has_tests(m.get("tests")) else ""
                else: row[c] = m.get(c)
            rows.append(row)
        if spec.sortBy in cols:
            rows.sort(key=lambda r: (r.get(spec.sortBy) is None, r.get(spec.sortBy)), reverse=(spec.sortDir == "desc"))
        out["columns"], out["rows"] = cols, rows
    return out


# --- Tools the project-agent drives. Every tool takes `map` — the named map it
# operates on (one per project). Mutations return a compact ack — the full model
# is too big for an agent's context (the browser UIs fetch it from /api/model and
# the graph polls). show_map returns a digest.
def _ack(store: Store, changed: str | None = None) -> dict:
    v = store.to_view()
    ack = {"ok": True, "changed": changed, "repo": v["repo"], "modules": len(v["modules"]),
           "orphans": v["orphans"], "openSuggestions": v["openSuggestions"],
           "docs": len(v.get("docs", []))}
    ids = {m["id"] for m in v["modules"]}
    dangling = sorted({f"{m['id']}->{t}"
                       for m in v["modules"]
                       for key in ("dependsOn", "leaksTo")
                       for t in (m.get(key) or []) if t not in ids})
    if dangling:                       # edge targets that match no module — usually a typo'd id
        ack["unresolvedEdges"] = dangling
    return ack


# Every string an agent reads is an instruction: when a dispatcher fails, the error
# must carry the call context, the atomicity guarantee, and a next step — not a bare
# KeyError. Writes go through Store (load -> mutate -> save under one lock), so a
# failed write means NOTHING was persisted.
def _guard(call: str, write: bool, hint: str, fn):
    try:
        return fn()
    except (KeyError, ValueError) as e:            # expected — keep the type, add context
        msg = e.args[0] if e.args else str(e)
        raise type(e)(_fail(call, str(msg), write, hint)) from e
    except Exception as e:  # unexpected — still reach the agent with context
        raise ValueError(_fail(call, f"{type(e).__name__}: {e}", write, hint)) from e


def _fail(call: str, msg: str, write: bool, hint: str) -> str:
    atomic = " Nothing was written — writes are all-or-nothing." if write else ""
    return f"{call} failed: {msg}.{atomic}" + (f" {hint}" if hint else "")


@mcp.tool(name="archmap_list_maps")
def list_maps(limit: int = 50, offset: int = 0) -> dict:
    """List the available architecture maps (id, repo label, module/proposal counts).
    Maps are shared — any agent can read or write any of them; pass the id as `map`.
    Use `limit` (default 50) and `offset` to page `maps`; the response carries
    total_count / has_more / next_offset."""
    all_maps = REGISTRY.list()
    page = all_maps[offset:offset + limit]
    return {"maps": page, "default": REGISTRY.default_id(),
            "total_count": len(all_maps),
            "has_more": offset + limit < len(all_maps),
            "next_offset": offset + limit if offset + limit < len(all_maps) else None}


@mcp.tool(name="archmap_create_map", **_APP)
def create_project(name: str, map_id: str = "", repo: str = "") -> dict:
    """Create a new map (one per project/repo) and open it empty, then render it.

    When to use: starting a new project/map (typically one per repo). `name` is the
    human project name (e.g. "Mr. Meeseeks") and becomes the display label. By
    default the map id is slugged from `name` ("mr-meeseeks"); pass `map_id` to set
    the id explicitly (lowercase a-z, 0-9, . _ -) and `repo` to override the display
    label. Returns the map id as `map` — pass it to archmap_modules(action="add", ...)
    and archmap_suggestions(action="flag", ...) to populate the map. Maps are shared:
    any agent can read or write this one."""
    mid = map_id if map_id else _slug(name)   # explicit id passes through (REGISTRY validates it)
    ack = _ack(REGISTRY.create(mid, repo or name or mid), changed=f"created project {mid}")
    ack["map"] = mid          # the id to pass to subsequent tool calls
    return ack


@mcp.tool(name="archmap_rename_map", **_APP)
def rename_map(map: str, to: str, repo: str = "") -> dict:
    """Rename a map. `map` is the current id, `to` the new id, `repo` the new
    display label (defaults to `to` if blank). Use to point a map at a real
    project, e.g. rename_map("arch-map", "mr-meeseeks", "Mr. Meeseeks")."""
    new_id = _slug(to)
    return _ack(REGISTRY.rename(map, new_id, repo or to), changed=f"renamed {map} -> {new_id}")


@mcp.tool(name="archmap_delete_map")
def delete_map(map: str) -> dict:
    """Delete an entire named map and its file. IRREVERSIBLE — the map's JSON file
    is removed permanently and there is no undo; archmap_list_maps first if unsure."""
    REGISTRY.delete(map)
    return {"ok": True, "deleted": map, "maps": [m["id"] for m in REGISTRY.list()]}


@mcp.tool(name="archmap_show_map", **_APP)
def show_map(map: str, domain: str = "", ids: list[str] | None = None) -> dict:
    """Render a map — a DIGEST by default, module records only on request. Creates
    the map empty if it doesn't exist yet.

    No filter -> digest: module/domain counts, orphans, open suggestions, and the
    ten worst-health modules. It deliberately does NOT return every module record
    (that grows with the map); pass `domain="<d>"` or `ids=[...]` to get the full
    view records for just that slice, or call archmap_get_full_model for everything.
    Inside an MCP-App host this drives the inline studio: the result tells the
    studio which `map` to render and it pulls the full model itself."""
    store = REGISTRY.ensure(map)
    v = store.to_view()
    if domain or ids:
        want = set(ids or [])
        sel = [m for m in v["modules"]
               if (m["id"] in want) or (domain and m.get("domain") == domain)]
        return {"map": map, "repo": v["repo"], "count": len(sel), "modules": sel}
    domains: dict[str, int] = {}
    for m in v["modules"]:
        d = m.get("domain") or "—"
        domains[d] = domains.get(d, 0) + 1
    worst = sorted(v["modules"], key=lambda m: (m.get("metrics") or {}).get("health", 100))[:10]
    return {
        "map": map, "repo": v["repo"],
        "moduleCount": len(v["modules"]),
        "domains": domains,
        "staleness": ledger.staleness_line(store._load(), GitFacts(os.getcwd())),
        "orphans": v["orphans"],
        "openSuggestions": v["openSuggestions"],
        "plans": len(v.get("plans", [])),
        "docs": len(v.get("docs", [])),
        "worstHealth": [{"id": m["id"], "domain": m.get("domain"),
                         "depth": m.get("depth"), "coverage": m.get("coverage"),
                         "health": (m.get("metrics") or {}).get("health")} for m in worst],
        "hint": "digest only — pass domain= or ids=[...] for module records; "
                "archmap_get_full_model(map) for the whole model",
    }


@mcp.tool(name="archmap_get_full_model", **_APP)
def get_full_model(map: str) -> dict:
    """Return a map's FULL model — every module's interface, files, tests, and
    suggestion bodies — which is what the inline studio renders. Heavier than
    archmap_show_map (the digest), so the studio calls this once it knows the
    map and after each edit; agents normally use archmap_show_map."""
    v = REGISTRY.ensure(map).to_dict()
    v["map"] = map
    return v


@mcp.tool(name="archmap_render_view", **_VIEW_APP)
def render_view(
    map: str,
    kind: Literal["table", "bar"] = "table",
    of: str = "all",
    columns: list[str] | None = None,
    sort_by: str = "",
    sort_dir: Literal["asc", "desc"] = "asc",
    metric: Literal["depth", "coverage"] = "depth",
    group_by: Literal["module", "domain"] = "module",
    agg: Literal["avg", "count"] = "avg",
    title: str = "",
) -> dict:
    """Render an on-brand ad-hoc VIEW of a map — a table or bar chart drawn with the
    studio's own design (not generic widgets).

    `of` selects which modules: "all" | "orphans" | "leaks" | "suggestions" |
    "updated" | "low-coverage" | "shallow" | "mid" | "deep" | <domain name>.
    Tables use `columns` (any of id, label, domain, depth, coverage, tests, files,
    suggestion), `sort_by` (a chosen column) and `sort_dir`. Bars use `metric`,
    `group_by` and `agg`; `title` overrides the heading.

    e.g. archmap_render_view(map, of="low-coverage", columns=["id","domain","coverage"], sort_by="coverage")
         archmap_render_view(map, kind="bar", metric="coverage", group_by="domain", agg="avg")"""
    spec: dict = {"kind": kind, "of": of, "title": title}
    if kind == "bar":
        spec |= {"metric": metric, "groupBy": group_by, "agg": agg}
    else:
        if columns:
            spec["columns"] = columns
        if sort_by:
            spec |= {"sortBy": sort_by, "sortDir": sort_dir}
    payload = _build_view(REGISTRY.store(map).to_dict(), _parse_view_spec(spec))
    payload["map"] = map
    return payload


@mcp.tool(name="archmap_get_metrics")
def get_metrics(map: str, module: str | None = None,
                        limit: int = 50, offset: int = 0) -> dict:
    """Return computed graph metrics for one module or all modules in `map`:
    fanIn, fanOut, instability, blastRadius, coupling, inCycle, health, churn.
    These are derived from the dependency graph — no extra data needed.

    Pass `module` for a single module's metrics. With no `module`, returns a page of
    all modules' metrics (keyed by id, ordered by id) — use `limit` (default 50) and
    `offset` to page; the response carries total_count / has_more / next_offset."""
    model = REGISTRY.store(map)._load()
    all_metrics = model.compute_metrics()
    if module:
        if module not in model.modules:
            raise KeyError(f"no module '{module}' in map '{map}'. "
                           f"Call archmap_get_metrics(map) for all modules, or "
                           f"archmap_show_map(map) to list module ids.")
        return {"map": map, "module": module, "metrics": all_metrics[module]}
    ids = sorted(all_metrics)
    page = ids[offset:offset + limit]
    return {"map": map,
            "metrics": {mid: all_metrics[mid] for mid in page},
            "total_count": len(ids),
            "has_more": offset + limit < len(ids),
            "next_offset": offset + limit if offset + limit < len(ids) else None}


def _compute_signals(m, mx: dict) -> list[str]:
    """Return the list of signal ids that fire for a module + its metrics dict."""
    signals = []
    cov = m.coverage         # 0..1
    churn = mx["churn"]      # 0..1
    if churn >= 0.4 and cov < 0.4:
        signals.append("danger-zone")
    if mx["blastRadius"] >= 10 and cov < 0.6:
        signals.append("critical-path-untested")
    if mx["inCycle"]:
        signals.append("circular-dep")
    if mx["fanOut"] >= 6 and m.depth < 0.5:
        signals.append("needs-refactor")
    if mx["fanIn"] >= 8 and mx["fanOut"] >= 6:
        signals.append("god-module")
    if mx["fanIn"] >= 8 and m.depth < 0.4:
        signals.append("bottleneck")
    if mx["blastRadius"] >= 5 and cov < 0.3:
        signals.append("test-first")
    if mx["instability"] > 0.7 and mx["fanIn"] >= 3:
        signals.append("unstable-api")
    if mx["fanOut"] >= 5 and mx["coupling"] >= 3:
        signals.append("split-candidate")
    if m.size >= 2.0 and m.depth < 0.5:
        signals.append("bulky-impl")
    if m.leaksTo:
        signals.append("leaky-seam")
    return signals


@mcp.tool(name="archmap_scan_signals")
def scan_signals(map: str, signal: str | None = None,
                         limit: int = 50, offset: int = 0) -> dict:
    """Scan a map for structural signals (rules-based architectural issues).

    Returns the modules that have at least one signal, with the signals they
    carry and a health score, sorted worst-first (lowest health). Optionally filter
    by a specific signal id. Results are paged: `limit` (default 50) and `offset`
    bound `modules`; `total` is the full count and the response carries has_more /
    next_offset. `signalCounts` always summarises the FULL result set, not the page.

    Signal ids:
      danger-zone             high churn + low coverage (highest risk)
      critical-path-untested  high blast radius + low coverage
      circular-dep            part of a dependency cycle
      needs-refactor          high fan-out + low depth
      god-module              high fan-in AND fan-out
      bottleneck              high fan-in + low depth
      test-first              high blast radius + very low coverage
      unstable-api            high instability + depended-upon
      split-candidate         high fan-out crossing many domains
      bulky-impl              large implementation mass for little depth (see MINIMALISM.md)
      leaky-seam              has seam violations (leaksTo)

    Use `signal=<id>` to focus on one issue type, e.g.
    scan_signals(map, "test-first") returns the modules you should write
    tests for first, in priority order."""
    model = REGISTRY.store(map)._load()
    all_metrics = model.compute_metrics()
    results = []
    for m in model.modules.values():
        mx = all_metrics[m.id]
        sigs = _compute_signals(m, mx)
        if signal and signal not in sigs:
            continue
        if not sigs and not signal:
            continue
        results.append({
            "id": m.id, "label": m.label, "domain": m.domain,
            "signals": sigs,
            "health": mx["health"],
            "depth": round(m.depth * 100),
            "coverage": round(m.coverage * 100),
            "fanIn": mx["fanIn"], "fanOut": mx["fanOut"],
            "blastRadius": mx["blastRadius"],
        })
    results.sort(key=lambda r: (r["health"], r["id"]))  # worst health first
    summary = {}
    for r in results:                                   # summarise the FULL set, not the page
        for s in r["signals"]:
            summary[s] = summary.get(s, 0) + 1
    page = results[offset:offset + limit]
    return {
        "map": map,
        "filter": signal,
        "total": len(results),
        "signalCounts": summary,
        "modules": page,
        "has_more": offset + limit < len(results),
        "next_offset": offset + limit if offset + limit < len(results) else None,
    }


# --- Ground truth: measured facts, drift, history, edge verification ---------
# These tools make the map self-truing: churn/coverage/LOC become measurements
# (git-facts + coverage-ingest), anchors recorded by the reconcile flow give the
# digest its staleness line (reconcile-ledger), and recorded edges are checked
# against real imports (import-graph). `root` is the repo work tree; it defaults
# to the server's cwd.
def _repo_root(root: str) -> str:
    return root or os.getcwd()


@mcp.tool(name="archmap_ingest")
def ingest(map: str, root: str = "", coverage_report: str = "",
           window_days: int = 90, anchor: bool = True) -> dict:
    """Measure ground truth for `map` and patch module facts in ONE locked write.

    churn: per actual-plane module with files, the share of the last
    `window_days`' commits touching those files (git history — measured, not
    estimated). coverage: only when `coverage_report` names a coverage.py
    XML/JSON or lcov file — line-weighted per module via its files; module
    halos are NOT flipped (fathom:map owns them). size: per actual-plane module
    with files, measured LOC normalized to relative implementation mass (1.0 ==
    the median measured module) — what the bulky-impl signal and whatif
    merge-weighting read; intended/file-less modules keep their estimate. Unless
    anchor=False, records a reconcile anchor
    (HEAD sha + per-module snapshot) — the baseline archmap_drift and
    archmap_history read. `root` defaults to the server's cwd."""
    call = f"archmap_ingest(map='{map}')"
    hint = ("Pass root=<repo work tree> if the server does not run inside the "
            "repo; coverage_report is optional.")
    return _guard(call, True, hint, lambda: _ingest_impl(
        map, root, coverage_report, window_days, anchor))


def _ingest_impl(map, root, coverage_report, window_days, anchor) -> dict:
    store = REGISTRY.store(map)
    g = GitFacts(_repo_root(root))
    head = g.head_sha()                       # NotARepo/UnknownSha -> guarded
    report = read_report(coverage_report) if coverage_report else None
    out = {"ok": True, "map": map, "sha": head, "churned": 0, "covered": 0,
           "sized": 0, "loc": {}, "anchor": None}

    def mutate(m):
        cov = module_coverage(m, report) if report else {}
        locs: dict[str, int] = {}
        for mid, mod in m.modules.items():
            if mod.plane != "actual" or not mod.files:
                continue
            mod.churn = max(0.0, min(1.0, g.churn(mod.files, window_days)))
            out["churned"] += 1
            locs[mid] = g.loc(mod.files)
            out["loc"][mid] = locs[mid]
        # Relative implementation mass from measured LOC: 1.0 == the median
        # measured module, so `size` stops being an eyeballed estimate and the
        # bulky-impl signal / whatif weighting rest on a real fact.
        # Median (not mean) keeps one outlier from shrinking everyone else.
        measured = sorted(n for n in locs.values() if n > 0)
        if measured:
            k = len(measured)
            median = (measured[k // 2] if k % 2
                      else (measured[k // 2 - 1] + measured[k // 2]) / 2)
            median = median or 1
            for mid, n in locs.items():
                if n > 0:
                    m.modules[mid].size = round(n / median, 3)
                    out["sized"] += 1
        for mid, frac in cov.items():
            if mid in m.modules:
                m.modules[mid].coverage = max(0.0, min(1.0, frac))
                out["covered"] += 1
        if anchor:
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            a = ledger.record_anchor(m, head, ts)
            out["anchor"] = {"sha": a["sha"], "ts": a["ts"],
                             "moduleCount": a["moduleCount"]}

    store._write(mutate)
    if report:
        out["unmappedCoverage"] = round(
            module_coverage(store._load(), report).get("_unmapped", 0.0), 3)
    return out


@mcp.tool(name="archmap_drift")
def drift(map: str, since_sha: str = "", root: str = "") -> dict:
    """How stale is the map? Changes since the last reconcile anchor (or since an
    explicit `since_sha` baseline — the review-style question): the changed files,
    the modules they belong to, the changed files NO module owns, and a one-line
    summary. Read-only; degraded outcomes (no anchors / no repo) come back with
    anchored=false and a `reason`, never an error."""
    call = f"archmap_drift(map='{map}')"
    hint = "Record a baseline first via archmap_ingest(map) on a reconcile."

    def run():
        model = REGISTRY.store(map)._load()
        out = ledger.drift(model, GitFacts(_repo_root(root)), since_sha or None)
        out["map"] = map
        return out
    return _guard(call, False, hint, run)


@mcp.tool(name="archmap_history")
def history(map: str, module: str = "", domain: str = "",
            metrics: list[str] | None = None) -> dict:
    """Trend series across the map's reconcile anchors, oldest -> newest: health/
    depth/coverage per module (default: every module ever anchored), for one
    `module`, or aggregated as the mean over one `domain`. Series lists are
    index-aligned with `anchors` (null where a module did not exist yet).
    Read-only; zero anchors -> empty lists, not an error."""
    call = f"archmap_history(map='{map}')"
    hint = "Anchors are recorded by archmap_ingest; run it on each reconcile."

    def run():
        model = REGISTRY.store(map)._load()
        out = ledger.history(model, module_id=module, domain=domain,
                             metrics=tuple(metrics) if metrics else ledger.METRICS)
        out["map"] = map
        return out
    return _guard(call, False, hint, run)


@mcp.tool(name="archmap_verify_edges")
def verify_edges(map: str, root: str = "") -> dict:
    """Check the map's recorded dependsOn/leaksTo edges against the code's REAL
    imports (Python via ast, JS/TS via import lexing). Returns confirmedEdges,
    undeclaredEdges (in code but not on the map — candidate leaks), missingEdges
    (on the map but not in code; only reported when both modules own parsed
    source, so prose modules never false-positive), and the unparseable files.
    Read-only — surfacing is this tool's job, deciding is fathom:map's."""
    call = f"archmap_verify_edges(map='{map}')"
    hint = "Pass root=<repo work tree> if the server does not run inside the repo."

    def run():
        out = verify_imports(REGISTRY.store(map)._load(), _repo_root(root))
        out["map"] = map
        return out
    return _guard(call, False, hint, run)


@mcp.tool(name="archmap_whatif")
def whatif(map: str, ids: list[str]) -> dict:
    """Preview the metrics of a hypothetical merge of 2+ modules: the merged
    node's fanIn/fanOut/instability/blastRadius/health (computed on a rewritten
    copy of the edge graph — no duplicated math), size-weighted depth/coverage,
    the member edges the merge absorbs, and the external edges it keeps.
    Pure read — the map is never changed; flagging a candidate from a preview
    stays with archmap_suggestions."""
    call = f"archmap_whatif(map='{map}')"
    hint = "Pass ids=[...] with at least two existing module ids."

    def run():
        out = preview_merge(REGISTRY.store(map)._load(), ids or [])
        out["map"] = map
        return out
    return _guard(call, False, hint, run)


# --- Write dispatchers: one action-routed tool per rich resource ------------
# modules / suggestions / grilling / plans / docs collapse the many per-operation
# tools into five action-dispatch tools, keeping the agent's tool surface small
# (≤15 total). The whole-map reads (show_map / get_full_model / get_metrics /
# scan_signals / render_view) and the map lifecycle stay as standalone tools above.
@mcp.tool(name="archmap_modules", **_APP)
def modules(
    map: str,
    action: Literal["add", "update", "delete", "get", "realize"],
    id: str = "",
    label: str | None = None, domain: str | None = None,
    depth: float | None = None, size: float | None = None,
    seam: str | None = None, iface: str | None = None,
    coverage: float | None = None, churn: float | None = None,
    updated: bool | None = None, plane: str | None = None, lifecycle: str | None = None,
    files: list[str] | None = None, dependsOn: list[str] | None = None,
    leaksTo: list[str] | None = None, intendsToDependOn: list[str] | None = None,
    supersedes: list[str] | None = None, tests: str | None = None,
    tags: list[str] | None = None,
    dependsOnAdd: list[str] | None = None, dependsOnRemove: list[str] | None = None,
    leaksToAdd: list[str] | None = None, leaksToRemove: list[str] | None = None,
    items: list[dict] | None = None, ids: list[str] | None = None,
) -> dict:
    """Create / read / update / delete / realize MODULE nodes in `map`, selected by
    `action`. Writes re-render and return the compact ack (it carries
    `unresolvedEdges` when an edge target matches no module — usually a typo);
    get returns the record(s).

      action="add":     create a module — needs id, label, domain (+ optional
                        depth/size/seam/iface/coverage/churn/files/dependsOn/leaksTo/
                        intendsToDependOn/supersedes/tests/tags). Bulk: items=[{...}, ...].
      action="update":  patch module `id` with any field above (depth/coverage/churn
                        0..1, clamped; size is a LOC-ratio where 1.0 == the median
                        module, normally set by archmap_ingest, not clamped; omitted
                        fields unchanged). Edge edits without
                        resending the whole list: dependsOnAdd/dependsOnRemove and
                        leaksToAdd/leaksToRemove merge server-side. Broadcast: pass
                        ids=[...] (or ids=["*"] for every module) to apply ONE shared
                        patch to many modules in a single write. Bulk with per-module
                        fields: items=[{id, ...}].
      action="delete":  delete module `id` and prune its edges. Bulk: ids=[...].
      action="get":     read module `id`'s full record (read-only). Bulk: ids=[...] ->
                        {"modules": [...]}.
      action="realize": flip planned module `id` to built (plane->actual,
                        lifecycle->built); optional depth/coverage/files. (fathom:code)"""
    call = f"archmap_modules(action='{action}'" + (f", id='{id}'" if id else "") + ")"
    hint = ("Check ids with archmap_modules(map, action='get', ids=[...]) or "
            "archmap_show_map(map).")
    return _guard(call, action != "get", hint, lambda: _modules_impl(
        map, action, id, dict(
            label=label, domain=domain, depth=depth, size=size, seam=seam, iface=iface,
            coverage=coverage, churn=churn, updated=updated, plane=plane, lifecycle=lifecycle,
            files=files, dependsOn=dependsOn, leaksTo=leaksTo,
            intendsToDependOn=intendsToDependOn, supersedes=supersedes, tests=tests, tags=tags,
        ),
        dependsOnAdd, dependsOnRemove, leaksToAdd, leaksToRemove,
        items, ids, depth, coverage, files))


def _modules_impl(map: str, action: str, id: str, raw_flds: dict,
                  dependsOnAdd, dependsOnRemove, leaksToAdd, leaksToRemove,
                  items, ids, depth, coverage, files) -> dict:
    store = REGISTRY.ensure(map) if action == "add" else REGISTRY.store(map)
    flds = {k: v for k, v in raw_flds.items() if v is not None}
    edge_ops = (("dependsOn", dependsOnAdd, dependsOnRemove),
                ("leaksTo", leaksToAdd, leaksToRemove))
    has_edge_ops = any(add or rem for _, add, rem in edge_ops)
    if action == "add":
        if items is not None:
            store.add_modules([Module.from_dict(d) for d in items])
        else:
            store.add_module(Module.from_dict({"id": id, **flds}))   # from_dict validates id/label/domain
        return _ack(store)
    if action == "update":
        if items is not None:
            store.update_modules(items)
        else:
            target_ids = ids if ids else ([id] if id else None)
            if not target_ids:
                raise ValueError("modules(action='update') needs id, ids=[...] "
                                 "(or [\"*\"] for all), or items=[{id, ...}]")
            if list(target_ids) == ["*"]:
                target_ids = sorted(store.modules.keys())
            current = {r["id"]: r for r in store.get_modules(target_ids)} if has_edge_ops else {}
            patches = []
            for tid in target_ids:
                p = dict(flds)
                for base, add, rem in edge_ops:
                    if add or rem:
                        cur = list(p.get(base) if base in p else (current[tid].get(base) or []))
                        drop = set(rem or [])
                        merged = [x for x in cur if x not in drop]
                        merged += [x for x in (add or []) if x not in merged]
                        p[base] = merged
                patches.append({"id": tid, **p})
            store.update_modules(patches)            # one locked, all-or-nothing write
        return _ack(store)
    if action == "delete":
        if ids is not None:
            store.delete_modules(ids)
        elif id:
            store.delete_module(id)
        else:
            raise ValueError("modules(action='delete') needs id, or ids=[...]")
        return _ack(store)
    if action == "get":
        if ids is not None:
            return {"map": map, "modules": store.get_modules(ids)}
        if not id:
            raise ValueError("modules(action='get') needs id, or ids=[...]")
        return store.get_module(id)
    if not id:                                                       # realize
        raise ValueError("modules(action='realize') needs id")
    store.realize_module(id, depth, coverage, files)
    return _ack(store)


@mcp.tool(name="archmap_suggestions", **_APP)
def suggestions(
    map: str,
    action: Literal["flag", "decide", "dismiss"],
    module: str = "",
    suggestion_id: str = "",
    title: str = "",
    strength: Literal["Strong", "Worth exploring", "Speculative", ""] = "",
    category: str = "",
    problem: str = "",
    solution: str = "",
    wins: list[str] | None = None,
    decision: Literal["accepted", "deferred", "rejected", ""] = "",
    note: str = "",
) -> dict:
    """Manage deepening SUGGESTIONS (candidates) on a module in `map`, by `action`.
    Re-renders; returns the compact ack.

      action="flag":    attach a new deepening suggestion to `module` — needs title,
                        strength ("Strong"|"Worth exploring"|"Speculative"), category,
                        problem, solution, wins. The suggestion id is derived as
                        f"{module}-{strength}" lower-cased with spaces dashed — pass
                        that id back as `suggestion_id` to decide/dismiss/grilling.
      action="decide":  record a verdict WITH its reason on `suggestion_id`: decision
                        "accepted"|"deferred"|"rejected" (or "" to re-open); `note` is
                        the reason. The candidate is KEPT as the durable record.
      action="dismiss": dismiss `suggestion_id` (status->done) with NO reason — the
                        never-load-bearing case. To keep a reason, use decide instead."""
    call = (f"archmap_suggestions(action='{action}'"
            + (f", module='{module}'" if module else "")
            + (f", suggestion_id='{suggestion_id}'" if suggestion_id else "") + ")")
    hint = "List a module's candidates via archmap_modules(map, action='get', id=<module>)."
    return _guard(call, True, hint, lambda: _suggestions_impl(
        map, action, module, suggestion_id, title, strength, category,
        problem, solution, wins, decision, note))


def _suggestions_impl(map, action, module, suggestion_id, title, strength,
                      category, problem, solution, wins, decision, note) -> dict:
    store = REGISTRY.store(map)
    if action == "flag":
        if not (module and title and strength):
            raise ValueError("suggestions(action='flag') needs module, title, strength")
        sid = f"{module}-{strength}".lower().replace(" ", "-")
        store.add_suggestion(module, Suggestion(sid, title, strength, category,
                                                problem, solution, wins or []))
        return _ack(store)
    if not suggestion_id:
        raise ValueError(f"suggestions(action='{action}') needs suggestion_id")
    if action == "decide":
        store.decide(suggestion_id, decision, note)
    else:                                          # dismiss
        store.resolve(suggestion_id)
    return _ack(store)


@mcp.tool(name="archmap_grilling", **_APP)
def grilling(
    map: str,
    action: Literal["start", "mark", "finish", "queue"],
    module: str = "",
    suggestion_id: str = "",
    decision: Literal["accepted", "deferred", "rejected", ""] = "",
    note: str = "",
    adr: str = "",
):
    """Drive the /deepen GRILLING lifecycle for a candidate in `map`, by `action`.

      action="start":  UI callback — persist `module`'s first open candidate as
                       'requested' and return {map, module, suggestion_id, prompt}
                       where `prompt` is the canonical /deepen prompt.
      action="mark":   mark `suggestion_id` as actively being grilled (status->grilling).
                       Call at the start of the loop; re-renders.
      action="finish": close the loop on `suggestion_id` — mark grilled and record
                       decision ("accepted"|"deferred"|"rejected") + `note` (+ optional
                       `adr` path, e.g. "docs/adr/0007-...md"). Candidate KEPT. Re-renders.
      action="queue":  list candidates a user flagged for grilling that no agent has
                       picked up yet (a terminal /deepen polls this). Read-only."""
    call = (f"archmap_grilling(action='{action}'"
            + (f", module='{module}'" if module else "")
            + (f", suggestion_id='{suggestion_id}'" if suggestion_id else "") + ")")
    hint = "See waiting candidates via archmap_grilling(map, action='queue')."
    return _guard(call, action not in ("queue",), hint, lambda: _grilling_impl(
        map, action, module, suggestion_id, decision, note, adr))


def _grilling_impl(map, action, module, suggestion_id, decision, note, adr):
    store = REGISTRY.store(map)
    if action == "start":
        if not module:
            raise ValueError("grilling(action='start') needs module")
        s = _first_open(store.modules[module])
        if s:
            store.request_grilling(s.id)
        return {"map": map, "module": module,
                "suggestion_id": s.id if s else None,
                "prompt": _grill_prompt(store, map, module)}
    if action == "queue":
        return {"map": map, "queued": store.queued_for_grilling()}
    if not suggestion_id:
        raise ValueError(f"grilling(action='{action}') needs suggestion_id")
    if action == "mark":
        store.mark_grilling(suggestion_id)
    else:                                          # finish
        if not decision:
            raise ValueError("grilling(action='finish') needs decision (accepted|deferred|rejected)")
        store.mark_grilled(suggestion_id)
        store.decide(suggestion_id, decision, note, adr)
    return _ack(store)


@mcp.tool(name="archmap_plans", **_APP)
def plans(
    map: str,
    action: Literal["create", "add_steps", "set_step_status", "update", "get"],
    plan_id: str = "",
    title: str = "",
    domain: str | None = None,
    intent: str | None = None,
    status: Literal["draft", "active", "done", "abandoned", ""] = "",
    moduleIds: list[str] | None = None,
    adrRefs: list[str] | None = None,
    steps: list[dict] | None = None,
    step_id: str = "",
    step_status: Literal["todo", "in-progress", "done", "blocked", ""] = "",
) -> dict:
    """Manage PLANS (intended deep structure) and their work steps in `map`, by `action`.
    Writes re-render and return the compact ack; get returns the plan record.

      action="create":          create plan `plan_id` (needs title; optional domain,
                                 intent, moduleIds). (fathom:plan)
      action="add_steps":       append ordered build steps to `plan_id`: steps=[{id,
                                 title, targets?, interface?, dependsOnSteps?, adapters?,
                                 note?}, ...]. Unknown step keys are REJECTED (not
                                 silently dropped). fathom:code executes steps in order.
      action="set_step_status": set step `step_id` of `plan_id` to step_status
                                 (todo|in-progress|done|blocked).
      action="update":          patch plan `plan_id` (title/domain/intent/status/
                                 moduleIds/adrRefs); status is draft|active|done|abandoned.
      action="get":             read plan `plan_id`'s full record (read-only)."""
    call = f"archmap_plans(action='{action}'" + (f", plan_id='{plan_id}'" if plan_id else "") + ")"
    hint = "Read the plan via archmap_plans(map, action='get', plan_id=...)."
    return _guard(call, action != "get", hint, lambda: _plans_impl(
        map, action, plan_id, title, domain, intent, status,
        moduleIds, adrRefs, steps, step_id, step_status))


def _plans_impl(map, action, plan_id, title, domain, intent, status,
                moduleIds, adrRefs, steps, step_id, step_status) -> dict:
    store = REGISTRY.ensure(map) if action == "create" else REGISTRY.store(map)
    if action == "create":
        store.create_plan(Plan(id=plan_id, title=title, domain=domain or "",
                               intent=intent or "", moduleIds=moduleIds or []))
        return _ack(store)
    if action == "add_steps":
        bad = [f"step {s.get('id') or '#' + str(i)}: {sorted(set(s) - _WS_FIELDS)}"
               for i, s in enumerate(steps or []) if set(s) - _WS_FIELDS]
        if bad:
            raise ValueError("unknown WorkStep key(s) — " + "; ".join(bad)
                             + f". Valid keys: {sorted(_WS_FIELDS)}")
        store.add_work_steps(plan_id, [WorkStep(**s) for s in (steps or [])])
        return _ack(store)
    if action == "set_step_status":
        store.set_step_status(plan_id, step_id, step_status)
        return _ack(store)
    if action == "update":
        ch = {k: v for k, v in dict(title=(title or None), domain=domain, intent=intent,
                                    status=(status or None), moduleIds=moduleIds,
                                    adrRefs=adrRefs).items() if v is not None}
        store.update_plan(plan_id, **ch)
        return _ack(store)
    return store.get_plan(plan_id)                 # get


def _scope_from_args(scope_kind: str, scope_ids, scope_domain: str,
                     query_domain: str, query_plane: str, query_lifecycle: str,
                     query_depth_gte, query_depth_lte, query_coverage_lte,
                     query_has_leak, query_has_open_candidate, query_tag: str) -> dict | None:
    """Assemble a model Scope dict from the flat tool args; None when no scope arg
    was provided at all (so update leaves the stored scope unchanged)."""
    predicate = {k: v for k, v in {
        "domain": query_domain or None, "plane": query_plane or None,
        "lifecycle": query_lifecycle or None,
        "depthGte": query_depth_gte, "depthLte": query_depth_lte,
        "coverageLte": query_coverage_lte,
        "hasLeak": query_has_leak, "hasOpenCandidate": query_has_open_candidate,
        "tag": query_tag or None,
    }.items() if v is not None}
    if not (scope_kind or scope_ids or scope_domain or predicate):
        return None
    kind = scope_kind or ("explicit" if scope_ids else "domain" if scope_domain else "query")
    if kind == "explicit":
        return {"kind": "explicit", "ids": scope_ids or []}
    if kind == "domain":
        return {"kind": "domain", "domain": scope_domain}
    if kind == "query":
        return {"kind": "query", "predicate": predicate}
    return {"kind": "system"}


@mcp.tool(name="archmap_docs", **_APP)
def docs(
    map: str,
    action: Literal["add", "update", "delete", "list", "get"],
    doc_id: str = "",
    type: Literal["adr", "note", "rule", "rfc", "glossary", ""] = "",
    title: str | None = None,
    summary: str | None = None,
    body: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
    supersedes: list[str] | None = None,
    adrRef: str | None = None,
    author: str | None = None,
    created: str | None = None,
    updated: str | None = None,
    scope_kind: Literal["system", "explicit", "domain", "query", ""] = "",
    scope_ids: list[str] | None = None,
    scope_domain: str = "",
    query_domain: str = "",
    query_plane: str = "",
    query_lifecycle: str = "",
    query_depth_gte: float | None = None,
    query_depth_lte: float | None = None,
    query_coverage_lte: float | None = None,
    query_has_leak: bool | None = None,
    query_has_open_candidate: bool | None = None,
    query_tag: str = "",
    include_membership: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Manage scoped architecture DOCS in `map`, by `action`. Writes re-render.

      action="add":    create doc `doc_id` — needs type (adr|note|rule|rfc|glossary)
                       and title; optional summary, body, status, tags, supersedes,
                       adrRef, author, and a scope (below; defaults to whole-system).
      action="update": patch doc `doc_id` (any field above; omitted unchanged).
      action="delete": delete doc `doc_id`.
      action="list":   list doc SUMMARIES (id/type/title/summary/status/tags/author/
                       scopeLabel/drift/moduleCount — no bodies), paged via limit/
                       offset. Pass include_membership=True for the moduleId->docIds
                       map. Full body via action="get". Read-only.
      action="get":    read doc `doc_id`'s full record with scope resolved. Read-only.

    Scope is given flat: scope_kind="system" (everything) | "explicit" + scope_ids
    | "domain" + scope_domain | "query" + any query_* filters (query_domain/
    query_plane/query_lifecycle/query_depth_gte/query_depth_lte/query_coverage_lte/
    query_has_leak/query_has_open_candidate/query_tag, ANDed). scope_kind may be
    omitted when scope_ids or scope_domain or a query_* filter makes it obvious."""
    call = f"archmap_docs(action='{action}'" + (f", doc_id='{doc_id}'" if doc_id else "") + ")"
    hint = "List existing docs via archmap_docs(map, action='list')."
    scope = _scope_from_args(scope_kind, scope_ids, scope_domain,
                             query_domain, query_plane, query_lifecycle,
                             query_depth_gte, query_depth_lte, query_coverage_lte,
                             query_has_leak, query_has_open_candidate, query_tag)
    return _guard(call, action in ("add", "update", "delete"), hint, lambda: _docs_impl(
        map, action, doc_id, type, title, scope, summary, body, status, tags,
        supersedes, adrRef, author, created, updated, include_membership, limit, offset))


_DOC_SUMMARY_KEYS = ("id", "type", "title", "summary", "status", "tags",
                     "author", "scopeLabel", "drift")


def _docs_impl(map, action, doc_id, type, title, scope, summary, body, status, tags,
               supersedes, adrRef, author, created, updated,
               include_membership, limit, offset) -> dict:
    store = REGISTRY.ensure(map) if action == "add" else REGISTRY.store(map)
    if action == "add":
        if not (doc_id and type and title):
            raise ValueError("docs(action='add') needs doc_id, type, title")
        _apply_doc(store, "add", {"doc": {
            "id": doc_id, "type": type, "title": title,
            "scope": scope or {"kind": "system"},
            "summary": summary or "", "body": body or "", "status": status or "",
            "tags": tags or [], "supersedes": supersedes or [],
            "adrRef": adrRef or "", "author": author or "",
        }})
        return _ack(store, changed=f"added doc {doc_id}")
    if action == "update":
        ch = {k: v for k, v in dict(
            type=(type or None), title=title, scope=scope, summary=summary, body=body,
            status=status, tags=tags, supersedes=supersedes, adrRef=adrRef,
            author=author, created=created, updated=updated,
        ).items() if v is not None}
        _apply_doc(store, "update", {"doc_id": doc_id, "fields": ch})
        return _ack(store, changed=f"updated doc {doc_id}")
    if action == "delete":
        _apply_doc(store, "delete", {"doc_id": doc_id})
        return _ack(store, changed=f"deleted doc {doc_id}")
    if action == "list":
        d = store.to_dict()
        slim = [{**{k: doc.get(k) for k in _DOC_SUMMARY_KEYS},
                 "moduleCount": len(doc.get("resolvedModuleIds") or [])}
                for doc in d["docs"]]
        page = slim[offset:offset + limit]
        out = {"map": map, "docs": page,
               "total_count": len(slim),
               "has_more": offset + limit < len(slim),
               "next_offset": offset + limit if offset + limit < len(slim) else None}
        if include_membership:
            out["docMembership"] = d["docMembership"]
        return out
    return store.get_doc(doc_id)                   # get


_WS_FIELDS = {f.name for f in fields(WorkStep)}

CANON_GRILL_PROMPT = (
    "Enter the /deepen grilling loop for {head} (map '{map}', module '{module}'"
    "{sid}, depth {depth:.2f}, coverage {cov:.0%}). Call grilling(action='mark') as you "
    "begin, then grilling(action='finish', decision=accepted|deferred|rejected, note, adr) "
    "to close it; "
    "offer an ADR on a load-bearing rejection."
)


def _first_open(m: Module):
    """The module's first still-open candidate (undecided, not closed), or None."""
    return next((s for s in m.suggestions if s.decision == "" and s.status != "done"), None)


def _grill_prompt(store: Store, map: str, module: str) -> str:
    m = store.modules[module]
    s = _first_open(m)
    head = s.title if s else f"the {m.label} module"
    sid = f", suggestion '{s.id}'" if s else ""
    return CANON_GRILL_PROMPT.format(head=head, map=map, module=module, sid=sid,
                                     depth=m.depth, cov=m.coverage)


# --- Plans + work steps (fathom:plan creates; fathom:code executes) ----------


# --- Docs: scoped architecture documents (doc-tools) ------------------------
# ONE dispatch helper for every doc mutation, called by BOTH the @mcp.tool
# functions below AND the /api/docs route — so docs are the first citizen of the
# unified-dispatch shape the open `http-backend-strong` candidate proposes, NOT a
# fourth copy of the legacy triple-dispatch (_apply_action / _call_tool / tools).
def _apply_doc(store: Store, action: str, body: dict) -> None:
    if action == "add":
        store.add_doc(Doc.from_dict(body["doc"]))
    elif action == "update":
        store.update_doc(body["doc_id"], **body.get("fields", {}))
    elif action == "delete":
        store.delete_doc(body["doc_id"])
    else:
        raise ValueError(f"unknown doc action '{action}'")


# --- HTTP studio app (browser UI -> saved back to the server) ---------------
# The studio (ui/studio/) is served from the same FastMCP app, so the page is
# same-origin with /api/maps + /api/model + /api/act (no CORS). The studio picks a
# map (?map=<id>, switchable in the header), GETs /api/model?map=, and POSTs every
# triage/edit to /api/act with the map in the body — mutating maps/<id>.json under
# a lock. It polls /api/model every 2.5s so changes from the agent/desktop/other
# tabs converge. Launch with `python -m arch_map.web`.
def _apply_action(store: Store, action: str, body: dict) -> None:
    if action == "decide":
        store.decide(body["suggestion_id"], body["decision"], body.get("note", ""),
                     body.get("adr", ""), body.get("expect"))
    elif action == "resolve":
        store.resolve(body["suggestion_id"])
    elif action == "request_grilling":
        store.request_grilling(body["suggestion_id"])
    elif action == "set_step_status":
        store.set_step_status(body["plan_id"], body["step_id"], body["status"])
    elif action == "update_plan":
        store.update_plan(body["plan_id"], **body.get("fields", {}))
    elif action == "set_depth":
        store.set_depth(body["module"], float(body["score"]))
    elif action == "set_coverage":
        store.set_coverage(body["module"], float(body["fraction"]))
    elif action == "update":
        store.update_module(body["module"], **body.get("fields", {}))
    elif action == "add":
        store.add_module(Module.from_dict(body["module"]))
    elif action == "delete":
        store.delete_module(body["module"])
    elif action == "flag":
        # the studio's what-if card flags ONE candidate through the existing FSM;
        # grilling and deciding stay with fathom:deepen
        s = body.get("suggestion") or {}
        if not (body.get("module") and s.get("title") and s.get("strength")):
            raise ValueError("flag needs module and suggestion {title, strength}")
        sid = f"{body['module']}-{s['strength']}".lower().replace(" ", "-")
        store.add_suggestion(body["module"], Suggestion(
            sid, s["title"], s["strength"], s.get("category", ""),
            s.get("problem", ""), s.get("solution", ""), s.get("wins") or []))
    else:
        raise ValueError(f"unknown action '{action}'")


@mcp.custom_route("/", ["GET"])
async def studio_page(request):
    """The unified studio — the primary browser UI."""
    return HTMLResponse(STUDIO_INDEX.read_text(encoding="utf-8"))


@mcp.custom_route("/assets/{path:path}", ["GET"])
async def studio_asset(request):
    """Serve the studio's CSS/JS bundle (index.html references /assets/...)."""
    target = (STUDIO_DIR / request.path_params["path"]).resolve()
    # contain reads to the studio dir — refuse path traversal
    if STUDIO_DIR not in target.parents or not target.is_file():
        return Response("not found", status_code=404)
    ct = _ASSET_CT.get(target.suffix, "application/octet-stream")
    return Response(target.read_text(encoding="utf-8"), media_type=ct)


@mcp.custom_route("/api/maps", ["GET", "POST"])
async def api_maps(request):
    """GET -> the list of maps (for the switcher). POST {op:create|delete,...} ->
    create/delete a map, returning the refreshed list."""
    if request.method == "GET":
        return JSONResponse({"maps": REGISTRY.list(), "default": REGISTRY.default_id()})
    body = await request.json()
    op = body.get("op", "")
    try:
        created = None
        if op == "create":
            mid = _slug(body.get("map", ""))
            if not body.get("map"):
                raise ValueError("a map name is required")
            REGISTRY.create(mid, body.get("repo") or body.get("map") or mid)
            created = mid
        elif op == "delete":
            REGISTRY.delete(body["map"])
        elif op == "rename":
            new_id = _slug(body.get("to") or body.get("map"))
            REGISTRY.rename(body["map"], new_id, body.get("repo") or body.get("to"))
            created = new_id
        else:
            raise ValueError(f"unknown op '{op}'")
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"maps": REGISTRY.list(), "default": REGISTRY.default_id(), "created": created})


@mcp.custom_route("/api/model", ["GET"])
async def api_model(request):
    try:
        store = REGISTRY.resolve(request.query_params.get("map"))
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return JSONResponse(store.to_dict())


@mcp.custom_route("/api/docs", ["GET", "POST"])
async def api_docs(request):
    """GET -> the map's docs with resolved scope (the same projection to_dict bakes).
    POST {op:add|update|delete,...} -> mutate via the SAME _apply_doc the @mcp.tool
    functions use (one dispatch, two surfaces), returning the refreshed full model."""
    if request.method == "GET":
        try:
            store = REGISTRY.resolve(request.query_params.get("map"))
        except (KeyError, ValueError) as e:
            return JSONResponse({"error": str(e)}, status_code=404)
        d = store.to_dict()
        return JSONResponse({"docs": d["docs"], "docMembership": d["docMembership"]})
    body = await request.json()
    try:
        store = REGISTRY.resolve(body.get("map"))
        _apply_doc(store, body.get("op", ""), body)
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(store.to_dict())


@mcp.custom_route("/view", ["GET"])
async def view_page(request):
    """Browser view of an ad-hoc table/chart, e.g. /view?map=…&kind=bar&metric=coverage&groupBy=domain."""
    return HTMLResponse(VIEW_INDEX.read_text(encoding="utf-8"))


@mcp.custom_route("/api/view", ["GET"])
async def api_view(request):
    """Shape a map into a prepared view payload (same logic render_view uses)."""
    q = request.query_params
    spec = {"kind": q.get("kind"), "of": q.get("of") or q.get("filter"), "title": q.get("title"),
            "metric": q.get("metric"), "groupBy": q.get("groupBy") or q.get("group"), "agg": q.get("agg"),
            "sortBy": q.get("sortBy") or q.get("sort"), "sortDir": q.get("sortDir")}
    if q.get("columns"):
        spec["columns"] = [c.strip() for c in q["columns"].split(",") if c.strip()]
    spec = {k: v for k, v in spec.items() if v is not None}
    try:
        store = REGISTRY.resolve(q.get("map"))
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    try:
        parsed = _parse_view_spec(spec)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(_build_view(store.to_dict(), parsed))


@mcp.custom_route("/api/whatif", ["GET"])
async def api_whatif(request):
    """Browser side of archmap_whatif: /api/whatif?map=<id>&ids=a,b,c."""
    q = request.query_params
    ids = [s for s in (q.get("ids") or "").split(",") if s]
    try:
        store = REGISTRY.resolve(q.get("map"))
        out = preview_merge(store._load(), ids)
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(out)


@mcp.custom_route("/api/act", ["POST"])
async def api_act(request):
    body = await request.json()
    try:
        store = REGISTRY.resolve(body.get("map"))
        _apply_action(store, body.get("action", ""), body)
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(store.to_dict())  # Store auto-saves on each write


@mcp.custom_route("/api/grill", ["POST"])
async def api_grill(request):
    """Browser grill hand-off. A browser CANNOT trigger an agent turn, so this only
    (a) persists the candidate as 'requested' and (b) returns the canonical /deepen
    prompt + a 'resume <map>' line for the user to paste into their agent."""
    body = await request.json()
    map_id = body.get("map") or REGISTRY.default_id()
    try:
        store = REGISTRY.resolve(body.get("map"))
        module = body["module"]
        s = _first_open(store.modules[module])
        if s:
            store.request_grilling(s.id)
        prompt = _grill_prompt(store, map_id, module)
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "prompt": prompt,
                         "resume": f"/deepen resume {map_id}",
                         "model": store.to_dict()})


# --- /api/dispatch: run a studio agent-button action via headless `claude -p` ---
# OFF by default — set ARCH_MAP_ALLOW_DISPATCH=1 to enable. Loopback only. When
# disabled / no `claude` on PATH it returns 503 {fallback:true,...} so the browser
# keeps its existing copy-paste path (no regression). The spawned agent reaches the
# SAME arch-map MCP over http://127.0.0.1:<PORT>/mcp, so its writes land in the store
# the studio already polls; source edits land in the working tree for human review.
_DISPATCH_RUNNING: set = set()        # (map, kind, module) -> single-writer guard
_DISPATCH_TOOLS = {                    # per-kind tool allowlist; only fix/realize edit
    "fix":     "Read,Edit,Bash(git *),mcp__arch-map__*",
    "realize": "Read,Edit,Bash(git *),mcp__arch-map__*",
    "grill":   "Read,mcp__arch-map__*",
    "rescan":  "Read,mcp__arch-map__*",
    "triage":  "Read,mcp__arch-map__*",
}


def _dispatch_prompt(store: Store, map_id: str, kind: str, module: str = "",
                     modules: list | None = None, suggestion_id: str = "") -> str:
    """The per-kind agent instruction — mirrors the studio's client-side dispatchPrompt
    so host and browser send identical wording."""
    m = store.modules.get(module) if module else None
    if kind == "fix":
        s = _first_open(m) if m else None
        lines = [f"Fix module '{module}'" + (f" ({m.label}, domain '{m.domain}')" if m else "") + "."]
        if s and getattr(s, "problem", ""):
            lines.append("Why: " + s.problem)
        if s and getattr(s, "solution", ""):
            lines.append("How: " + s.solution)
        return "\n".join(lines)
    if kind == "rescan":
        return f"Re-scan module '{module}' for fresh signals."
    if kind == "realize":
        return f"Realize planned module '{module}' — build it to its intended interface."
    if kind == "triage":
        ids = ", ".join(modules or [])
        return "Triage the top critical modules: " + (ids or "(none)") + "."
    if kind == "grill":
        return _grill_prompt(store, map_id, module)
    return f"Agent request ({kind})" + (f" for module '{module}'" if module else "") + "."


def _dispatch_line(line: str) -> str:
    """Condense one stream-json event into a short human progress line (or '')."""
    try:
        ev = json.loads(line)
    except ValueError:
        return ""
    t = ev.get("type")
    if t == "system" and ev.get("subtype") == "init":
        return "agent started"
    if t == "assistant":
        for b in (ev.get("message", {}).get("content") or []):
            if b.get("type") == "tool_use":
                inp = b.get("input") or {}
                target = inp.get("file_path") or inp.get("command") or inp.get("id") or inp.get("pattern") or ""
                return (f"{b.get('name', 'tool')} {target}").strip()
            if b.get("type") == "text" and (b.get("text") or "").strip():
                return b["text"].strip()[:140]
    if t == "result":
        return "finished"
    return ""


@mcp.custom_route("/api/dispatch", ["POST"])
async def api_dispatch(request):
    """Run a studio agent-button action by spawning headless `claude -p` in the repo
    with the arch-map MCP attached, streaming progress back as SSE. OFF unless
    ARCH_MAP_ALLOW_DISPATCH is set; degrades to 503 {fallback} so the browser keeps
    its copy-paste path."""
    body = await request.json()
    map_id = body.get("map") or REGISTRY.default_id()
    kind = body.get("kind", "")
    module = body.get("module", "")
    modules = body.get("modules") or []
    sid = body.get("suggestion_id", "")
    try:
        store = REGISTRY.resolve(body.get("map"))
        prompt = _dispatch_prompt(store, map_id, kind, module, modules, sid)
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    if not os.environ.get("ARCH_MAP_ALLOW_DISPATCH"):
        return JSONResponse({"fallback": True, "reason": "dispatch-disabled", "prompt": prompt}, status_code=503)
    claude = shutil.which("claude")
    if not claude:
        return JSONResponse({"fallback": True, "reason": "no-agent-binary", "prompt": prompt}, status_code=503)

    # best-effort instant feedback, mirroring the MCP-App host pre-calls
    try:
        if kind == "rescan" and module:
            store.update_module(module, updated=False)
        elif kind == "grill" and module:
            s = _first_open(store.modules[module])
            if s:
                store.request_grilling(s.id)
    except (KeyError, ValueError):
        pass

    key = (map_id, kind, module)
    if key in _DISPATCH_RUNNING:
        return JSONResponse({"error": "already-running", "kind": kind, "module": module}, status_code=409)

    port = os.environ.get("ARCH_MAP_PORT", "8800")
    mcp_cfg = json.dumps({"mcpServers": {"arch-map": {"type": "http", "url": f"http://127.0.0.1:{port}/mcp"}}})
    argv = [
        claude, "-p", prompt,
        "--add-dir", os.getcwd(),
        "--permission-mode", "acceptEdits",
        "--allowedTools", _DISPATCH_TOOLS.get(kind, "Read,mcp__arch-map__*"),
        "--disallowedTools", "Bash(rm *),Bash(git push *),WebFetch,WebSearch",
        "--mcp-config", mcp_cfg,
        "--output-format", "stream-json", "--verbose",
        "--append-system-prompt",
        ("You are running headless from an arch-map studio button. Make the smallest "
         "change that satisfies the request, then reconcile the modules you touched on "
         "the arch-map spine via the arch-map MCP tools. Do not commit, push, or touch "
         "files outside the repo."),
    ]

    async def stream():
        def sse(event, data):
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"
        _DISPATCH_RUNNING.add(key)
        yield sse("start", {"kind": kind, "module": module, "prompt": prompt})
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, cwd=os.getcwd(),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)
            async for raw in proc.stdout:
                msg = _dispatch_line(raw.decode("utf-8", "replace").strip())
                if msg:
                    yield sse("progress", {"text": msg})
            await proc.wait()
            yield sse("done", {"ok": proc.returncode == 0, "code": proc.returncode})
        except Exception as e:                      # noqa: BLE001 — surface, never crash the server
            yield sse("error", {"error": str(e)})
        finally:
            _DISPATCH_RUNNING.discard(key)

    return StreamingResponse(stream(), media_type="text/event-stream")


# The graph UI (network.html) calls tools by their MCP name; dispatch them here
# so the same page works both as an MCP App (desktop) and served over HTTP.
def _call_tool(store: Store, name: str, a: dict) -> None:
    if name == "set_depth":
        store.set_depth(a["module"], float(a["score"]))
    elif name == "set_coverage":
        store.set_coverage(a["module"], float(a["fraction"]))
    elif name == "update_module":
        store.update_module(a["module"], **a.get("fields", {}))
    elif name == "delete_module":
        store.delete_module(a["module"])
    elif name == "add_module":
        store.add_module(Module.from_dict(a))
    elif name == "resolve":
        store.resolve(a["suggestion_id"])
    elif name == "decide":
        store.decide(a["suggestion_id"], a["decision"], a.get("note", ""), a.get("adr", ""))
    elif name == "request_grilling":
        store.request_grilling(a["suggestion_id"])
    elif name == "mark_grilled":
        store.mark_grilled(a["suggestion_id"])
    elif name == "start_grilling":
        # A browser can't trigger an agent turn — but it CAN persist the request so
        # a terminal /deepen (or an MCP-App host's sendMessage) picks it up.
        s = _first_open(store.modules[a["module"]]) if a.get("module") else None
        if s:
            store.request_grilling(s.id)
    else:
        raise ValueError(f"unknown tool '{name}'")


@mcp.custom_route("/map", ["GET"])
async def map_page(request):
    # back-compat alias: the standalone /map graph is now part of the studio
    return HTMLResponse(STUDIO_INDEX.read_text(encoding="utf-8"))


@mcp.custom_route("/api/tool", ["POST"])
async def api_tool(request):
    body = await request.json()
    try:
        store = REGISTRY.resolve(body.get("map") or (body.get("arguments") or {}).get("map"))
        _call_tool(store, body.get("name", ""), body.get("arguments", {}))
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(store.to_dict())


def main() -> None:
    mcp.run()


if __name__ == "__main__":  # pragma: no cover — would start a live stdio server
    main()
