"""Interface tests for the **MCP Tools — Map lifecycle** slice (server.py).

The lifecycle + read surface every skill bootstraps through: list_maps,
create_project (slugs a human name), create_map (explicit id), rename_map,
delete_map, show_map (lightweight view), get_model (full dict).
"""
import pytest

import arch_map.server as srv


def test_list_maps_shape(reg):
    out = srv.list_maps()
    assert set(out) == {"maps", "default"}
    assert out["maps"] == []                    # temp registry starts empty


def test_create_project_slugs_name_and_returns_map_id(reg):
    ack = srv.create_project(name="Mr. Meeseeks")
    assert ack["map"] == "mr-meeseeks"          # slugged id to pass onward
    assert ack["repo"] == "Mr. Meeseeks"        # human label preserved
    assert ack["ok"] is True


def test_create_map_with_explicit_id_and_repo(reg):
    ack = srv.create_map(map="proj", repo="Project")
    assert ack["repo"] == "Project"
    assert reg.exists("proj")


def test_rename_map_slugs_target(reg):
    srv.create_map(map="old", repo="Old")
    srv.rename_map(map="old", to="Brand New")
    assert not reg.exists("old")
    assert reg.exists("brand-new")


def test_delete_map_returns_remaining(reg):
    srv.create_map(map="a", repo="A")
    srv.create_map(map="b", repo="B")
    out = srv.delete_map(map="a")
    assert out["deleted"] == "a"
    assert "a" not in out["maps"] and "b" in out["maps"]


def test_show_map_returns_view_with_map_id(reg):
    srv.add_module(map="m", id="a", label="A", domain="d")
    v = srv.show_map(map="m")
    assert v["map"] == "m"
    assert [mod["id"] for mod in v["modules"]] == ["a"]


def test_get_model_returns_full_dict(reg):
    srv.add_module(map="m", id="a", label="A", domain="d")
    full = srv.get_model(map="m")
    assert full["map"] == "m"
    assert {"repo", "modules", "plans", "orphans", "openSuggestions"} <= set(full)
