"""Interface tests for the **MCP Tools — Plans + Work Steps** slice (server.py).

The intended-plane Plan/WorkStep write-slice fathom:plan and fathom:code own.
add_work_steps filters step dicts to WorkStep fields (silently drops unknowns);
realize_module flips plane intended->actual + lifecycle planned->built.
"""
import pytest

import arch_map.server as srv


def test_create_and_get_plan(reg):
    srv.plans(action="create", map="m", plan_id="p1", title="Plan One", intent="do X", moduleIds=["a"])
    plan = srv.plans(action="get", map="m", plan_id="p1")
    assert plan["id"] == "p1"
    assert plan["title"] == "Plan One"
    assert plan["moduleIds"] == ["a"]


def test_add_work_steps_drops_unknown_keys(reg):
    srv.plans(action="create", map="m", plan_id="p1", title="P")
    srv.plans(action="add_steps", map="m", plan_id="p1", steps=[
        {"id": "s1", "title": "Step one", "targets": ["a"], "bogus": "ignored"},
    ])
    step = srv.plans(action="get", map="m", plan_id="p1")["steps"][0]
    assert step["id"] == "s1"
    assert step["targets"] == ["a"]
    assert "bogus" not in step


def test_set_step_status_advances(reg):
    srv.plans(action="create", map="m", plan_id="p1", title="P")
    srv.plans(action="add_steps", map="m", plan_id="p1", steps=[{"id": "s1", "title": "S"}])
    srv.plans(action="set_step_status", map="m", plan_id="p1", step_id="s1", step_status="done")
    assert srv.plans(action="get", map="m", plan_id="p1")["steps"][0]["status"] == "done"


def test_update_plan_patches_editable_fields(reg):
    srv.plans(action="create", map="m", plan_id="p1", title="P")
    srv.plans(action="update", map="m", plan_id="p1", status="active", intent="new")
    plan = srv.plans(action="get", map="m", plan_id="p1")
    assert plan["status"] == "active"
    assert plan["intent"] == "new"


def test_realize_module_flips_plane_and_lifecycle(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    srv.modules(action="update", map="m", id="a", plane="intended", lifecycle="planned")
    srv.modules(action="realize", map="m", id="a", depth=0.9, coverage=0.5, files=["src/a.py"])
    rec = srv.modules(action="get", map="m", id="a")
    assert rec["plane"] == "actual"
    assert rec["lifecycle"] == "built"
    assert rec["depth"] == 0.9
    assert rec["coverage"] == 0.5
    assert rec["files"] == ["src/a.py"]
