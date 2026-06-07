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
    ack = srv.add_module(map="m", id="a", label="A", domain="d")   # ensure-creates the map
    assert ack["ok"] is True
    assert ACK_KEYS <= set(ack)
    assert ack["modules"] == 1


def test_get_and_update_and_delete_module(reg):
    srv.add_module(map="m", id="a", label="A", domain="d")
    assert srv.get_module(map="m", module="a")["id"] == "a"
    srv.update_module(map="m", module="a", fields={"depth": 0.9, "iface": "x"})
    assert srv.get_module(map="m", module="a")["depth"] == 0.9
    srv.delete_module(map="m", module="a")
    with pytest.raises(KeyError):
        srv.get_module(map="m", module="a")


def test_set_depth_coverage_churn_and_mark_updated(reg):
    srv.add_module(map="m", id="a", label="A", domain="d")
    srv.set_depth(map="m", module="a", score=0.7)
    srv.set_coverage(map="m", module="a", fraction=0.6)
    srv.set_churn(map="m", module="a", churn=9.0)        # clamped to 1.0
    srv.mark_updated(map="m", module="a", updated=False)
    rec = srv.get_module(map="m", module="a")
    assert rec["depth"] == 0.7
    assert rec["coverage"] == 0.6
    assert rec["churn"] == 1.0
    assert rec["updated"] is False


def test_bulk_add_get_update_delete(reg):
    srv.add_modules(map="m", modules=[
        {"id": "a", "label": "A", "domain": "d"},
        {"id": "b", "label": "B", "domain": "d", "dependsOn": ["a"]},
    ])
    got = srv.get_modules(map="m", modules=["a", "b"])["modules"]
    assert [r["id"] for r in got] == ["a", "b"]
    srv.update_modules(map="m", updates=[{"id": "a", "depth": 0.95}])
    assert srv.get_module(map="m", module="a")["depth"] == 0.95
    srv.delete_modules(map="m", modules=["a", "b"])
    assert srv.show_map(map="m")["modules"] == []


def test_store_tool_on_missing_map_raises(reg):
    with pytest.raises(KeyError):
        srv.set_coverage(map="ghost", module="a", fraction=0.5)


def test_update_unknown_module_raises(reg):
    srv.create_map(map="m", repo="M")
    with pytest.raises(KeyError):
        srv.update_module(map="m", module="ghost", fields={"depth": 0.1})


def test_update_module_rejects_non_editable_field(reg):
    srv.add_module(map="m", id="a", label="A", domain="d")
    with pytest.raises(ValueError):
        srv.update_module(map="m", module="a", fields={"bogus": 1})
