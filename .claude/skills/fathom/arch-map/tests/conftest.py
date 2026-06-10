"""Shared fixtures for the server-layer tests.

The @mcp.tool functions and the HTTP routes both read the module-level REGISTRY
at call time, so pointing srv.REGISTRY at a throwaway directory lets us exercise
the real tool/route code against disposable maps — never the real maps/ dir.
"""
import pytest

import arch_map.server as srv


@pytest.fixture
def reg(tmp_path, monkeypatch):
    """A temp MapRegistry wired into the server module (legacy migration disabled)."""
    monkeypatch.setattr(srv, "LEGACY_STATE", tmp_path / "no-legacy.json")
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
