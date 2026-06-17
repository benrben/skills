"""Interface tests for the **Plan & WorkStep CRUD** module (model.py).

The error contract is part of the interface: duplicate plan ids and duplicate
step ids raise KeyError before anything is written, missing plans/steps raise
KeyError, update_plan rejects fields outside the editable whitelist with
ValueError, and delete_plan removes the plan or raises if absent. The happy
paths (create + step lifecycle) are crossed by test_tools_plan.py through the
dispatcher; these tests pin the model-level contract directly.
"""
import pytest

from arch_map.model import ArchModel, Plan, WorkStep


def plan(id="p1", **kw):
    return Plan(id=id, title=kw.pop("title", id), **kw)


def model():
    return ArchModel("repo", [])


# ---- plan CRUD errors --------------------------------------------------------

def test_create_duplicate_plan_raises():
    m = model()
    m.create_plan(plan())
    with pytest.raises(KeyError, match="already exists"):
        m.create_plan(plan())

def test_get_missing_plan_raises_with_next_step():
    m = model()
    with pytest.raises(KeyError, match="no plan 'ghost'"):
        m.get_plan("ghost")

def test_update_plan_rejects_non_editable_field():
    m = model()
    m.create_plan(plan())
    with pytest.raises(ValueError, match="cannot update"):
        m.update_plan("p1", steps=[])         # steps is managed, not editable
    assert m.plans["p1"].steps == []          # nothing written

def test_delete_plan_removes_then_missing_raises():
    m = model()
    m.create_plan(plan())
    m.delete_plan("p1")
    assert "p1" not in m.plans
    with pytest.raises(KeyError, match="no plan 'p1'"):
        m.delete_plan("p1")


# ---- work-step errors ----------------------------------------------------------

def test_add_work_steps_rejects_duplicate_step_ids():
    m = model()
    m.create_plan(plan())
    m.add_work_steps("p1", [WorkStep(id="s1", title="S")])
    with pytest.raises(KeyError, match="already exist"):
        m.add_work_steps("p1", [WorkStep(id="s1", title="again")])
    assert [s.id for s in m.plans["p1"].steps] == ["s1"]   # nothing appended

def test_set_step_status_finds_later_step():
    m = model()
    m.create_plan(plan())
    m.add_work_steps("p1", [WorkStep(id="s1", title="A"), WorkStep(id="s2", title="B")])
    m.set_step_status("p1", "s2", "in-progress")
    assert m.plans["p1"].steps[0].status == "todo"     # untouched
    assert m.plans["p1"].steps[1].status == "in-progress"

def test_set_step_status_missing_step_raises():
    m = model()
    m.create_plan(plan())
    with pytest.raises(KeyError, match="no step 's9' in plan 'p1'"):
        m.set_step_status("p1", "s9", "done")
