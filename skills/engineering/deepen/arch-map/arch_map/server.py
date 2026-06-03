"""arch-map FastMCP server (hybrid UI).

Two rendering lanes, per the explored design:

  Lane 1 — the bespoke *studio* (ui://arch/network.html), inlined from ui/studio/.
           Tools link to it via AppConfig and stream the model into it
           (show_map/get_model -> app.ontoolresult); the studio routes edits back
           via app.callServerTool (set_depth/add_module/decide/resolve/...). The
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

from dataclasses import fields
import fcntl
import json
import re

from fastmcp import FastMCP
from starlette.responses import HTMLResponse, JSONResponse, Response

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

from .model import ArchModel, Module, Suggestion, Plan, WorkStep

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
    def queued_for_grilling(self): return self._load().queued_for_grilling()
    @property
    def modules(self): return self._load().modules
    @property
    def plans(self): return self._load().plans

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
            raise KeyError(f"no map '{map_id}' (create it with create_map)")
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
            "https://cdnjs.cloudflare.com",   # dagre (graph layout)
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
    and drives everything through tools instead of /api. The dagre + ext-apps CDN
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
    sandboxed iframe and drives it through the tools: show_map names the map,
    get_model feeds the full model, and set_depth / add_module / decide / resolve /
    … mutate it — every change re-rendered with the studio's own components."""
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


def _build_view(model: dict, spec: dict) -> dict:
    """Turn a {kind, of, ...} spec + a full model into a prepared view payload the
    renderer draws verbatim (numbers already scaled to 0..100 for display)."""
    kind = (spec.get("kind") or "table").lower()
    of = spec.get("of") or spec.get("filter") or "all"
    sel = _view_filter(model.get("modules", []), of, model)
    label = "all modules" if str(of).lower() in ("", "all") else of
    out = {"kind": kind, "title": spec.get("title") or f"{kind} · {label}",
           "repo": model.get("repo", ""), "count": len(sel)}

    if kind == "bar":
        metric = (spec.get("metric") or "depth").lower()        # depth | coverage
        group = (spec.get("groupBy") or spec.get("group") or "module").lower()
        out["metric"], out["groupBy"] = metric, group
        if group == "domain":
            agg = spec.get("agg") or "avg"                       # avg | count
            buckets: dict[str, list[float]] = {}
            for m in sel:
                buckets.setdefault(m.get("domain", "—"), []).append(m.get(metric) or 0)
            if agg == "count":
                mx = max((len(v) for v in buckets.values()), default=1) or 1
                bars = [{"label": d, "value": str(len(v)), "pct": round(len(v) / mx * 100)} for d, v in buckets.items()]
            else:
                bars = [{"label": d, "value": f"{round(sum(v) / len(v) * 100)}%", "pct": round(sum(v) / len(v) * 100)} for d, v in buckets.items()]
        else:
            bars = [{"label": m["id"], "value": f"{round((m.get(metric) or 0) * 100)}%", "pct": round((m.get(metric) or 0) * 100)} for m in sel]
        bars.sort(key=lambda b: b["pct"], reverse=True)
        out["bars"] = bars
    else:                                                        # table (default)
        cols = [c for c in (spec.get("columns") or ["id", "domain", "depth", "coverage"]) if c in _VIEW_COLS]
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
                elif c == "tests": row[c] = "✓" if (m.get("tests") or "").strip() else ""
                else: row[c] = m.get(c)
            rows.append(row)
        sby = spec.get("sortBy") or spec.get("sort")
        sdir = spec.get("sortDir", "asc")
        if isinstance(sby, dict): sdir, sby = sby.get("dir", "asc"), sby.get("by")
        if sby in cols:
            rows.sort(key=lambda r: (r.get(sby) is None, r.get(sby)), reverse=(sdir == "desc"))
        out["columns"], out["rows"] = cols, rows
    return out


# --- Tools the project-agent drives. Every tool takes `map` — the named map it
# operates on (one per project). Mutations return a compact ack — the full model
# is too big for an agent's context (the browser UIs fetch it from /api/model and
# the graph polls). show_map returns the lightweight view.
def _ack(store: Store, changed: str | None = None) -> dict:
    v = store.to_view()
    return {"ok": True, "changed": changed, "repo": v["repo"], "modules": len(v["modules"]),
            "orphans": v["orphans"], "openSuggestions": v["openSuggestions"]}


@mcp.tool
def list_maps() -> dict:
    """List the available architecture maps (id, repo label, module/proposal counts).
    Maps are shared — any agent can read or write any of them; pass the id as `map`."""
    return {"maps": REGISTRY.list(), "default": REGISTRY.default_id()}


@mcp.tool(**_APP)
def create_project(name: str) -> dict:
    """Create a new project and open its (empty) architecture map. `name` is the
    human project name (e.g. "Mr. Meeseeks"); it becomes the display label and is
    slugged to the map id (e.g. "mr-meeseeks"). Returns that id as `map` — pass it
    to add_module/add_modules/flag_deepening to populate the project. Projects are
    shared: any agent can read or write this one.

    This is the friendly front door for create_map (which takes an explicit id)."""
    mid = _slug(name)
    ack = _ack(REGISTRY.create(mid, name or mid), changed=f"created project {mid}")
    ack["map"] = mid          # the id to pass to subsequent tool calls
    return ack


@mcp.tool(**_APP)
def create_map(map: str, repo: str = "") -> dict:
    """Create a new named, empty map (typically one per project) and render it.
    `map` is the id (lowercase a-z, 0-9, . _ -); `repo` is the display label.
    Prefer create_project(name) unless you need to set the id explicitly."""
    return _ack(REGISTRY.create(map, repo), changed=f"created map {map}")


@mcp.tool(**_APP)
def rename_map(map: str, to: str, repo: str = "") -> dict:
    """Rename a map. `map` is the current id, `to` the new id, `repo` the new
    display label (defaults to `to` if blank). Use to point a map at a real
    project, e.g. rename_map("arch-map", "mr-meeseeks", "Mr. Meeseeks")."""
    new_id = _slug(to)
    return _ack(REGISTRY.rename(map, new_id, repo or to), changed=f"renamed {map} -> {new_id}")


@mcp.tool
def delete_map(map: str) -> dict:
    """Delete an entire named map and its file."""
    REGISTRY.delete(map)
    return {"ok": True, "deleted": map, "maps": [m["id"] for m in REGISTRY.list()]}


@mcp.tool(**_APP)
def show_map(map: str) -> dict:
    """Render a map's architecture network graph (lightweight view). Creates the
    map empty if it doesn't exist yet. Inside an MCP-App host this drives the
    inline studio: the result tells the studio which `map` to render, and it then
    pulls the full model via get_model."""
    v = REGISTRY.ensure(map).to_view()
    v["map"] = map
    return v


@mcp.tool(**_APP)
def get_model(map: str) -> dict:
    """Return a map's FULL model — every module's interface, files, tests, and
    suggestion bodies — which is what the inline studio renders. Heavier than
    show_map (which is the lightweight agent view), so the studio calls this once
    it knows the map and after each edit; agents normally use show_map."""
    v = REGISTRY.ensure(map).to_dict()
    v["map"] = map
    return v


@mcp.tool(**_VIEW_APP)
def render_view(map: str, spec: dict) -> dict:
    """Render an on-brand ad-hoc VIEW of a map — a table or bar chart drawn with the
    studio's own design (not generic widgets). `spec` is declarative:

      kind:    "table" (default) | "bar"
      of:      which modules — "all" | "orphans" | "leaks" | "suggestions" |
               "updated" | "low-coverage" | "shallow" | "mid" | "deep" | <domain>
      title:   optional heading
      table:   columns=[id,label,domain,depth,coverage,tests,files,suggestion],
               sortBy=<column>, sortDir="asc"|"desc"
      bar:     metric="depth"|"coverage", groupBy="module"|"domain", agg="avg"|"count"

    e.g. render_view(map, {"kind":"table","of":"low-coverage","columns":["id","domain","coverage"],"sortBy":"coverage","sortDir":"asc"})
         render_view(map, {"kind":"bar","metric":"coverage","groupBy":"domain","agg":"avg"})"""
    payload = _build_view(REGISTRY.store(map).to_dict(), spec or {})
    payload["map"] = map
    return payload


@mcp.tool(**_APP)
def flag_deepening(
    map: str,
    module: str,
    title: str,
    strength: str,
    category: str,
    problem: str,
    solution: str,
    wins: list[str],
) -> dict:
    """Attach a deepening suggestion to a module in `map` and re-render.

    strength: "Strong" | "Worth exploring" | "Speculative".
    category: the dependency category at the seam (in-process, ports & adapters, ...).
    """
    sid = f"{module}-{strength}".lower().replace(" ", "-")
    store = REGISTRY.store(map)
    store.add_suggestion(module, Suggestion(sid, title, strength, category, problem, solution, wins))
    return _ack(store)


@mcp.tool(**_APP)
def set_depth(map: str, module: str, score: float) -> dict:
    """Set a module's depth score (0 = shallow, 1 = deep) in `map` and re-render."""
    store = REGISTRY.store(map)
    store.set_depth(module, score)
    return _ack(store)


@mcp.tool(**_APP)
def set_coverage(map: str, module: str, fraction: float) -> dict:
    """Set a module's interface test coverage (0..1) in `map` and re-render."""
    store = REGISTRY.store(map)
    store.set_coverage(module, fraction)
    return _ack(store)


@mcp.tool(**_APP)
def mark_updated(map: str, module: str, updated: bool = True) -> dict:
    """Flag a module as changed since the last scan (drives the 'updated' halo)."""
    store = REGISTRY.store(map)
    store.mark_updated(module, updated)
    return _ack(store)


@mcp.tool(**_APP)
def resolve(map: str, suggestion_id: str) -> dict:
    """Dismiss a suggestion in `map` (e.g. after grilling rejects it) and re-render."""
    store = REGISTRY.store(map)
    store.resolve(suggestion_id)
    return _ack(store)


@mcp.tool(**_APP)
def decide(map: str, suggestion_id: str, decision: str, note: str = "") -> dict:
    """Record a decision on a suggestion in `map` and re-render. decision is
    "accepted" | "deferred" | "rejected" (or "" to re-open). The studio's
    Accept / Defer / Reject buttons call this; Dismiss calls resolve()."""
    store = REGISTRY.store(map)
    store.decide(suggestion_id, decision, note)
    return _ack(store)


# --- Module CRUD ------------------------------------------------------------
@mcp.tool(**_APP)
def add_module(
    map: str,
    id: str,
    label: str,
    domain: str,
    depth: float = 0.5,
    size: float = 1.0,
    seam: str = "",
    iface: str = "",
    coverage: float = 0.0,
    files: list[str] | None = None,
    dependsOn: list[str] | None = None,
    leaksTo: list[str] | None = None,
    tests: str = "",
) -> dict:
    """Create a module node in `map` and re-render (creates the map if new).
    depth 0=shallow..1=deep; domain groups it."""
    store = REGISTRY.ensure(map)
    store.add_module(Module(
        id=id, label=label, domain=domain, depth=depth, size=size, seam=seam,
        iface=iface, coverage=coverage, files=files or [],
        dependsOn=dependsOn or [], leaksTo=leaksTo or [], tests=tests,
    ))
    return _ack(store)


@mcp.tool
def get_module(map: str, module: str) -> dict:
    """Read one module's full record from `map` (read-only; does not redraw)."""
    return REGISTRY.store(map).get_module(module)


@mcp.tool(**_APP)
def update_module(map: str, module: str, fields: dict) -> dict:
    """Patch a module in `map` and re-render. Editable: label, domain, depth, size,
    seam, iface, coverage, updated, files, dependsOn, leaksTo, tests.
    (Suggestions are managed via flag_deepening / resolve.)"""
    store = REGISTRY.store(map)
    store.update_module(module, **fields)
    return _ack(store)


@mcp.tool(**_APP)
def delete_module(map: str, module: str) -> dict:
    """Delete a module from `map` and prune edges that referenced it, then re-render."""
    store = REGISTRY.store(map)
    store.delete_module(module)
    return _ack(store)


# --- Bulk CRUD --------------------------------------------------------------
@mcp.tool(**_APP)
def add_modules(map: str, modules: list[dict]) -> dict:
    """Bulk-create modules in `map` and re-render (creates the map if new). Each
    dict needs id/label/domain; depth/size/seam/iface/coverage/files/dependsOn/
    leaksTo/tests are optional."""
    store = REGISTRY.ensure(map)
    store.add_modules([Module.from_dict(d) for d in modules])
    return _ack(store)


@mcp.tool
def get_modules(map: str, modules: list[str]) -> dict:
    """Bulk-read module records from `map` by id (read-only; does not redraw)."""
    return {"modules": REGISTRY.store(map).get_modules(modules)}


@mcp.tool(**_APP)
def update_modules(map: str, updates: list[dict]) -> dict:
    """Bulk-patch modules in `map` and re-render. Each dict needs 'id' plus editable fields."""
    store = REGISTRY.store(map)
    store.update_modules(updates)
    return _ack(store)


@mcp.tool(**_APP)
def delete_modules(map: str, modules: list[str]) -> dict:
    """Bulk-delete modules from `map` by id, prune dangling edges, then re-render."""
    store = REGISTRY.store(map)
    store.delete_modules(modules)
    return _ack(store)


_WS_FIELDS = {f.name for f in fields(WorkStep)}

CANON_GRILL_PROMPT = (
    "Enter the /deepen grilling loop for {head} (map '{map}', module '{module}'"
    "{sid}, depth {depth:.2f}, coverage {cov:.0%}). Call mark_grilling as you begin, "
    "then grilling_done(decision=accepted|deferred|rejected, note, adr) to close it; "
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


@mcp.tool
def start_grilling(map: str, module: str) -> str:
    """UI callback: fired when the user clicks 'Grill this candidate' on a node.

    Persists the candidate as 'requested' (so a terminal /deepen or another surface
    can pick it up via grilling_queue) and returns the prompt that hands control to
    the /deepen grilling loop for `module` in `map`.
    """
    store = REGISTRY.store(map)
    s = _first_open(store.modules[module])
    if s:
        store.request_grilling(s.id)
    return _grill_prompt(store, map, module)


@mcp.tool
def grilling_queue(map: str) -> dict:
    """Candidates a user flagged for grilling that no agent has picked up yet — a
    terminal /deepen polls this to find work queued from the studio / another surface."""
    return {"map": map, "queued": REGISTRY.store(map).queued_for_grilling()}


@mcp.tool(**_APP)
def grilling_done(map: str, suggestion_id: str, decision: str, note: str = "", adr: str = "") -> dict:
    """Close a grilling loop: mark the candidate grilled and record the verdict
    (accepted | deferred | rejected) + reason (+ optional docs/adr/NNNN path), then
    re-render. The candidate is KEPT as the durable record (not deleted)."""
    store = REGISTRY.store(map)
    store.mark_grilled(suggestion_id)
    store.decide(suggestion_id, decision, note, adr)
    return _ack(store)


@mcp.tool(**_APP)
def realize_module(map: str, module: str, depth: float | None = None,
                   coverage: float | None = None, files: list[str] | None = None) -> dict:
    """fathom:code: flip a planned/intended module to a real built one
    (plane->actual, lifecycle->built) once its source exists, optionally recording
    the achieved depth/coverage/files. Re-renders."""
    store = REGISTRY.store(map)
    store.realize_module(module, depth, coverage, files)
    return _ack(store)


# --- Plans + work steps (fathom:plan creates; fathom:code executes) ----------
@mcp.tool(**_APP)
def create_plan(map: str, id: str, title: str, domain: str = "", intent: str = "",
                moduleIds: list[str] | None = None) -> dict:
    """fathom:plan: create a Plan (intended deep structure for new/changing work) on
    `map`. `moduleIds` are the intended modules it introduces — add those with
    add_module(plane='intended', lifecycle='planned'). Re-renders."""
    store = REGISTRY.ensure(map)
    store.create_plan(Plan(id=id, title=title, domain=domain, intent=intent,
                           moduleIds=moduleIds or []))
    return _ack(store)


@mcp.tool(**_APP)
def add_work_steps(map: str, plan_id: str, steps: list[dict]) -> dict:
    """Append ordered build steps to a plan. Each step dict needs id/title; optional
    targets (module ids), interface (the test surface), dependsOnSteps, adapters
    (DEEPENING.md category + which adapters), note. fathom:code executes them in
    order. Re-renders."""
    store = REGISTRY.store(map)
    store.add_work_steps(plan_id, [WorkStep(**{k: v for k, v in s.items() if k in _WS_FIELDS})
                                   for s in steps])
    return _ack(store)


@mcp.tool(**_APP)
def set_step_status(map: str, plan_id: str, step_id: str, status: str) -> dict:
    """Advance a work step: todo | in-progress | done | blocked. Re-renders."""
    store = REGISTRY.store(map)
    store.set_step_status(plan_id, step_id, status)
    return _ack(store)


@mcp.tool
def get_plan(map: str, plan_id: str) -> dict:
    """Read a plan's full record (intent, intended module ids, ordered steps). Read-only."""
    return REGISTRY.store(map).get_plan(plan_id)


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
    return JSONResponse(_build_view(store.to_dict(), spec))


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


if __name__ == "__main__":
    main()
