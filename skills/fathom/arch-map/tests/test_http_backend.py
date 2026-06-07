"""Interface tests for the **HTTP + MCP-App Backend** module (server.py).

Two surfaces:
  * the dispatch cores _apply_action (/api/act) and _call_tool (/api/tool) —
    the "parallel adapters" that re-implement the mutation surface directly
    against Store. Tested directly: action/tool name -> Store effect + the
    unknown-name ValueError.
  * the HTTP routes themselves, via a Starlette TestClient — status/error
    mapping (KeyError/ValueError -> 404/400) and a real mutation round-trip.

NOTE: the open `http-backend-strong` candidate will unify these three dispatchers
behind one seam. These tests assert *behaviour* (name -> effect), which the
unified dispatcher must preserve, so they should survive that refactor.
"""
import pytest

from arch_map.model import Module
from arch_map.server import _apply_action, _call_tool, Store


def store_with_a(tmp_path):
    s = Store(tmp_path / "m.json")
    s.add_module(Module(id="a", label="A", domain="d", depth=0.5, size=1.0, seam=""))
    return s


# ---- _apply_action (the /api/act dispatch core) -----------------------------

def test_apply_action_set_depth(tmp_path):
    s = store_with_a(tmp_path)
    _apply_action(s, "set_depth", {"module": "a", "score": 0.9})
    assert s.get_module("a")["depth"] == 0.9

def test_apply_action_set_coverage(tmp_path):
    s = store_with_a(tmp_path)
    _apply_action(s, "set_coverage", {"module": "a", "fraction": 0.4})
    assert s.get_module("a")["coverage"] == 0.4

def test_apply_action_add_and_delete(tmp_path):
    s = store_with_a(tmp_path)
    _apply_action(s, "add", {"module": {"id": "b", "label": "B", "domain": "d"}})
    assert "b" in s.modules
    _apply_action(s, "delete", {"module": "b"})
    assert "b" not in s.modules

def test_apply_action_decide_and_resolve(tmp_path):
    from arch_map.model import Suggestion
    s = store_with_a(tmp_path)
    s.add_suggestion("a", Suggestion("a-strong", "T", "Strong", "in-process", "p", "sol"))
    _apply_action(s, "decide", {"suggestion_id": "a-strong", "decision": "accepted"})
    assert s.get_module("a")["suggestions"][0]["decision"] == "accepted"
    _apply_action(s, "resolve", {"suggestion_id": "a-strong"})
    assert s.get_module("a")["suggestions"][0]["status"] == "done"

def test_apply_action_unknown_raises(tmp_path):
    with pytest.raises(ValueError):
        _apply_action(store_with_a(tmp_path), "bogus", {})


# ---- _call_tool (the /api/tool dispatch core) -------------------------------

def test_call_tool_set_coverage(tmp_path):
    s = store_with_a(tmp_path)
    _call_tool(s, "set_coverage", {"module": "a", "fraction": 0.6})
    assert s.get_module("a")["coverage"] == 0.6

def test_call_tool_add_module_from_arguments(tmp_path):
    s = store_with_a(tmp_path)
    _call_tool(s, "add_module", {"id": "b", "label": "B", "domain": "d"})
    assert "b" in s.modules

def test_call_tool_unknown_raises(tmp_path):
    with pytest.raises(ValueError):
        _call_tool(store_with_a(tmp_path), "bogus", {})


# ---- HTTP routes (via TestClient) -------------------------------------------

def test_api_maps_get(client):
    r = client.get("/api/maps")
    assert r.status_code == 200
    assert set(r.json()) >= {"maps", "default"}

def test_api_model_missing_map_404(client):
    r = client.get("/api/model?map=does-not-exist")
    assert r.status_code == 404
    assert "error" in r.json()

def test_api_model_ok(reg, client):
    reg.create("m1", "M1")
    r = client.get("/api/model?map=m1")
    assert r.status_code == 200
    assert r.json()["repo"] == "M1"

def test_api_act_add_mutates_and_returns_model(reg, client):
    reg.create("m1", "M1")
    r = client.post("/api/act", json={
        "map": "m1", "action": "add",
        "module": {"id": "x", "label": "X", "domain": "d"}})
    assert r.status_code == 200
    assert "x" in {m["id"] for m in r.json()["modules"]}

def test_api_act_unknown_action_400(reg, client):
    reg.create("m1", "M1")
    r = client.post("/api/act", json={"map": "m1", "action": "bogus"})
    assert r.status_code == 400
    assert "error" in r.json()

def test_api_tool_set_coverage_round_trip(reg, client):
    reg.create("m1", "M1")
    reg.store("m1").add_module(Module(id="x", label="X", domain="d", depth=0.5, size=1.0, seam=""))
    r = client.post("/api/tool", json={
        "map": "m1", "name": "set_coverage",
        "arguments": {"module": "x", "fraction": 0.5}})
    assert r.status_code == 200
    cov = {m["id"]: m["coverage"] for m in r.json()["modules"]}
    assert cov["x"] == 0.5

def test_api_maps_create(client):
    r = client.post("/api/maps", json={"op": "create", "map": "fresh", "repo": "Fresh"})
    assert r.status_code == 200
    assert r.json()["created"] == "fresh"
