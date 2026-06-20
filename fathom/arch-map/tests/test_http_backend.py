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


# ---- remaining _apply_action / _call_tool branches ----------------------------

def test_apply_action_request_grilling_and_update(tmp_path):
    from arch_map.model import Suggestion
    s = store_with_a(tmp_path)
    s.add_suggestion("a", Suggestion("a-strong", "T", "Strong", "in-process", "p", "sol"))
    _apply_action(s, "request_grilling", {"suggestion_id": "a-strong"})
    assert s.get_module("a")["suggestions"][0]["status"] == "requested"
    _apply_action(s, "update", {"module": "a", "fields": {"label": "A2"}})
    assert s.get_module("a")["label"] == "A2"

def test_apply_action_plan_steps(tmp_path):
    from arch_map.model import Plan, WorkStep
    s = store_with_a(tmp_path)
    s.create_plan(Plan(id="p1", title="P"))
    s.add_work_steps("p1", [WorkStep(id="s1", title="S")])
    _apply_action(s, "set_step_status", {"plan_id": "p1", "step_id": "s1", "status": "done"})
    assert s.get_plan("p1")["steps"][0]["status"] == "done"
    _apply_action(s, "update_plan", {"plan_id": "p1", "fields": {"status": "active"}})
    assert s.get_plan("p1")["status"] == "active"

def test_call_tool_module_mutations(tmp_path):
    s = store_with_a(tmp_path)
    _call_tool(s, "set_depth", {"module": "a", "score": 0.8})
    assert s.get_module("a")["depth"] == 0.8
    _call_tool(s, "update_module", {"module": "a", "fields": {"label": "A2"}})
    assert s.get_module("a")["label"] == "A2"
    _call_tool(s, "delete_module", {"module": "a"})
    assert "a" not in s.modules

def test_call_tool_suggestion_lifecycle(tmp_path):
    from arch_map.model import Suggestion
    s = store_with_a(tmp_path)
    s.add_suggestion("a", Suggestion("a-strong", "T", "Strong", "in-process", "p", "sol"))
    _call_tool(s, "request_grilling", {"suggestion_id": "a-strong"})
    assert s.get_module("a")["suggestions"][0]["status"] == "requested"
    _call_tool(s, "mark_grilled", {"suggestion_id": "a-strong"})
    assert s.get_module("a")["suggestions"][0]["status"] == "grilled"
    _call_tool(s, "decide", {"suggestion_id": "a-strong", "decision": "accepted"})
    assert s.get_module("a")["suggestions"][0]["decision"] == "accepted"
    _call_tool(s, "resolve", {"suggestion_id": "a-strong"})
    assert s.get_module("a")["suggestions"][0]["status"] == "done"

def test_call_tool_start_grilling_persists_request(tmp_path):
    from arch_map.model import Suggestion
    s = store_with_a(tmp_path)
    s.add_suggestion("a", Suggestion("a-strong", "T", "Strong", "in-process", "p", "sol"))
    _call_tool(s, "start_grilling", {"module": "a"})
    assert s.get_module("a")["suggestions"][0]["status"] == "requested"
    _call_tool(s, "start_grilling", {})              # no module -> persists nothing
    _call_tool(s, "start_grilling", {"module": "a"}) # already requested -> still open, idempotent


# ---- pages + assets ------------------------------------------------------------

def test_pages_serve_studio_and_view(client):
    assert client.get("/").status_code == 200
    assert client.get("/map").status_code == 200      # back-compat alias -> studio
    assert client.get("/view").status_code == 200


# ---- /api/dispatch guards (CSRF + enable gate) — neither path spawns an agent ----

def test_api_dispatch_cross_origin_refused(reg, client):
    # a foreign web page must NOT be able to drive the loopback agent button
    r = client.post("/api/dispatch", json={"map": "m1", "kind": "rescan", "module": "a"},
                    headers={"origin": "http://evil.example"})
    assert r.status_code == 403
    assert "cross-origin" in r.json()["error"]

def test_api_dispatch_disabled_falls_back(reg, client, monkeypatch):
    # dispatch is OFF by default (opt-in); ARCH_MAP_ALLOW_DISPATCH=0 keeps it off
    # -> 503 + copy-paste prompt (set explicitly so the test is independent of env)
    monkeypatch.setenv("ARCH_MAP_ALLOW_DISPATCH", "0")
    reg.create("m1", "M1")
    r = client.post("/api/dispatch", json={"map": "m1", "kind": "rescan", "module": "a"})
    assert r.status_code == 503
    body = r.json()
    assert body["fallback"] is True and body["reason"] == "dispatch-disabled" and "Re-scan" in body["prompt"]

def test_assets_served_with_content_type_and_traversal_refused(client):
    ok = client.get("/assets/shared/ui.css")
    assert ok.status_code == 200
    assert "text/css" in ok.headers["content-type"]
    assert client.get("/assets/missing.css").status_code == 404
    assert client.get("/assets/..%2f..%2fserver.py").status_code == 404  # contained


# ---- /api/maps lifecycle ---------------------------------------------------------

def test_api_maps_lifecycle_over_http(client):
    r = client.post("/api/maps", json={"op": "create", "map": "Web Map"})
    assert r.status_code == 200 and r.json()["created"] == "web-map"
    r2 = client.post("/api/maps", json={"op": "rename", "map": "web-map", "to": "Web 2"})
    assert r2.status_code == 200 and r2.json()["created"] == "web-2"
    assert client.post("/api/maps", json={"op": "delete", "map": "web-2"}).status_code == 200
    assert client.post("/api/maps", json={"op": "create", "map": ""}).status_code == 400
    assert client.post("/api/maps", json={"op": "bogus"}).status_code == 400


# ---- /api/view -------------------------------------------------------------------

def test_api_view_shapes_table_and_bar(reg, client):
    reg.create("m", "M")
    reg.store("m").add_module(Module(id="a", label="A", domain="d", depth=0.5, size=1.0, seam=""))
    t = client.get("/api/view", params={"map": "m", "columns": "id,depth", "sort": "depth"})
    assert t.status_code == 200 and t.json()["kind"] == "table"
    b = client.get("/api/view", params={"map": "m", "kind": "bar", "metric": "coverage",
                                        "group": "domain"})
    assert b.status_code == 200 and b.json()["kind"] == "bar"
    assert client.get("/api/view", params={"map": "ghost"}).status_code == 404
    assert client.get("/api/view", params={"map": "m", "kind": "bogus"}).status_code == 400


# ---- /api/grill + /api/tool error mapping ------------------------------------------

def test_api_grill_persists_request_and_returns_prompt(reg, client):
    from arch_map.model import Suggestion
    reg.create("m", "M")
    s = reg.store("m")
    s.add_module(Module(id="a", label="A", domain="d", depth=0.5, size=1.0, seam=""))
    s.add_suggestion("a", Suggestion("a-strong", "T", "Strong", "in-process", "p", "sol"))
    r = client.post("/api/grill", json={"map": "m", "module": "a"})
    body = r.json()
    assert body["ok"] is True
    assert body["resume"] == "/deepen resume m"
    assert "prompt" in body and "model" in body
    assert s.get_module("a")["suggestions"][0]["status"] == "requested"  # persisted
    assert client.post("/api/grill", json={"map": "m", "module": "ghost"}).status_code == 400
    s.add_module(Module(id="b", label="B", domain="d", depth=0.5, size=1.0, seam=""))
    bare = client.post("/api/grill", json={"map": "m", "module": "b"})   # no open candidate
    assert bare.status_code == 200 and "prompt" in bare.json()

def test_api_tool_unknown_name_400(reg, client):
    reg.create("m", "M")
    r = client.post("/api/tool", json={"map": "m", "name": "bogus", "arguments": {}})
    assert r.status_code == 400
    assert "unknown tool" in r.json()["error"]


# ---- stdio entrypoint ----------------------------------------------------------------

def test_server_main_runs_mcp(monkeypatch):
    import arch_map.server as srv
    calls = []
    monkeypatch.setattr(srv.mcp, "run", lambda *a, **k: calls.append((a, k)))
    srv.main()
    assert calls == [((), {})]
