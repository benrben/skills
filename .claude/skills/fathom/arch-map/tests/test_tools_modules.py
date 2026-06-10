"""Interface tests for the **MCP Tools — Modules slice** (server.py).

The MODULES write-slice fathom:map owns: thin pass-throughs that resolve the map
via MapRegistry, delegate to ArchModel CRUD/mutation, and return the uniform ack
{ok, changed, repo, modules, orphans, openSuggestions}. Exercised against a temp
registry (the `reg` fixture).
"""
import pytest

import arch_map.server as srv

ACK_KEYS = {"ok", "changed", "repo", "modules", "orphans", "openSuggestions"}


def test_add_module_returns_uniform_ack(reg):
    ack = srv.modules(action="add", map="m", id="a", label="A", domain="d")   # ensure-creates the map
    assert ack["ok"] is True
    assert ACK_KEYS <= set(ack)
    assert ack["modules"] == 1


def test_get_and_update_and_delete_module(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    assert srv.modules(action="get", map="m", id="a")["id"] == "a"
    srv.modules(action="update", map="m", id="a", depth=0.9, iface="x")
    assert srv.modules(action="get", map="m", id="a")["depth"] == 0.9
    srv.modules(action="delete", map="m", id="a")
    with pytest.raises(KeyError):
        srv.modules(action="get", map="m", id="a")


def test_set_depth_coverage_churn_and_mark_updated(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    srv.modules(action="update", map="m", id="a", depth=0.7)
    srv.modules(action="update", map="m", id="a", coverage=0.6)
    srv.modules(action="update", map="m", id="a", churn=9.0)        # clamped to 1.0
    srv.modules(action="update", map="m", id="a", updated=False)
    rec = srv.modules(action="get", map="m", id="a")
    assert rec["depth"] == 0.7
    assert rec["coverage"] == 0.6
    assert rec["churn"] == 1.0
    assert rec["updated"] is False


def test_bulk_add_get_update_delete(reg):
    srv.modules(action="add", map="m", items=[
        {"id": "a", "label": "A", "domain": "d"},
        {"id": "b", "label": "B", "domain": "d", "dependsOn": ["a"]},
    ])
    got = srv.modules(action="get", map="m", ids=["a", "b"])["modules"]
    assert [r["id"] for r in got] == ["a", "b"]
    srv.modules(action="update", map="m", items=[{"id": "a", "depth": 0.95}])
    assert srv.modules(action="get", map="m", id="a")["depth"] == 0.95
    srv.modules(action="delete", map="m", ids=["a", "b"])
    assert srv.show_map(map="m")["modules"] == []


def test_store_tool_on_missing_map_raises(reg):
    with pytest.raises(KeyError):
        srv.modules(action="update", map="ghost", id="a", coverage=0.5)


def test_update_unknown_module_raises(reg):
    srv.create_project(name="M", map_id="m", repo="M")
    with pytest.raises(KeyError):
        srv.modules(action="update", map="m", id="ghost", depth=0.1)


def test_update_module_rejects_non_editable_field(reg):
    # modules(action="update") has no param for a non-editable field, so an unknown
    # kwarg is a TypeError at the tool boundary (the agent's schema can't even offer
    # it). The model-level _EDITABLE guard is still exercised via the bulk items path,
    # which takes raw dicts.
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    with pytest.raises(TypeError):
        srv.modules(action="update", map="m", id="a", bogus=1)
    with pytest.raises(ValueError):
        srv.modules(action="update", map="m", items=[{"id": "a", "bogus": 1}])
