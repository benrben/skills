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

from .model import ArchModel, Module, Suggestion

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
    @property
    def modules(self): return self._load().modules

    # writes (load -> mutate -> save)
    def set_depth(self, mid, s): self._write(lambda m: m.set_depth(mid, s))
    def set_coverage(self, mid, f): self._write(lambda m: m.set_coverage(mid, f))
    def mark_updated(self, mid, u=True): self._write(lambda m: m.mark_updated(mid, u))
    def add_suggestion(self, mid, s): self._write(lambda m: m.add_suggestion(mid, s))
    def resolve(self, sid): self._write(lambda m: m.resolve(sid))
    def decide(self, sid, d, n=""): self._write(lambda m: m.decide(sid, d, n))
    def add_module(self, mod): self._write(lambda m: m.add_module(mod))
    def update_module(self, mid, **ch): self._write(lambda m: m.update_module(mid, **ch))
    def delete_module(self, mid): self._write(lambda m: m.delete_module(mid))
    def add_modules(self, mods): self._write(lambda m: m.add_modules(mods))
    def update_modules(self, ups): self._write(lambda m: m.update_modules(ups))
    def delete_modules(self, ids): self._write(lambda m: m.delete_modules(ids))


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
UI_APP = AppConfig(resourceUri=UI_URI, csp=_UI_CSP) if _HAS_APPS else None  # tools -> point at the UI
UI_RESOURCE_APP = AppConfig(csp=_UI_CSP) if _HAS_APPS else None             # resource -> is the UI
# Spread these into the decorators instead of hard-coding `app=...`: without the
# fastmcp[apps] extra there's no MCP-App link (the host falls back to text), and a
# FastMCP that predates the `app=` kwarg would otherwise raise on import. The HTTP
# studio (custom routes + /api) doesn't need apps and works either way.
_APP = {"app": UI_APP} if _HAS_APPS else {}
_RES_APP = {"app": UI_RESOURCE_APP} if _HAS_APPS else {}


def _inline_studio_app() -> str:
    """Build the self-contained studio for the MCP-App sandbox.

    A host renders this resource in a sandboxed iframe that can't reach the HTTP
    server, so we inline the studio's own CSS/JS (read fresh, so edits propagate)
    rather than linking `/assets/*`. A flag set just before state.js flips its data
    layer into **host mode** — it connects to the host via @modelcontextprotocol/
    ext-apps and drives everything through the tools (get_model / set_depth /
    add_module / decide / …) instead of /api. The dagre + ext-apps CDN tags stay;
    they're whitelisted by _UI_CSP. This reuses the exact studio the browser serves
    at `/`, so the inline render mirrors it."""
    html = STUDIO_INDEX.read_text(encoding="utf-8")

    def _rel(p: str) -> str:                       # "/assets/shared/ui.css" -> "shared/ui.css"
        return p.lstrip("/").removeprefix("assets/")

    def _css(m) -> str:
        return f"<style>\n{(STUDIO_DIR / _rel(m.group(1))).read_text(encoding='utf-8')}\n</style>"

    def _js(m) -> str:
        rel = _rel(m.group(1))
        flag = "window.__ARCH_APP__ = true;\n" if rel.endswith("state.js") else ""
        return f"<script>\n{flag}{(STUDIO_DIR / rel).read_text(encoding='utf-8')}\n</script>"

    html = re.sub(r'<link rel="stylesheet" href="(/assets/[^"]+)">', _css, html)
    html = re.sub(r'<script src="(/assets/[^"]+)"></script>', _js, html)
    return html


@mcp.resource(UI_URI, mime_type="text/html;profile=mcp-app", **_RES_APP)
def studio_ui() -> str:
    """The unified studio, inlined for the MCP-App sandbox. A host renders this in a
    sandboxed iframe and drives it through the tools: show_map names the map,
    get_model feeds the full model, and set_depth / add_module / decide / resolve /
    … mutate it — every change re-rendered with the studio's own components."""
    return _inline_studio_app()


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


@mcp.tool
def start_grilling(map: str, module: str) -> str:
    """UI callback: fired when the user clicks 'Grill this candidate' on a node.

    Returns a prompt that hands control to the /improve-codebase-architecture
    grilling loop for the chosen module in `map`.
    """
    m = REGISTRY.store(map).modules[module]
    s = m.suggestion
    head = s.title if s else f"the {m.label} module"
    return (
        f"Enter the /improve-codebase-architecture grilling loop for {head} "
        f"(map '{map}', module '{module}', depth {m.depth:.2f}, coverage {m.coverage:.0%})."
    )


# --- HTTP studio app (browser UI -> saved back to the server) ---------------
# The studio (ui/studio/) is served from the same FastMCP app, so the page is
# same-origin with /api/maps + /api/model + /api/act (no CORS). The studio picks a
# map (?map=<id>, switchable in the header), GETs /api/model?map=, and POSTs every
# triage/edit to /api/act with the map in the body — mutating maps/<id>.json under
# a lock. It polls /api/model every 2.5s so changes from the agent/desktop/other
# tabs converge. Launch with `python -m arch_map.web`.
def _apply_action(store: Store, action: str, body: dict) -> None:
    if action == "decide":
        store.decide(body["suggestion_id"], body["decision"], body.get("note", ""))
    elif action == "resolve":
        store.resolve(body["suggestion_id"])
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


@mcp.custom_route("/api/act", ["POST"])
async def api_act(request):
    body = await request.json()
    try:
        store = REGISTRY.resolve(body.get("map"))
        _apply_action(store, body.get("action", ""), body)
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(store.to_dict())  # Store auto-saves on each write


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
    elif name == "start_grilling":
        pass  # agent-only hand-off; a no-op when driven from a browser
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
