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

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Annotated, Literal
import asyncio
import json
import os
import re
import shutil

from fastmcp import FastMCP
from pydantic import Field
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

from .model import ArchModel, Module, Suggestion, Plan, WorkStep, Doc, Worktree
from . import ledger
from .store import Store
from .map_registry import MapRegistry, _slug
from .view_builder import TableSpec, BarSpec, _parse_view_spec, _view_filter, _build_view
from .dispatch import _dispatch_line, _dispatch_same_origin, build_dispatch_argv
from .coverage_ingest import module_coverage, read_report
from .git_facts import GitFacts, NotARepo, UnknownSha
from .import_graph import verify as verify_imports
from .whatif import preview_merge
from .worktrees import Worktrees, WorktreeError, slug as _wt_slug, default_path as _wt_default_path

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

mcp = FastMCP(
    "arch-map",
    instructions=(
        "Persistent, file-backed architecture maps — one named map per project; every "
        "tool takes an explicit `map` id and maps are shared (no per-agent access). "
        "READ the model: archmap_show_map, archmap_get_full_model, archmap_get_metrics, "
        "archmap_render_view, archmap_board (the skill-cycle task Kanban). MEASURE facts: "
        "archmap_ingest (churn from git, coverage from a test report, size from LOC) and "
        "archmap_scan_signals. TRACK change: archmap_drift, archmap_history, "
        "archmap_verify_edges, archmap_whatif. MUTATE through action-dispatchers — "
        "archmap_modules, archmap_suggestions, archmap_grilling, archmap_plans (its steps are "
        "board tasks), archmap_docs, archmap_worktrees (per-task isolated git branches) — each "
        "takes action=add|update|delete|... . "
        "Vocabulary: module (interface + implementation), depth (much behaviour behind a small "
        "interface), seam, leak, coverage, candidate (a proposed deepening) and its grilling, "
        "Plan/WorkStep (a task on the board), worktree (a task's isolated branch), and doc types "
        "(glossary/note/adr/spec/risk/runbook/postmortem/diagram). "
        "Over HTTP, root defaults to the studio's launch dir, so pass root= explicitly to the "
        "tools that read the repo (archmap_ingest/archmap_drift/archmap_verify_edges/archmap_worktrees)."
    ),
)

# Persisted, file-backed state. Each *named map* is one JSON file under maps/, so
# many maps (one per project) coexist; every read loads the latest from disk and
# every write saves it back under a lock, so the stdio tools, the HTTP studio, and
# other processes share ONE source of truth per map and survive restarts. A map
# starts EMPTY — no sample is seeded; whatever you add is kept.
# Persistent map storage. Honors $ARCH_MAP_DATA_DIR (the plugin's .mcp.json sets this
# to ${CLAUDE_PLUGIN_DATA}) so user maps survive plugin updates and read-only install
# trees; falls back to maps/ beside the package for local dev. Created on first use.
_DATA_DIR = os.environ.get("ARCH_MAP_DATA_DIR")
MAPS_DIR = ((Path(_DATA_DIR).expanduser() / "maps") if _DATA_DIR else (HERE.parent / "maps")).resolve()
MAPS_DIR.mkdir(parents=True, exist_ok=True)


# Store and MapRegistry now live in store.py / map_registry.py (extracted per
# adr-split-spine-hub) and are imported above, so srv.Store / srv.MapRegistry /
# srv._slug resolve unchanged for the tools, routes, and tests.


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

# Cap on the whole-model reads (show_map / get_full_model / render_view), which can
# otherwise dump the entire model into the context window. Honored by hosts that
# read the `anthropic/maxResultSizeChars` tool meta.
_MAX_RESULT = {"anthropic/maxResultSizeChars": 25000}


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
# The view-builder (TableSpec / BarSpec / _parse_view_spec / _view_filter /
# _build_view) now lives in view_builder.py (extracted per adr-split-spine-hub)
# and is imported above; render_view and the /api/view route drive it unchanged.


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
    def run():
        all_maps = REGISTRY.list()
        page = all_maps[offset:offset + limit]
        return {"maps": page, "default": REGISTRY.default_id(),
                "total_count": len(all_maps),
                "has_more": offset + limit < len(all_maps),
                "next_offset": offset + limit if offset + limit < len(all_maps) else None}
    return _guard("archmap_list_maps()", False, "", run)


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
    call = f"archmap_create_map(name='{name}'" + (f", map_id='{mid}'" if map_id else "") + ")"
    hint = "List existing maps via archmap_list_maps; pass a different map_id to avoid a clash."

    def run():
        ack = _ack(REGISTRY.create(mid, repo or name or mid), changed=f"created project {mid}")
        ack["map"] = mid          # the id to pass to subsequent tool calls
        return ack
    return _guard(call, True, hint, run)


@mcp.tool(name="archmap_rename_map", **_APP)
def rename_map(map: str, to: str, repo: str = "") -> dict:
    """Rename a map. `map` is the current id, `to` the new id, `repo` the new
    display label (defaults to `to` if blank). Use to point a map at a real
    project, e.g. rename_map("arch-map", "mr-meeseeks", "Mr. Meeseeks")."""
    new_id = _slug(to)
    call = f"archmap_rename_map(map='{map}', to='{new_id}')"
    hint = "List existing maps via archmap_list_maps; the target id must be free."
    return _guard(call, True, hint, lambda: _ack(
        REGISTRY.rename(map, new_id, repo or to), changed=f"renamed {map} -> {new_id}"))


@mcp.tool(name="archmap_delete_map")
def delete_map(map: str) -> dict:
    """Delete an entire named map and its file. IRREVERSIBLE — the map's JSON file
    is removed permanently and there is no undo; archmap_list_maps first if unsure."""
    call = f"archmap_delete_map(map='{map}')"
    hint = "List existing maps via archmap_list_maps to confirm the id."

    def run():
        REGISTRY.delete(map)
        return {"ok": True, "deleted": map, "maps": [m["id"] for m in REGISTRY.list()]}
    return _guard(call, True, hint, run)


@mcp.tool(name="archmap_show_map", meta=_MAX_RESULT, **_APP)
def show_map(map: str, domain: str = "", ids: list[str] | None = None) -> dict:
    """Render a map — a DIGEST by default, module records only on request. Reads
    only an EXISTING map (it never auto-creates one); use archmap_create_map first.

    No filter -> digest: module/domain counts, orphans, open suggestions, and the
    ten worst-health modules. It deliberately does NOT return every module record
    (that grows with the map); pass `domain="<d>"` or `ids=[...]` to get the full
    view records for just that slice, or call archmap_get_full_model for everything.
    Inside an MCP-App host this drives the inline studio: the result tells the
    studio which `map` to render and it pulls the full model itself."""
    call = f"archmap_show_map(map='{map}')"
    hint = "List existing maps via archmap_list_maps, or create one with archmap_create_map."
    return _guard(call, False, hint, lambda: _show_map_impl(map, domain, ids))


def _show_map_impl(map: str, domain: str, ids: list[str] | None) -> dict:
    store = REGISTRY.store(map)                       # raises KeyError — no phantom map on a read
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


_FULL_MODEL_SECTIONS = ("modules", "plans", "docs", "board")


@mcp.tool(name="archmap_get_full_model", meta=_MAX_RESULT, **_APP)
def get_full_model(
    map: str,
    include: list[str] | None = None,
    module_limit: int = 0,
    module_offset: int = 0,
) -> dict:
    """Return a map's FULL model — every module's interface, files, tests, and
    suggestion bodies — which is what the inline studio renders. Heavier than
    archmap_show_map (the digest), so the studio calls this once it knows the
    map and after each edit; agents normally use archmap_show_map.

    With NO extra args the result is byte-for-byte today's whole model. To bound it:
      include: keep only these top-level sections (subset of
               ["modules","plans","docs","board"]); "docs" also keeps docMembership,
               "board" also keeps worktrees. Sections you omit are dropped.
      module_limit / module_offset: page the modules list (only when module_limit>0).
               Adds {"truncated", "next_offset", "total_modules"} so the caller can
               fetch the rest with a follow-up call."""
    call = f"archmap_get_full_model(map='{map}')"
    hint = "List existing maps via archmap_list_maps, or create one with archmap_create_map."
    return _guard(call, False, hint, lambda: _get_full_model_impl(
        map, include, module_limit, module_offset))


def _get_full_model_impl(map: str, include: list[str] | None,
                         module_limit: int, module_offset: int) -> dict:
    v = REGISTRY.store(map).to_dict()                 # raises KeyError — no phantom map on a read
    v["map"] = map
    if module_limit and module_limit > 0:
        all_mods = v.get("modules") or []
        total = len(all_mods)
        end = module_offset + module_limit
        v["modules"] = all_mods[module_offset:end]
        v["truncated"] = end < total
        v["next_offset"] = end if end < total else None
        v["total_modules"] = total
    if include is not None:
        keep = set(include)
        # each requested section keeps its computed companion key
        if "docs" in keep:
            keep.add("docMembership")
        if "board" in keep:
            keep.add("worktrees")
        droppable = set(_FULL_MODEL_SECTIONS) | {"docMembership", "worktrees"}
        for key in list(v):
            if key in droppable and key not in keep:
                v.pop(key, None)
    return v


@mcp.tool(name="archmap_render_view", meta=_MAX_RESULT, **_VIEW_APP)
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
    call = f"archmap_render_view(map='{map}')"
    hint = "List existing maps via archmap_list_maps, or create one with archmap_create_map."

    def run():
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
    return _guard(call, False, hint, run)


@mcp.tool(name="archmap_get_metrics")
def get_metrics(map: str, module: str | None = None,
                        limit: int = 50, offset: int = 0) -> dict:
    """Return computed graph metrics for one module or all modules in `map`:
    fanIn, fanOut, instability, blastRadius, coupling, inCycle, health, churn.
    These are derived from the dependency graph — no extra data needed.

    Pass `module` for a single module's metrics. With no `module`, returns a page of
    all modules' metrics (keyed by id, ordered by id) — use `limit` (default 50) and
    `offset` to page; the response carries total_count / has_more / next_offset."""
    call = f"archmap_get_metrics(map='{map}')"
    hint = "List existing maps via archmap_list_maps, or create one with archmap_create_map."

    def run():
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
    return _guard(call, False, hint, run)


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


@mcp.tool(name="archmap_scan_signals", meta=_MAX_RESULT)
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
    call = f"archmap_scan_signals(map='{map}')"
    hint = "List existing maps via archmap_list_maps, or create one with archmap_create_map."

    def run():
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
    return _guard(call, False, hint, run)


# --- Ground truth: measured facts, drift, history, edge verification ---------
# These tools make the map self-truing: churn/coverage/LOC become measurements
# (git-facts + coverage-ingest), anchors recorded by the reconcile flow give the
# digest its staleness line (reconcile-ledger), and recorded edges are checked
# against real imports (import-graph). `root` is the repo work tree; it defaults
# to the server's cwd.
def _repo_root(root: str) -> str:
    return root or os.getcwd()


# --- worktrees: per-task isolated branches (the board's isolation unit) -------
# Real `git worktree` work lives in worktrees.py; here we guard it (default ON,
# same gate philosophy as /api/dispatch) and pick a default location OUTSIDE the
# main working tree so the checkout never nests in the repo it forks from.
_BOARD_RUNNING: set = set()        # (map, planId, stepId) — a task agent is live in its worktree


def _running_keys(map_id: str) -> set:
    """The (planId, stepId) pairs a task agent is actively dispatched on, for `map`
    — the board's ⚙ live marker. Ephemeral per-process state, never persisted."""
    return {(p, s) for (m, p, s) in _BOARD_RUNNING if m == map_id}


def _worktree_exec_allowed() -> bool:
    """Real `git worktree` provisioning is ON unless ARCH_MAP_ALLOW_WORKTREE is
    0/false/no/off — then create/remove degrade to a copy-paste command (fallback),
    mirroring /api/dispatch's disabled path."""
    return os.environ.get("ARCH_MAP_ALLOW_WORKTREE", "1").strip().lower() not in ("0", "false", "no", "off")


def _worktree_base(root: str) -> "Path":
    """Where task worktrees are checked out: $ARCH_MAP_WORKTREE_DIR if set, else a
    `.fathom-worktrees/` sibling of the repo (kept out of the main working tree)."""
    env = os.environ.get("ARCH_MAP_WORKTREE_DIR")
    if env:
        return Path(env).expanduser()
    return Path(_repo_root(root)).resolve().parent / ".fathom-worktrees"


def _safe_git_worktrees(wm: "Worktrees") -> list[dict]:
    """`git worktree list`, or [] when there's no repo/git — sync/list never error
    just because the server isn't running inside a git work tree."""
    try:
        return wm.list()
    except (NotARepo, UnknownSha, WorktreeError):
        return []


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
    archmap_history read. `root` defaults to the server's cwd. Over HTTP, root
    defaults to the studio's launch dir, so pass root= explicitly."""
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


@mcp.tool(name="archmap_drift", meta=_MAX_RESULT)
def drift(map: str, since_sha: str = "", root: str = "",
          limit: int = 0, offset: int = 0) -> dict:
    """How stale is the map? Changes since the last reconcile anchor (or since an
    explicit `since_sha` baseline — the review-style question): the changed files,
    the modules they belong to, the changed files NO module owns, and a one-line
    summary. Read-only; degraded outcomes (no anchors / no repo) come back with
    anchored=false and a `reason`, never an error. Over HTTP, root defaults to the
    studio's launch dir, so pass root= explicitly.

    Big diffs: pass limit>0 to page the changedFiles/unmappedFiles lists (default 0 =
    return everything); the response then carries total_count / has_more / next_offset."""
    call = f"archmap_drift(map='{map}')"
    hint = "Record a baseline first via archmap_ingest(map) on a reconcile."

    def run():
        model = REGISTRY.store(map)._load()
        out = ledger.drift(model, GitFacts(_repo_root(root)), since_sha or None)
        out["map"] = map
        if limit and limit > 0:
            changed = out.get("changedFiles") or []
            total = len(changed)
            end = offset + limit
            out["changedFiles"] = changed[offset:end]
            out["unmappedFiles"] = (out.get("unmappedFiles") or [])[offset:end]
            out["total_count"] = total
            out["has_more"] = end < total
            out["next_offset"] = end if end < total else None
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


@mcp.tool(name="archmap_verify_edges", meta=_MAX_RESULT)
def verify_edges(map: str, root: str = "", limit: int = 0, offset: int = 0) -> dict:
    """Check the map's recorded dependsOn/leaksTo edges against the code's REAL
    imports (Python via ast, JS/TS via import lexing). Returns confirmedEdges,
    undeclaredEdges (in code but not on the map — candidate leaks), missingEdges
    (on the map but not in code; only reported when both modules own parsed
    source, so prose modules never false-positive), and the unparseable files.
    Read-only — surfacing is this tool's job, deciding is fathom:map's. Over HTTP,
    root defaults to the studio's launch dir, so pass root= explicitly.

    Big graphs: pass limit>0 to page the confirmed/undeclared/missingEdges lists
    (default 0 = return everything); the response then carries total_count /
    has_more / next_offset (total_count is the longest of the three edge lists)."""
    call = f"archmap_verify_edges(map='{map}')"
    hint = "Pass root=<repo work tree> if the server does not run inside the repo."

    def run():
        out = verify_imports(REGISTRY.store(map)._load(), _repo_root(root))
        out["map"] = map
        if limit and limit > 0:
            end = offset + limit
            total = max(len(out.get(k) or [])
                        for k in ("confirmedEdges", "undeclaredEdges", "missingEdges"))
            for k in ("confirmedEdges", "undeclaredEdges", "missingEdges"):
                out[k] = (out.get(k) or [])[offset:end]
            out["total_count"] = total
            out["has_more"] = end < total
            out["next_offset"] = end if end < total else None
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
    action: Annotated[Literal["add", "update", "delete", "get", "realize"],
                      Field(description="which operation to run on module node(s)")],
    id: Annotated[str, Field(description="the single module id this action targets")] = "",
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
    items: Annotated[list[dict] | None,
                     Field(description="bulk add/update payload: [{id, label, domain, ...}, ...]")] = None,
    ids: Annotated[list[str] | None,
                   Field(description="bulk target ids (or [\"*\"] on update for every module)")] = None,
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
            mods = [Module.from_dict(d) for d in items]
            store.add_modules(mods)
            ack = _ack(store)
            ack["createdIds"] = [m.id for m in mods]   # the ids the bulk add created
            return ack
        store.add_module(Module.from_dict({"id": id, **flds}))   # from_dict validates id/label/domain
        ack = _ack(store)
        ack["created"] = store.get_module(id)          # the created record (ids/edges resolved)
        return ack
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
    action: Annotated[Literal["flag", "decide", "dismiss"],
                      Field(description="flag a new candidate, decide a verdict, or dismiss one")],
    module: Annotated[str, Field(description="module id to flag a candidate on (action='flag')")] = "",
    suggestion_id: Annotated[str, Field(description="candidate id to decide/dismiss (from a flag ack)")] = "",
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
        ack = _ack(store)
        ack["suggestion_id"] = sid                     # the derived id to decide/dismiss/grill
        return ack
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
    action: Annotated[Literal["start", "mark", "finish", "queue"],
                      Field(description="which step of the /deepen grilling lifecycle to run")],
    module: Annotated[str, Field(description="module whose first open candidate to start grilling (action='start')")] = "",
    suggestion_id: Annotated[str, Field(description="candidate id to mark/finish")] = "",
    decision: Literal["accepted", "deferred", "rejected", ""] = "",
    note: str = "",
    adr: str = "",
) -> dict:
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
    action: Annotated[Literal["create", "add_steps", "set_step_status", "set_step", "update", "get"],
                      Field(description="which plan/work-step operation to run")],
    plan_id: Annotated[str, Field(description="the plan this action targets")] = "",
    title: str = "",
    domain: str | None = None,
    intent: str | None = None,
    status: Literal["draft", "active", "done", "abandoned", ""] = "",
    moduleIds: list[str] | None = None,
    adrRefs: list[str] | None = None,
    steps: Annotated[list[dict] | None,
                     Field(description="ordered build steps to append: [{id, title, targets?, interface?, ...}, ...]")] = None,
    step_id: str = "",
    step_status: Literal["todo", "understand", "plan", "in-progress",
                         "review", "done", "blocked", ""] = "",
    priority: Literal["low", "normal", "high", "urgent", ""] = "",
    agent: str | None = None,
    worktree: str | None = None,
    blocked: bool | None = None,
) -> dict:
    """Manage PLANS (intended deep structure) and their work steps in `map`, by `action`.
    Writes re-render and return the compact ack; get returns the plan record. A step is
    a TASK on the board (archmap_board) — its `status` is the skill-cycle column and its
    `agent` is the swimlane.

      action="create":          create plan `plan_id` (needs title; optional domain,
                                 intent, moduleIds). (fathom:design)
      action="add_steps":       append ordered build steps to `plan_id`: steps=[{id,
                                 title, targets?, interface?, dependsOnSteps?, adapters?,
                                 note?, priority?, agent?, worktree?}, ...]. Unknown step
                                 keys are REJECTED. fathom:code executes steps in order.
      action="set_step_status": move step `step_id` of `plan_id` across the board — its
                                 status is one of todo|understand|plan|in-progress|review|done.
      action="set_step":        patch a step's board fields without moving columns —
                                 step_status and/or priority (low|normal|high|urgent),
                                 agent (swimlane), worktree (id), blocked (true|false).
      action="update":          patch plan `plan_id` (title/domain/intent/status/
                                 moduleIds/adrRefs); status is draft|active|done|abandoned.
      action="get":             read plan `plan_id`'s full record (read-only)."""
    call = f"archmap_plans(action='{action}'" + (f", plan_id='{plan_id}'" if plan_id else "") + ")"
    hint = "Read the plan via archmap_plans(map, action='get', plan_id=...)."
    return _guard(call, action != "get", hint, lambda: _plans_impl(
        map, action, plan_id, title, domain, intent, status,
        moduleIds, adrRefs, steps, step_id, step_status,
        priority, agent, worktree, blocked))


def _plans_impl(map, action, plan_id, title, domain, intent, status,
                moduleIds, adrRefs, steps, step_id, step_status,
                priority="", agent=None, worktree=None, blocked=None) -> dict:
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
    if action == "set_step":
        ch = {k: v for k, v in dict(
            status=(step_status or None), priority=(priority or None),
            agent=agent, worktree=worktree, blocked=blocked).items() if v is not None}
        if not ch:
            raise ValueError("plans(action='set_step') needs at least one of "
                             "step_status/priority/agent/worktree/blocked")
        store.set_step_fields(plan_id, step_id, **ch)
        return _ack(store)
    if action == "update":
        ch = {k: v for k, v in dict(title=(title or None), domain=domain, intent=intent,
                                    status=(status or None), moduleIds=moduleIds,
                                    adrRefs=adrRefs).items() if v is not None}
        store.update_plan(plan_id, **ch)
        return _ack(store)
    return store.get_plan(plan_id)                 # get


@mcp.tool(name="archmap_board", meta=_MAX_RESULT, **_APP)
def board(map: str) -> dict:
    """The TASK BOARD: every WorkStep projected into the skill-cycle Kanban — columns
    `todo | understand | plan | in-progress | review | done` (each column owned by a
    Fathom skill: understand→understand, plan→design, in-progress→code, review→review),
    swimlanes grouped by the agent handling each task, and the per-task git worktree
    each card is built in. Read-only; the SAME projection the studio board renders.

    Returns {columns, counts (per column), lanes:[{agent, cards}], cards, worktrees}.
    Each card carries planId/stepId/title/column/blocked/priority/agent/targets and its
    worktree (branch + path) or null, plus a `running` flag when a task agent is live in
    its worktree. Use to see/track work across the cycle from a terminal agent — moves
    are made with archmap_plans(action='set_step'|'set_step_status') and worktrees with
    archmap_worktrees."""
    call = f"archmap_board(map='{map}')"
    hint = "List existing maps via archmap_list_maps, or create one with archmap_create_map."

    def run():
        model = REGISTRY.store(map)._load()          # raises KeyError — no phantom map on a read
        out = model.board(running=_running_keys(map))
        out["map"] = map
        return out
    return _guard(call, False, hint, run)


@mcp.tool(name="archmap_worktrees", **_APP)
def worktrees(
    map: str,
    action: Annotated[Literal["list", "create", "remove", "prune", "attach", "sync"],
                      Field(description="which worktree operation to run")],
    branch: Annotated[str, Field(description="the task branch (create/attach); derived from step/title if blank)")] = "",
    path: str = "",
    base: str = "",
    plan_id: str = "",
    step_id: str = "",
    agent: str = "",
    id: Annotated[str, Field(description="worktree id to remove (or override the derived id on create/attach)")] = "",
    force: bool = False,
    root: str = "",
    note: str = "",
) -> dict:
    """Manage per-task git WORKTREES on `map`, by `action` — the board's isolation
    unit: one branch + checkout per WorkStep so an agent builds a task without
    colliding in the shared working tree. The spine RECORDS each worktree (the board
    shows the branch + agent); real `git worktree` runs when allowed (ON unless
    ARCH_MAP_ALLOW_WORKTREE is off) — otherwise it degrades to a copy-paste command.

      action="create": provision a worktree for a task — needs branch (or a step_id/
                       title to derive one); optional base (fork point), plan_id/step_id
                       (links + back-references the card), agent, path. Records it and
                       (when allowed) runs `git worktree add -b <branch>`; returns the
                       worktree + provisioned flag (and a `command` fallback if not).
      action="attach": record an EXISTING branch/worktree as a task's worktree (no git
                       mutation) — branch (+ optional path/plan_id/step_id/agent).
      action="remove": drop worktree `id` — removes the checkout (best-effort) and the
                       spine record. force=true discards local changes.
      action="prune":  `git worktree prune` (forget vanished checkouts).
      action="sync":   reconcile spine worktrees against `git worktree list` — refresh
                       HEAD shas, mark vanished ones status='removed'. fathom:map runs this.
      action="list":   spine worktrees + the live `git worktree list`. Read-only.

    Over HTTP, root defaults to the studio's launch dir, so pass root= explicitly."""
    call = f"archmap_worktrees(action='{action}')"
    hint = "List worktrees via archmap_worktrees(map, action='list')."
    return _guard(call, action not in ("list",), hint, lambda: _worktrees_impl(
        map, action, branch=branch, path=path, base=base, plan_id=plan_id,
        step_id=step_id, agent=agent, wt_id=id, force=force, root=root, note=note))


def _worktrees_impl(map, action, *, branch="", path="", base="", plan_id="",
                    step_id="", agent="", wt_id="", force=False, root="", note=""):
    store = REGISTRY.ensure(map) if action in ("create", "attach") else REGISTRY.store(map)
    repo = _repo_root(root)
    wm = Worktrees(repo)

    if action == "list":
        model = store._load()
        return {"map": map, "worktrees": [asdict(w) for w in model.worktrees.values()],
                "gitWorktrees": _safe_git_worktrees(wm)}

    if action == "create":
        # derive a branch from the step/title when not given (feat/<slug>)
        if not branch:
            seed = step_id or note
            if not seed:
                raise ValueError("worktrees(action='create') needs branch (or step_id/note to derive one)")
            branch = "feat/" + _wt_slug(seed)
        wid = wt_id or _wt_slug(branch)
        wt_path = path or _wt_default_path(_worktree_base(root), branch)
        provisioned, head = False, ""
        fallback_cmd = f"git worktree add -b {branch} {wt_path}" + (f" {base}" if base else "")
        if _worktree_exec_allowed() and shutil.which("git"):
            try:
                e = wm.add(wt_path, branch, base=base, new_branch=True)
                head, wt_path, provisioned = e.get("head", ""), e.get("path", wt_path), True
            except (NotARepo, UnknownSha, WorktreeError) as ex:
                note = (note + " — " if note else "") + f"not provisioned: {ex}"
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        store.add_worktree(Worktree(id=wid, branch=branch, path=wt_path, base=base,
                                    planId=plan_id, stepId=step_id, agent=agent,
                                    head=head, created=created, note=note))
        out = _ack(store, changed=f"created worktree {wid}")
        out.update({"worktree": store.get_worktree(wid), "provisioned": provisioned})
        if not provisioned:
            out.update({"fallback": True, "command": fallback_cmd})
        return out

    if action == "attach":
        if not branch:
            raise ValueError("worktrees(action='attach') needs branch")
        wid = wt_id or _wt_slug(branch)
        wt_path = path
        if not wt_path:                       # find the checkout git already has for this branch
            wt_path = next((e["path"] for e in _safe_git_worktrees(wm) if e["branch"] == branch), "")
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        store.add_worktree(Worktree(id=wid, branch=branch, path=wt_path, base=base,
                                    planId=plan_id, stepId=step_id, agent=agent,
                                    created=created, note=note))
        out = _ack(store, changed=f"attached worktree {wid}")
        out["worktree"] = store.get_worktree(wid)
        return out

    if action == "remove":
        if not wt_id:
            raise ValueError("worktrees(action='remove') needs id")
        rec = store.get_worktree(wt_id)       # KeyError if absent
        git_removed = False
        if rec.get("path") and _worktree_exec_allowed() and shutil.which("git"):
            try:
                wm.remove(rec["path"], force=force)
                git_removed = True
            except (NotARepo, UnknownSha, WorktreeError):
                pass
        store.delete_worktree(wt_id)
        out = _ack(store, changed=f"removed worktree {wt_id}")
        out["gitRemoved"] = git_removed
        return out

    if action == "prune":
        if _worktree_exec_allowed() and shutil.which("git"):
            try:
                wm.prune()
            except (NotARepo, WorktreeError):
                pass
        return _worktrees_sync(store, map, wm)

    # action == "sync"
    return _worktrees_sync(store, map, wm)


def _worktrees_sync(store: Store, map: str, wm: Worktrees) -> dict:
    """Reconcile spine worktrees against the live `git worktree list`: refresh each
    one's HEAD sha, and mark a worktree whose checkout has vanished status='removed'
    (and re-activate one that came back). The honesty pass fathom:map runs."""
    git_list = _safe_git_worktrees(wm)
    by_path = {os.path.realpath(e["path"]): e for e in git_list if e.get("path")}
    by_branch = {e["branch"]: e for e in git_list if e.get("branch")}
    updated = []
    for w in list(store.worktrees.values()):
        git_entry = (by_path.get(os.path.realpath(w.path)) if w.path else None) or by_branch.get(w.branch)
        # A worktree whose checkout dir is gone is dead even if git hasn't pruned its
        # admin entry yet — the honest signal is the directory on disk, not git's list.
        path_gone = bool(w.path) and not os.path.isdir(w.path)
        live = git_entry is not None and not path_gone
        ch = {}
        if live:
            if git_entry.get("head") and git_entry["head"] != w.head:
                ch["head"] = git_entry["head"]
            if w.status == "removed":
                ch["status"] = "active"
        elif w.status != "removed":
            ch["status"] = "removed"
        if ch:
            store.update_worktree(w.id, **ch)
            updated.append(w.id)
    out = _ack(store, changed="synced worktrees")
    out.update({"updated": updated, "gitWorktrees": git_list})
    return out


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
    action: Annotated[Literal["add", "update", "delete", "list", "get"],
                      Field(description="which doc operation to run")],
    doc_id: Annotated[str, Field(description="the doc this action targets (add/update/delete/get)")] = "",
    type: Literal["adr", "note", "rule", "rfc", "glossary",
                  "spec", "ceiling", "risk", "runbook", "postmortem", "diagram", ""] = "",
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

      action="add":    create doc `doc_id` — needs type and title; optional summary,
                       body, status, tags, supersedes, adrRef, author, and a scope
                       (below; defaults to whole-system). Types (see DOC-TYPES.md):
                       glossary|note|risk|runbook|postmortem (knowledge), diagram
                       (a Mermaid body), rfc|adr (decision), spec (contract),
                       rule|ceiling (build/style).
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


def _grill_text(map: str, m: Module, s) -> str:
    """The canonical /deepen walkthrough text for one module + (optional) candidate.
    Single source of truth shared by the archmap_grilling(start) tool, the
    archmap:// flow, and the grill_candidate prompt — given the already-resolved
    module and suggestion so each caller resolves them however it keys (module-first
    for the tool, suggestion-first for the prompt)."""
    head = s.title if s else f"the {m.label} module"
    sid = f", suggestion '{s.id}'" if s else ""
    return CANON_GRILL_PROMPT.format(head=head, map=map, module=m.id, sid=sid,
                                     depth=m.depth, cov=m.coverage)


def _grill_prompt(store: Store, map: str, module: str) -> str:
    m = store.modules[module]
    return _grill_text(map, m, _first_open(m))


def _grill_prompt_for_suggestion(store: Store, map: str, suggestion_id: str) -> str:
    """Build the SAME walkthrough text the archmap_grilling(start) tool builds, but
    keyed by suggestion id (raises KeyError if the suggestion — and thus its map —
    does not exist; never creates anything)."""
    m, s = store._load()._find_suggestion(suggestion_id)
    return _grill_text(map, m, s)


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
    elif action == "set_step_fields":
        store.set_step_fields(body["plan_id"], body["step_id"], **body.get("fields", {}))
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


def _overlay_running(model_dict: dict, map_id: str) -> None:
    """Stamp the board cards a task agent is live on with running=True. The board in
    to_dict() is computed without the ephemeral run set (model.py stays pure); this
    overlays it per request so every polling studio tab shows the ⚙ marker."""
    keys = _running_keys(map_id)
    if not keys:
        return
    for c in (model_dict.get("board") or {}).get("cards", []):
        if (c.get("planId"), c.get("stepId")) in keys:
            c["running"] = True            # cards are shared refs with lanes -> both update


@mcp.custom_route("/api/model", ["GET"])
async def api_model(request):
    map_id = request.query_params.get("map")
    try:
        store = REGISTRY.resolve(map_id)
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    d = store.to_dict()
    _overlay_running(d, map_id or REGISTRY.default_id())
    return JSONResponse(d)


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


@mcp.custom_route("/api/board", ["GET"])
async def api_board(request):
    """GET -> the task board projection (skill-cycle columns × agent swimlanes) with
    the live ⚙ run markers for this map. The studio also gets `board` inside /api/model
    (to_dict), so this is mainly for parity + cross-tool reads."""
    map_id = request.query_params.get("map")
    try:
        store = REGISTRY.resolve(map_id)
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return JSONResponse(store.board(running=_running_keys(map_id or REGISTRY.default_id())))


@mcp.custom_route("/api/worktrees", ["GET", "POST"])
async def api_worktrees(request):
    """GET -> the map's worktrees + the live `git worktree list`. POST {op|action, ...}
    -> create/attach/remove/prune/sync via the SAME _worktrees_impl the archmap_worktrees
    tool uses (one dispatch, two surfaces). POST returns the refreshed full model (so the
    studio reconciles like /api/act), with the op's result stashed under `_worktreeResult`
    (carries the fallback `command` when real provisioning is off)."""
    if request.method == "GET":
        map_id = request.query_params.get("map")
        try:
            store = REGISTRY.resolve(map_id)
        except (KeyError, ValueError) as e:
            return JSONResponse({"error": str(e)}, status_code=404)
        model = store._load()
        wm = Worktrees(_repo_root(""))
        return JSONResponse({"worktrees": [asdict(w) for w in model.worktrees.values()],
                             "gitWorktrees": _safe_git_worktrees(wm)})
    # POST: a browser worktree op — same-origin guarded like /api/dispatch (it shells git)
    if not _dispatch_same_origin(request):
        return JSONResponse({"error": "cross-origin worktree op refused"}, status_code=403)
    body = await request.json()
    map_id = body.get("map") or REGISTRY.default_id()
    try:
        result = _worktrees_impl(
            map_id, body.get("op") or body.get("action", ""),
            branch=body.get("branch", ""), path=body.get("path", ""), base=body.get("base", ""),
            plan_id=body.get("plan_id", ""), step_id=body.get("step_id", ""),
            agent=body.get("agent", ""), wt_id=body.get("id", ""),
            force=bool(body.get("force")), root=body.get("root", ""), note=body.get("note", ""))
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    model = REGISTRY.resolve(map_id).to_dict()
    model["_worktreeResult"] = result
    return JSONResponse(model)


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
# OFF by default (ARCH_MAP_ALLOW_DISPATCH defaults to "0") — set ARCH_MAP_ALLOW_DISPATCH=1
# to opt in. Spawning an agent shells out, so it stays opt-in; two guards then make
# an enabled agent button safe enough for a loopback dev server: (1) a same-origin
# check so only the studio's own page can trigger a run (no cross-site/CSRF POST can
# drive the agent), and (2) the server's 127.0.0.1 bind. The spawned agent runs
# `claude -p` with acceptEdits (NOT bypass) + deny rules (no rm / git push / network).
# When disabled / no `claude` on PATH it returns 503 {fallback:true,...} so the
# browser falls back to copy-paste. The agent reaches the SAME arch-map MCP over
# http://127.0.0.1:<PORT>/mcp, so its writes land in the store the studio polls;
# source edits land in the working tree for human review (nothing is committed).
_DISPATCH_RUNNING: set = set()        # (map, kind, module) -> single-writer guard


def _step_of(store: Store, plan_id: str, step_id: str):
    """The WorkStep (plan_id, step_id) or None — no raise (a dispatch must degrade)."""
    p = store.plans.get(plan_id) if plan_id else None
    return next((s for s in p.steps if s.id == step_id), None) if p else None


def _dispatch_prompt(store: Store, map_id: str, kind: str, module: str = "",
                     modules: list | None = None, suggestion_id: str = "",
                     plan_id: str = "", step_id: str = "") -> str:
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
    if kind == "task":
        st = _step_of(store, plan_id, step_id)
        wt = store.worktrees.get(st.worktree) if (st and st.worktree) else None
        lines = [f"Build task '{step_id}'" + (f" — {st.title}" if st else "")
                 + f" (plan '{plan_id}', map '{map_id}'). This is a fathom:code build step."]
        if st and st.interface:
            lines.append("Interface (the test surface to build to): " + st.interface)
        if st and st.targets:
            lines.append("Target module(s): " + ", ".join(st.targets))
        if st and st.adapters:
            lines.append("Dependency category / adapters: " + ", ".join(st.adapters))
        if wt and wt.path:
            lines.append(f"You are running INSIDE this task's worktree at {wt.path} "
                         f"(branch '{wt.branch}'). Make ALL edits here, on this branch.")
        lines.append("When the interface tests pass, reconcile the modules you touched on "
                     "the arch-map spine and move the card to the 'review' column "
                     "(archmap_plans set_step_status). Do not commit or push.")
        return "\n".join(lines)
    return f"Agent request ({kind})" + (f" for module '{module}'" if module else "") + "."


# _dispatch_line / _dispatch_same_origin / the tool allowlist / the claude -p argv
# now live in dispatch.py (extracted per adr-split-spine-hub) and are imported above.


@mcp.custom_route("/api/dispatch", ["POST"])
async def api_dispatch(request):
    """Run a studio agent-button action by spawning headless `claude -p` in the repo
    with the arch-map MCP attached, streaming progress back as SSE. OFF unless
    ARCH_MAP_ALLOW_DISPATCH is set; degrades to 503 {fallback} so the browser keeps
    its copy-paste path."""
    if not _dispatch_same_origin(request):
        return JSONResponse({"error": "cross-origin dispatch refused"}, status_code=403)
    body = await request.json()
    map_id = body.get("map") or REGISTRY.default_id()
    kind = body.get("kind", "")
    module = body.get("module", "")
    modules = body.get("modules") or []
    sid = body.get("suggestion_id", "")
    plan_id = body.get("plan") or body.get("plan_id") or ""
    step_id = body.get("step") or body.get("step_id") or ""
    try:
        store = REGISTRY.resolve(body.get("map"))
        prompt = _dispatch_prompt(store, map_id, kind, module, modules, sid, plan_id, step_id)
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # OFF by default (opt-in): ARCH_MAP_ALLOW_DISPATCH must be 1/true/yes/on to enable.
    if os.environ.get("ARCH_MAP_ALLOW_DISPATCH", "0").strip().lower() not in ("1", "true", "yes", "on"):
        return JSONResponse({"fallback": True, "reason": "dispatch-disabled", "prompt": prompt}, status_code=503)
    claude = shutil.which("claude")
    if not claude:
        return JSONResponse({"fallback": True, "reason": "no-agent-binary", "prompt": prompt}, status_code=503)

    # A 'task' build runs INSIDE its WorkStep's worktree (the board's isolation unit):
    # cwd = the worktree checkout, the card flips to in-progress + records its agent,
    # and the board shows the ⚙ live marker for every surface watching this map.
    run_dir = os.getcwd()
    board_key = None
    label = module or (f"{plan_id}/{step_id}" if step_id else "")
    if kind == "task" and plan_id and step_id:
        st = _step_of(store, plan_id, step_id)
        wt = store.worktrees.get(st.worktree) if (st and st.worktree) else None
        if wt and wt.path and os.path.isdir(wt.path):
            run_dir = wt.path
        try:
            store.set_step_fields(plan_id, step_id, status="in-progress",
                                  agent=(st.agent if (st and st.agent) else "fathom:code"))
        except (KeyError, ValueError):
            pass
        board_key = (map_id, plan_id, step_id)

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

    key = (map_id, kind, label)
    if key in _DISPATCH_RUNNING:
        return JSONResponse({"error": "already-running", "kind": kind, "module": label}, status_code=409)

    port = os.environ.get("ARCH_MAP_PORT", "8800")
    argv = build_dispatch_argv(claude, prompt, kind, run_dir, port)

    async def stream():
        def sse(event, data):
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"
        _DISPATCH_RUNNING.add(key)
        if board_key:
            _BOARD_RUNNING.add(board_key)
        yield sse("start", {"kind": kind, "module": module, "step": step_id,
                            "plan": plan_id, "cwd": run_dir, "prompt": prompt})
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, cwd=run_dir,
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
            if board_key:
                _BOARD_RUNNING.discard(board_key)

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


# --- archmap:// read resources + grill_candidate prompt ----------------------
# Registered ONCE here, after `mcp` and every tool/helper above is defined, so the
# resource/prompt modules can reuse the read tools' `_impl` helpers and the shared
# grilling text builder (single source of truth). The read TOOLS above are left
# unchanged — they remain the tools-only-client fallback. (Local imports avoid an
# import cycle: resources/prompts import this module.)
from . import resources as _resources  # noqa: E402
from . import prompts as _prompts      # noqa: E402

_resources.register(mcp)
_prompts.register(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":  # pragma: no cover — would start a live stdio server
    main()
