"""Interface tests for the **MCP Tools + API — Docs slice** (server.py).

Two surfaces, ONE dispatch:
  * _apply_doc — the single doc-mutation core both the @mcp.tool functions and the
    /api/docs route call (no fourth copy of the legacy triple-dispatch). Tested
    directly: action -> Store effect + the unknown-action ValueError.
  * the /api/docs + /api/model routes via a Starlette TestClient — GET projection
    (resolvedModuleIds/drift/membership baked in), POST round-trip, error mapping.

The @mcp.tool wrappers aren't called directly (this FastMCP build wraps them into
non-callable FunctionTool objects — the same reason test_http_backend tests the
dispatch cores + routes, not the tool wrappers).
"""
import pytest

from arch_map.model import Module
from arch_map.server import _apply_doc, Store


def store_with_modules(tmp_path):
    s = Store(tmp_path / "m.json")
    s.add_module(Module(id="a", label="A", domain="ui", depth=0.5, size=1.0, seam=""))
    s.add_module(Module(id="b", label="B", domain="ui", depth=0.5, size=1.0, seam=""))
    s.add_module(Module(id="c", label="C", domain="srv", depth=0.5, size=1.0, seam=""))
    return s


# ---- _apply_doc (the single dispatch core) ----------------------------------

def test_apply_doc_add(tmp_path):
    s = store_with_modules(tmp_path)
    _apply_doc(s, "add", {"doc": {"id": "d1", "type": "rule", "title": "T",
                                  "scope": {"kind": "domain", "domain": "ui"}}})
    assert s.get_doc("d1")["resolvedModuleIds"] == ["a", "b"]

def test_apply_doc_update(tmp_path):
    s = store_with_modules(tmp_path)
    _apply_doc(s, "add", {"doc": {"id": "d1", "type": "note", "title": "T"}})
    _apply_doc(s, "update", {"doc_id": "d1", "fields": {"status": "current",
                                                        "scope": {"kind": "domain", "domain": "srv"}}})
    got = s.get_doc("d1")
    assert got["status"] == "current"
    assert got["resolvedModuleIds"] == ["c"]

def test_apply_doc_delete(tmp_path):
    s = store_with_modules(tmp_path)
    _apply_doc(s, "add", {"doc": {"id": "d1", "type": "note", "title": "T"}})
    _apply_doc(s, "delete", {"doc_id": "d1"})
    with pytest.raises(KeyError):
        s.get_doc("d1")

def test_apply_doc_unknown_action_raises(tmp_path):
    with pytest.raises(ValueError):
        _apply_doc(store_with_modules(tmp_path), "bogus", {})

def test_apply_doc_add_invalid_type_raises(tmp_path):
    with pytest.raises(ValueError):
        _apply_doc(store_with_modules(tmp_path), "add",
                   {"doc": {"id": "d1", "type": "memo", "title": "T"}})


# ---- /api/docs route (via TestClient) ---------------------------------------

def test_api_docs_post_add_then_get(reg, client):
    reg.create("m1", "M1")
    reg.store("m1").add_module(Module(id="a", label="A", domain="ui", depth=0.5, size=1.0, seam=""))
    r = client.post("/api/docs", json={"map": "m1", "op": "add",
                                       "doc": {"id": "d1", "type": "adr", "title": "Decision",
                                               "scope": {"kind": "domain", "domain": "ui"}}})
    assert r.status_code == 200
    # the POST returns the full model with the doc projected
    docs = {d["id"]: d for d in r.json()["docs"]}
    assert docs["d1"]["resolvedModuleIds"] == ["a"]
    # and GET /api/docs returns the same projection
    g = client.get("/api/docs?map=m1")
    assert g.status_code == 200
    assert g.json()["docMembership"]["a"] == ["d1"]

def test_api_docs_post_unknown_op_400(reg, client):
    reg.create("m1", "M1")
    r = client.post("/api/docs", json={"map": "m1", "op": "bogus"})
    assert r.status_code == 400
    assert "error" in r.json()

def test_api_docs_post_delete_round_trip(reg, client):
    reg.create("m1", "M1")
    client.post("/api/docs", json={"map": "m1", "op": "add",
                                   "doc": {"id": "d1", "type": "note", "title": "T"}})
    r = client.post("/api/docs", json={"map": "m1", "op": "delete", "doc_id": "d1"})
    assert r.status_code == 200
    assert r.json()["docs"] == []

def test_api_docs_get_missing_map_404(client):
    r = client.get("/api/docs?map=does-not-exist")
    assert r.status_code == 404


# ---- /api/model carries the baked doc projection ----------------------------

def test_api_model_bakes_doc_projection(reg, client):
    reg.create("m1", "M1")
    s = reg.store("m1")
    s.add_module(Module(id="a", label="A", domain="ui", depth=0.5, size=1.0, seam=""))
    s.add_module(Module(id="x", label="X", domain="ui", depth=0.5, size=1.0, seam=""))
    client.post("/api/docs", json={"map": "m1", "op": "add",
                                   "doc": {"id": "d1", "type": "rule", "title": "T",
                                           "scope": {"kind": "domain", "domain": "ui"}}})
    r = client.get("/api/model?map=m1")
    assert r.status_code == 200
    body = r.json()
    d1 = {d["id"]: d for d in body["docs"]}["d1"]
    assert d1["resolvedModuleIds"] == ["a", "x"]
    assert "scopeLabel" in d1 and "drift" in d1
    assert set(body["docMembership"]["a"]) == {"d1"}
