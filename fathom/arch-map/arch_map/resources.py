"""archmap:// read-only RESOURCES — the resource/full-MCP-client face of the
read tools (spec-spine-resources).

Every template here is READ-ONLY and returns JSON: it reuses the SAME payload
the equivalent archmap_* read tool builds (the `_impl` helpers and the store/
registry read methods in server.py — no projection logic is duplicated here) and
has NO side effects. Crucially it goes through ``REGISTRY.store(map)``, which
raises ``KeyError`` for an unknown map — it NEVER creates or ensures a map. A
missing map or id surfaces as a recoverable ``ResourceError`` rather than a
phantom empty map.

Resources are invisible to tools-only hosts; the archmap_* read tools stay the
fallback for those. ``register(mcp)`` is called once from server.py after the
tools are defined.
"""
from __future__ import annotations

from fastmcp.exceptions import ResourceError

from . import server as srv


def _recoverable(fn):
    """Run a payload builder, turning the read methods' KeyError/ValueError into a
    recoverable ResourceError (so a bad map/id is a clear, correctable message —
    never a phantom map and never a raw stack trace)."""
    try:
        return fn()
    except (KeyError, ValueError) as e:
        raise ResourceError(str(e).strip("'\"")) from e


def register(mcp) -> None:
    """Register the archmap:// read-only resource templates on `mcp`. Called once
    from server.py after `mcp` and the read tools are defined."""

    @mcp.resource("archmap://maps", mime_type="application/json")
    def maps() -> dict:
        """Every architecture map (id, repo label, module/proposal counts) — the
        archmap_list_maps payload."""
        all_maps = srv.REGISTRY.list()
        return {"maps": all_maps, "default": srv.REGISTRY.default_id(),
                "total_count": len(all_maps),
                "has_more": False, "next_offset": None}

    @mcp.resource("archmap://{map}/model", mime_type="application/json")
    def model(map: str) -> dict:
        """A map's full (bounded) model — the archmap_get_full_model payload."""
        return _recoverable(lambda: srv._get_full_model_impl(map, None, 0, 0))

    @mcp.resource("archmap://{map}/digest", mime_type="application/json")
    def digest(map: str) -> dict:
        """A map's digest — the archmap_show_map payload (counts, orphans, open
        suggestions, worst-health modules)."""
        return _recoverable(lambda: srv._show_map_impl(map, "", None))

    @mcp.resource("archmap://{map}/board", mime_type="application/json")
    def board(map: str) -> dict:
        """A map's task board — the archmap_board projection (the SAME projection
        the studio board renders)."""
        def run():
            out = srv.REGISTRY.store(map)._load().board(running=srv._running_keys(map))
            out["map"] = map
            return out
        return _recoverable(run)

    @mcp.resource("archmap://{map}/module/{id}", mime_type="application/json")
    def module(map: str, id: str) -> dict:
        """One module's full record — the archmap_modules(action='get', id=...)
        payload."""
        return _recoverable(lambda: srv.REGISTRY.store(map).get_module(id))

    @mcp.resource("archmap://{map}/doc/{id}", mime_type="application/json")
    def doc(map: str, id: str) -> dict:
        """One doc's full record (scope resolved) — the
        archmap_docs(action='get', doc_id=...) payload."""
        return _recoverable(lambda: srv.REGISTRY.store(map).get_doc(id))

    @mcp.resource("archmap://{map}/metrics/{module}", mime_type="application/json")
    def metrics(map: str, module: str) -> dict:
        """One module's computed graph metrics — the
        archmap_get_metrics(module=...) payload."""
        def run():
            model = srv.REGISTRY.store(map)._load()
            all_metrics = model.compute_metrics()
            if module not in model.modules:
                raise KeyError(f"no module '{module}' in map '{map}'. "
                               f"Read archmap://{map}/model to list module ids.")
            return {"map": map, "module": module, "metrics": all_metrics[module]}
        return _recoverable(run)
