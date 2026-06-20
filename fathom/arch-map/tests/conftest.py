"""Shared fixtures for the server-layer tests.

The @mcp.tool functions and the HTTP routes both read the module-level REGISTRY
at call time, so pointing srv.REGISTRY at a throwaway directory lets us exercise
the real tool/route code against disposable maps — never the real maps/ dir.
"""
import pytest

import arch_map.server as srv
import arch_map.map_registry as mr

# FastMCP 3.x's @mcp.tool / @mcp.resource bind a FunctionTool / FunctionResource
# wrapper (not the raw function) under pytest, so calling srv.<tool>(...) directly —
# as every tool/resource test does — raises "'FunctionTool' object is not callable".
# Unwrap each fastmcp-wrapped binding back to its underlying .fn ONCE at import so the
# tests exercise the real function. The MCP registration is untouched: it lives in
# mcp's provider registry, not in these module bindings.
for _name, _obj in list(vars(srv).items()):
    if type(_obj).__module__.startswith("fastmcp") and callable(getattr(_obj, "fn", None)):
        setattr(srv, _name, _obj.fn)


@pytest.fixture
def reg(tmp_path, monkeypatch):
    """A temp MapRegistry wired into the server module (legacy migration disabled)."""
    monkeypatch.setattr(mr, "LEGACY_STATE", tmp_path / "no-legacy.json")
    registry = srv.MapRegistry(tmp_path / "maps")
    monkeypatch.setattr(srv, "REGISTRY", registry)
    return registry


@pytest.fixture
def client(reg):
    """Starlette TestClient over the FastMCP app, with REGISTRY already pointed at
    a temp dir (routes resolve REGISTRY per request, so this composes with reg)."""
    from starlette.testclient import TestClient
    with TestClient(srv.mcp.http_app()) as c:
        yield c
