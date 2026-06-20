"""Interface tests for the **task board projection** (model.board) and the worktree
CRUD it renders.

The board is the skill-cycle Kanban: columns are WORKSTEP_STAGES (each owned by a
Fathom skill), rows are agents, cards are WorkSteps carrying their per-task worktree.
Legacy 'blocked' status must project onto the `blocked` flag with no migration.
"""
import pytest

from arch_map.model import (ArchModel, Plan, WorkStep, Worktree, WORKSTEP_STAGES)


def model_with_steps(*steps, worktrees=()):
    m = ArchModel("repo", [])
    m.create_plan(Plan(id="p1", title="Orders"))
    m.add_work_steps("p1", list(steps))
    for w in worktrees:
        m.add_worktree(w)
    return m


def test_columns_are_the_skill_cycle():
    b = model_with_steps().board()
    assert b["columns"] == ["todo", "understand", "plan", "in-progress", "review", "done"]
    assert tuple(b["columns"]) == WORKSTEP_STAGES


def test_card_lands_in_its_status_column_and_counts():
    m = model_with_steps(
        WorkStep(id="s1", title="A", status="understand"),
        WorkStep(id="s2", title="B", status="in-progress"),
        WorkStep(id="s3", title="C", status="review"),
    )
    b = m.board()
    assert b["counts"]["understand"] == 1
    assert b["counts"]["in-progress"] == 1
    assert b["counts"]["review"] == 1
    assert b["counts"]["done"] == 0


def test_legacy_blocked_status_projects_to_todo_column_with_flag():
    # an existing map with status='blocked' loads untouched; the board flags it
    m = model_with_steps(WorkStep(id="s1", title="legacy", status="blocked"))
    card = m.board()["cards"][0]
    assert card["column"] == "todo"
    assert card["blocked"] is True


def test_blocked_flag_is_orthogonal_to_column():
    m = model_with_steps(WorkStep(id="s1", title="X", status="in-progress", blocked=True))
    card = m.board()["cards"][0]
    assert card["column"] == "in-progress"     # stays in its column
    assert card["blocked"] is True             # but is flagged


def test_lanes_group_by_agent_unassigned_last():
    m = model_with_steps(
        WorkStep(id="s1", title="A", agent="Explore"),
        WorkStep(id="s2", title="B", agent=""),          # unassigned
        WorkStep(id="s3", title="C", agent="Explore"),
    )
    lanes = m.board()["lanes"]
    agents = [l["agent"] for l in lanes]
    assert "Explore" in agents and "unassigned" in agents
    assert agents[-1] == "unassigned"                    # unassigned sinks to the bottom
    explore = next(l for l in lanes if l["agent"] == "Explore")
    assert len(explore["cards"]) == 2


def test_priority_orders_cards_within_the_board():
    m = model_with_steps(
        WorkStep(id="s1", title="low", priority="low"),
        WorkStep(id="s2", title="urgent", priority="urgent"),
        WorkStep(id="s3", title="normal", priority="normal"),
    )
    order = [c["stepId"] for c in m.board()["cards"]]
    assert order[0] == "s2"          # urgent first
    assert order[-1] == "s1"         # low last


def test_card_carries_its_worktree_and_running_flag():
    m = model_with_steps(
        WorkStep(id="s1", title="A", worktree="wt1"),
        worktrees=[Worktree(id="wt1", branch="feat/a", path="/tmp/a", planId="p1", stepId="s1")],
    )
    b = m.board(running={("p1", "s1")})
    card = b["cards"][0]
    assert card["worktree"]["branch"] == "feat/a"
    assert card["running"] is True
    assert b["worktrees"][0]["id"] == "wt1"


# ---- worktree CRUD the board reads ------------------------------------------

def test_add_worktree_back_references_the_step():
    m = model_with_steps(WorkStep(id="s1", title="A"))
    m.add_worktree(Worktree(id="wt1", branch="feat/a", planId="p1", stepId="s1"))
    assert m.plans["p1"].steps[0].worktree == "wt1"     # the step now points back


def test_delete_worktree_clears_the_step_link():
    m = model_with_steps(WorkStep(id="s1", title="A"))
    m.add_worktree(Worktree(id="wt1", branch="feat/a", planId="p1", stepId="s1"))
    m.delete_worktree("wt1")
    assert m.plans["p1"].steps[0].worktree == ""
    assert "wt1" not in m.worktrees


def test_link_step_worktree_sets_both_sides():
    m = model_with_steps(WorkStep(id="s1", title="A"))
    m.add_worktree(Worktree(id="wt1", branch="feat/a"))
    m.link_step_worktree("p1", "s1", "wt1")
    assert m.plans["p1"].steps[0].worktree == "wt1"
    assert m.worktrees["wt1"].stepId == "s1"


def test_set_step_fields_rejects_unknown_key():
    m = model_with_steps(WorkStep(id="s1", title="A"))
    with pytest.raises(ValueError, match="cannot update step"):
        m.set_step_fields("p1", "s1", bogus="x")
    m.set_step_fields("p1", "s1", agent="Explore", priority="high", blocked=True)
    s = m.plans["p1"].steps[0]
    assert (s.agent, s.priority, s.blocked) == ("Explore", "high", True)


def test_worktree_survives_json_round_trip(tmp_path):
    m = model_with_steps(
        WorkStep(id="s1", title="A", worktree="wt1", priority="high", agent="x"),
        worktrees=[Worktree(id="wt1", branch="feat/a", path="/tmp/a", stepId="s1")],
    )
    p = tmp_path / "m.json"
    m.save(p)
    m2 = ArchModel.from_json(p)
    assert m2.worktrees["wt1"].branch == "feat/a"
    assert m2.plans["p1"].steps[0].priority == "high"
    assert m2.board()["cards"][0]["worktree"]["branch"] == "feat/a"
