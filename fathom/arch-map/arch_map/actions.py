"""Studio action / dispatch / UI core — the mutation, headless-dispatch, and
studio-UI-path helpers shared by BOTH the MCP tools/resources AND the Starlette
/api/* routes (extracted from server.py per the server-cleanup plan, step s5).

This leaf is what lets the HTTP routes (web-routes, step s4) move out of server
without recreating a cycle: it imports only DOWNWARD (base/model/store/grill-text),
never server. server imports the names back — its docs() tool reuses _apply_doc and
its studio_ui/view_ui resources reuse _inline_app + the STUDIO_* constants — so
srv._apply_doc / srv.STUDIO_DIR resolve unchanged. web-routes will import them here.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .base import _running_keys
from .grill_text import _first_open, _grill_prompt
from .model import Doc, Module, Suggestion

if TYPE_CHECKING:                       # type-only — keeps this a leaf
    from .store import Store

HERE = Path(__file__).parent

# The unified studio assets (served over HTTP and inlined as the MCP-App resource).
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


# ONE dispatch helper for every doc mutation, called by BOTH the @mcp.tool docs()
# function AND the /api/docs route — so docs are the first citizen of the unified
# dispatch shape, NOT a fourth copy of the legacy triple-dispatch.
def _apply_doc(store: "Store", action: str, body: dict) -> None:
    if action == "add":
        store.add_doc(Doc.from_dict(body["doc"]))
    elif action == "update":
        store.update_doc(body["doc_id"], **body.get("fields", {}))
    elif action == "delete":
        store.delete_doc(body["doc_id"])
    else:
        raise ValueError(f"unknown doc action '{action}'")


# The studio (ui/studio/) is served from the same FastMCP app, same-origin with
# /api/maps + /api/model + /api/act. The browser POSTs every triage/edit to /api/act;
# this applier mutates maps/<id>.json under a lock.
def _apply_action(store: "Store", action: str, body: dict) -> None:
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


_DISPATCH_RUNNING: set = set()        # (map, kind, module) -> single-writer guard


def _step_of(store: "Store", plan_id: str, step_id: str):
    """The WorkStep (plan_id, step_id) or None — no raise (a dispatch must degrade)."""
    p = store.plans.get(plan_id) if plan_id else None
    return next((s for s in p.steps if s.id == step_id), None) if p else None


def _dispatch_prompt(store: "Store", map_id: str, kind: str, module: str = "",
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


# The graph UI (network.html) calls tools by their MCP name; dispatch them here
# so the same page works both as an MCP App (desktop) and served over HTTP.
def _call_tool(store: "Store", name: str, a: dict) -> None:
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
