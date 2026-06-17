"""Interface tests for the **MCP Tools — Map lifecycle** slice (server.py).

The lifecycle + read surface every skill bootstraps through: list_maps,
create_project (slugs a human name, or takes an explicit map_id), rename_map,
delete_map, show_map (lightweight view), get_full_model (full dict).
"""
import pytest

import arch_map.server as srv


def test_list_maps_shape(reg):
    out = srv.list_maps()
    assert {"maps", "default", "total_count", "has_more", "next_offset"} <= set(out)
    assert out["maps"] == []                    # temp registry starts empty
    assert out["total_count"] == 0
    assert out["has_more"] is False
    assert out["next_offset"] is None


def test_list_maps_paginates(reg):
    srv.create_project(name="A", map_id="a")
    srv.create_project(name="B", map_id="b")
    srv.create_project(name="C", map_id="c")
    first = srv.list_maps(limit=2, offset=0)
    assert first["total_count"] == 3
    assert len(first["maps"]) == 2
    assert first["has_more"] is True
    assert first["next_offset"] == 2
    last = srv.list_maps(limit=2, offset=2)
    assert len(last["maps"]) == 1
    assert last["has_more"] is False
    assert last["next_offset"] is None


def test_create_project_explicit_map_id_and_repo(reg):
    # the explicit-id path that create_map used to own now lives in create_project
    ack = srv.create_project(name="Project", map_id="proj", repo="Project")
    assert ack["map"] == "proj"
    assert ack["repo"] == "Project"
    assert reg.exists("proj")


def test_create_project_slugs_name_and_returns_map_id(reg):
    ack = srv.create_project(name="Mr. Meeseeks")
    assert ack["map"] == "mr-meeseeks"          # slugged id to pass onward
    assert ack["repo"] == "Mr. Meeseeks"        # human label preserved
    assert ack["ok"] is True


def test_create_map_with_explicit_id_and_repo(reg):
    ack = srv.create_project(name="Project", map_id="proj", repo="Project")
    assert ack["repo"] == "Project"
    assert reg.exists("proj")


def test_rename_map_slugs_target(reg):
    srv.create_project(name="Old", map_id="old", repo="Old")
    srv.rename_map(map="old", to="Brand New")
    assert not reg.exists("old")
    assert reg.exists("brand-new")


def test_delete_map_returns_remaining(reg):
    srv.create_project(name="A", map_id="a", repo="A")
    srv.create_project(name="B", map_id="b", repo="B")
    out = srv.delete_map(map="a")
    assert out["deleted"] == "a"
    assert "a" not in out["maps"] and "b" in out["maps"]


def test_show_map_returns_digest_with_map_id(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    v = srv.show_map(map="m")
    assert v["map"] == "m"
    assert v["moduleCount"] == 1
    assert v["domains"] == {"d": 1}
    assert "modules" not in v                       # digest, not the full record list
    assert [w["id"] for w in v["worstHealth"]] == ["a"]


def test_show_map_domain_and_ids_filters_return_records(reg):
    srv.modules(action="add", map="m", items=[
        {"id": "a", "label": "A", "domain": "d1"},
        {"id": "b", "label": "B", "domain": "d2"},
    ])
    by_domain = srv.show_map(map="m", domain="d1")
    assert [mod["id"] for mod in by_domain["modules"]] == ["a"]
    by_ids = srv.show_map(map="m", ids=["b"])
    assert [mod["id"] for mod in by_ids["modules"]] == ["b"]
    assert by_ids["count"] == 1


def test_get_model_returns_full_dict(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    full = srv.get_full_model(map="m")
    assert full["map"] == "m"
    assert {"repo", "modules", "plans", "orphans", "openSuggestions"} <= set(full)
