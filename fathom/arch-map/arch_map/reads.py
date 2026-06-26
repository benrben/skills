"""Read PROJECTIONS — the shaping the archmap:// resources (resources.py), the
studio /api/* routes, and the interface tests all read through (extracted from
server.py per the server-cleanup plan / adr-surface-register-inversion).

These used to be @mcp.tool read tools; per spec-spine-resources the ONLY way an MCP
client reads stored state is now the archmap:// RESOURCES, which call straight into
these helpers — no projection logic is duplicated. They never auto-create a map: the
read goes through REGISTRY.store(map), which raises KeyError for an unknown id.

A leaf: it imports the shared runtime substrate (REGISTRY / _guard / the run-set /
the repo helpers) DOWNWARD from base.py, never from server. So resources.py imports
THIS module instead of reaching up into server — breaking the server<->resources
import cycle. server.py imports every name back, so srv.show_map / srv.board /
srv.get_full_model resolve unchanged for the routes and tests.
"""
from __future__ import annotations

from dataclasses import asdict
import os

from . import ledger
from .git_facts import GitFacts
from .worktrees import Worktrees
from .base import REGISTRY, _guard, _running_keys, _repo_root, _safe_git_worktrees


def list_maps(limit: int = 50, offset: int = 0) -> dict:
    """List the available architecture maps (id, repo label, module/proposal counts).
    Maps are shared — any agent can read or write any of them; pass the id as `map`.
    Use `limit` (default 50) and `offset` to page `maps`; the response carries
    total_count / has_more / next_offset. Read via resource archmap://maps{?q}."""
    def run():
        all_maps = REGISTRY.list()
        page = all_maps[offset:offset + limit] if limit and limit > 0 else all_maps[offset:]
        end = offset + limit if (limit and limit > 0) else len(all_maps)
        return {"maps": page, "default": REGISTRY.default_id(),
                "total_count": len(all_maps),
                "has_more": end < len(all_maps),
                "next_offset": end if end < len(all_maps) else None}
    return _guard("archmap://maps", False, "", run)


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


def get_metrics(map: str, module: str | None = None,
                        limit: int = 50, offset: int = 0) -> dict:
    """Return computed graph metrics for one module or all modules in `map`:
    fanIn, fanOut, instability, blastRadius, coupling, inCycle, health, churn.
    These are derived from the dependency graph — no extra data needed.

    Pass `module` for a single module's metrics. With no `module`, returns a page of
    all modules' metrics (keyed by id, ordered by id) — use `limit` (default 50) and
    `offset` to page; the response carries total_count / has_more / next_offset."""
    call = "archmap://{map}/metrics"
    hint = "Read maps via resource archmap://maps, or create one with archmap_create_map."

    def run():
        model = REGISTRY.store(map)._load()
        all_metrics = model.compute_metrics()
        if module:
            if module not in model.modules:
                raise KeyError(f"no module '{module}' in map '{map}'. "
                               f"Read archmap://{map}/metrics for all modules, or "
                               f"archmap://{map}/model to list module ids.")
            return {"map": map, "module": module, "metrics": all_metrics[module]}
        ids = sorted(all_metrics)
        page = ids[offset:offset + limit] if limit and limit > 0 else ids[offset:]
        end = offset + limit if (limit and limit > 0) else len(ids)
        return {"map": map,
                "metrics": {mid: all_metrics[mid] for mid in page},
                "total_count": len(ids),
                "has_more": end < len(ids),
                "next_offset": end if end < len(ids) else None}
    return _guard(call, False, hint, run)


def get_module(map: str, id: str) -> dict:
    """One module's full record — backs resource archmap://{map}/module/{id}."""
    return REGISTRY.store(map).get_module(id)


def get_modules(map: str, ids: list[str]) -> dict:
    """Several modules' records by id — used by the model resource + tests."""
    return {"map": map, "modules": REGISTRY.store(map).get_modules(ids)}


def get_plan(map: str, plan_id: str) -> dict:
    """One plan's full record — backs resource archmap://{map}/plan/{id}."""
    return REGISTRY.store(map).get_plan(plan_id)


def list_plans(map: str, status: str = "") -> dict:
    """The plans list (view projection) — backs archmap://{map}/plans{?status}.
    Optional exact status filter (draft|active|done|abandoned)."""
    v = REGISTRY.store(map).to_view()
    plans = v.get("plans", [])
    if status:
        plans = [p for p in plans if p.get("status") == status]
    return {"map": map, "plans": plans}


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


def list_worktrees(map: str, status: str = "", root: str = "") -> dict:
    """Spine worktrees + the live `git worktree list` — backs archmap://{map}/worktrees.
    The resource surfaces only the STORED `worktrees`; gitWorktrees is the computed
    companion the studio/tests also read. Optional exact status filter."""
    model = REGISTRY.store(map)._load()
    wts = [asdict(w) for w in model.worktrees.values()]
    if status:
        wts = [w for w in wts if w.get("status") == status]
    return {"map": map, "worktrees": wts,
            "gitWorktrees": _safe_git_worktrees(Worktrees(_repo_root(root)))}


def get_doc(map: str, doc_id: str) -> dict:
    """One doc's full record (scope resolved) — backs archmap://{map}/doc/{id}."""
    return REGISTRY.store(map).get_doc(doc_id)


_DOC_SUMMARY_KEYS = ("id", "type", "title", "summary", "status", "tags",
                     "author", "scopeLabel", "drift")


def list_docs(map: str, include_membership: bool = False,
              limit: int = 50, offset: int = 0) -> dict:
    """The slim doc summaries (no bodies), paged — backs archmap://{map}/docs.
    include_membership adds the moduleId->docIds map."""
    d = REGISTRY.store(map).to_dict()
    slim = [{**{k: doc.get(k) for k in _DOC_SUMMARY_KEYS},
             "moduleCount": len(doc.get("resolvedModuleIds") or [])}
            for doc in d["docs"]]
    page = slim[offset:offset + limit] if limit and limit > 0 else slim[offset:]
    end = offset + limit if (limit and limit > 0) else len(slim)
    out = {"map": map, "docs": page,
           "total_count": len(slim),
           "has_more": end < len(slim),
           "next_offset": end if end < len(slim) else None}
    if include_membership:
        out["docMembership"] = d["docMembership"]
    return out
