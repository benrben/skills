"""Interface tests for the **MCP Tools — Worktrees + Board** slice (server.py).

archmap_worktrees provisions per-task isolated branches (real git, guarded) and
records them on the spine; archmap_board projects WorkSteps into the skill-cycle
Kanban. create degrades to a copy-paste `command` when real exec is disabled.
"""
import subprocess

import pytest

import arch_map.server as srv


def _git(root, *args):
    subprocess.run(["git", "-C", str(root),
                    "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false", *args],
                   check=True, capture_output=True, text=True)


@pytest.fixture
def gitrepo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "a.py").write_text("print(1)\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "c1")
    return r


@pytest.fixture
def wt_dir(tmp_path, monkeypatch):
    """Pin the worktree checkout dir so created worktrees land in a temp location."""
    d = tmp_path / "worktrees"
    monkeypatch.setenv("ARCH_MAP_WORKTREE_DIR", str(d))
    return d


def _plan_with_step(reg):
    srv.plans(action="create", map="m", plan_id="p1", title="P")
    srv.plans(action="add_steps", map="m", plan_id="p1",
              steps=[{"id": "s1", "title": "Build pricing", "targets": ["pricing"]}])


# ---- create: real git, records + links the step -----------------------------

def test_create_provisions_and_records(reg, gitrepo, wt_dir, monkeypatch):
    monkeypatch.setenv("ARCH_MAP_ALLOW_WORKTREE", "1")
    _plan_with_step(reg)
    out = srv.worktrees(action="create", map="m", branch="feat/pricing",
                        plan_id="p1", step_id="s1", agent="fathom:code", root=str(gitrepo))
    assert out["provisioned"] is True
    assert out["worktree"]["branch"] == "feat/pricing"
    # real git knows about it
    listed = srv.list_worktrees(map="m", root=str(gitrepo))
    assert "feat/pricing" in [g["branch"] for g in listed["gitWorktrees"]]
    # the spine linked it back onto the card
    assert srv.get_plan(map="m", plan_id="p1")["steps"][0]["worktree"] == out["worktree"]["id"]


def test_create_derives_branch_from_step(reg, gitrepo, wt_dir):
    _plan_with_step(reg)
    out = srv.worktrees(action="create", map="m", step_id="s1", plan_id="p1", root=str(gitrepo))
    assert out["worktree"]["branch"] == "feat/s1"          # feat/<slug(step_id)>


def test_create_disabled_falls_back_to_command(reg, gitrepo, wt_dir, monkeypatch):
    monkeypatch.setenv("ARCH_MAP_ALLOW_WORKTREE", "0")
    _plan_with_step(reg)
    out = srv.worktrees(action="create", map="m", branch="feat/x",
                        plan_id="p1", step_id="s1", root=str(gitrepo))
    assert out["provisioned"] is False
    assert out["fallback"] is True
    assert out["command"].startswith("git worktree add -b feat/x")
    # still recorded on the spine so the board shows it
    assert out["worktree"]["branch"] == "feat/x"


# ---- attach / sync / remove --------------------------------------------------

def test_attach_records_without_git_mutation(reg):
    _plan_with_step(reg)
    out = srv.worktrees(action="attach", map="m", branch="feat/existing",
                        plan_id="p1", step_id="s1")
    assert out["worktree"]["branch"] == "feat/existing"
    assert srv.get_plan(map="m", plan_id="p1")["steps"][0]["worktree"] == out["worktree"]["id"]


def test_sync_marks_vanished_worktree_removed(reg, gitrepo, wt_dir):
    import shutil
    _plan_with_step(reg)
    out = srv.worktrees(action="create", map="m", branch="feat/gone",
                        plan_id="p1", step_id="s1", root=str(gitrepo))
    shutil.rmtree(out["worktree"]["path"])                 # delete the checkout behind git's back
    synced = srv.worktrees(action="sync", map="m", root=str(gitrepo))
    assert out["worktree"]["id"] in synced["updated"]
    rec = srv.list_worktrees(map="m", root=str(gitrepo))["worktrees"][0]
    assert rec["status"] == "removed"


def test_remove_drops_git_and_spine(reg, gitrepo, wt_dir):
    _plan_with_step(reg)
    out = srv.worktrees(action="create", map="m", branch="feat/rm",
                        plan_id="p1", step_id="s1", root=str(gitrepo))
    rm = srv.worktrees(action="remove", map="m", id=out["worktree"]["id"], root=str(gitrepo))
    assert rm["gitRemoved"] is True
    assert srv.list_worktrees(map="m", root=str(gitrepo))["worktrees"] == []


# ---- board tool --------------------------------------------------------------

def test_board_tool_projects_cards(reg):
    _plan_with_step(reg)
    srv.plans(action="set_step_status", map="m", plan_id="p1", step_id="s1", step_status="plan")
    srv.plans(action="set_step", map="m", plan_id="p1", step_id="s1", agent="fathom:design", priority="high")
    b = srv.board(map="m")
    assert b["map"] == "m"
    assert b["columns"][2] == "plan"
    card = b["cards"][0]
    assert card["column"] == "plan" and card["agent"] == "fathom:design" and card["priority"] == "high"


def test_remove_missing_worktree_raises(reg):
    _plan_with_step(reg)                                   # the map must exist first
    with pytest.raises(KeyError, match="no worktree"):
        srv.worktrees(action="remove", map="m", id="ghost")
