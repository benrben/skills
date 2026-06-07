"""Interface tests for the **MCP Tools — Plans + Work Steps** slice (server.py).

The intended-plane Plan/WorkStep write-slice fathom:plan and fathom:code own.
add_work_steps filters step dicts to WorkStep fields (silently drops unknowns);
realize_module flips plane intended->actual + lifecycle planned->built.
"""
import pytest

import arch_map.server as srv


def test_create_and_get_plan(reg):
    srv.create_plan(map="m", id="p1", title="Plan One", intent="do X", moduleIds=["a"])
    plan = srv.get_plan(map="m", plan_id="p1")
    assert plan["id"] == "p1"
    assert plan["title"] == "Plan One"
    assert plan["moduleIds"] == ["a"]


def test_add_work_steps_drops_unknown_keys(reg):
    srv.create_plan(map="m", id="p1", title="P")
    srv.add_work_steps(map="m", plan_id="p1", steps=[
        {"id": "s1", "title": "Step one", "targets": ["a"], "bogus": "ignored"},
    ])
    step = srv.get_plan(map="m", plan_id="p1")["steps"][0]
    assert step["id"] == "s1"
    assert step["targets"] == ["a"]
    assert "bogus" not in step


def test_set_step_status_advances(reg):
    srv.create_plan(map="m", id="p1", title="P")
    srv.add_work_steps(map="m", plan_id="p1", steps=[{"id": "s1", "title": "S"}])
    srv.set_step_status(map="m", plan_id="p1", step_id="s1", status="done")
    assert srv.get_plan(map="m", plan_id="p1")["steps"][0]["status"] == "done"


def test_update_plan_patches_editable_fields(reg):
    srv.create_plan(map="m", id="p1", title="P")
    srv.update_plan(map="m", plan_id="p1", fields={"status": "active", "intent": "new"})
    plan = srv.get_plan(map="m", plan_id="p1")
    assert plan["status"] == "active"
    assert plan["intent"] == "new"


def test_realize_module_flips_plane_and_lifecycle(reg):
    srv.add_module(map="m", id="a", label="A", domain="d")
    srv.update_module(map="m", module="a", fields={"plane": "intended", "lifecycle": "planned"})
    srv.realize_module(map="m", module="a", depth=0.9, coverage=0.5, files=["src/a.py"])
    rec = srv.get_module(map="m", module="a")
    assert rec["plane"] == "actual"
    assert rec["lifecycle"] == "built"
    assert rec["depth"] == 0.9
    assert rec["coverage"] == 0.5
    assert rec["files"] == ["src/a.py"]
