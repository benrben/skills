"""Interface tests for the **Git Worktree Source** (worktrees.py).

Local-substitutable seam exercised as designed: REAL git, throwaway repos in tmp
dirs. Every assertion crosses the public interface only.
"""
import subprocess

import pytest

from arch_map.git_facts import NotARepo, UnknownSha
from arch_map.worktrees import Worktrees, WorktreeError, slug, default_path


def _git(root, *args):
    subprocess.run(["git", "-C", str(root),
                    "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false", *args],
                   check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "a.py").write_text("print(1)\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "c1")
    return r


# ---- slug / path helpers (pure) ---------------------------------------------

def test_slug_is_filesystem_safe():
    assert slug("Build pricing/engine!") == "build-pricing-engine"
    assert slug("") == "task"


def test_default_path_joins_base_and_slug(tmp_path):
    assert default_path(tmp_path, "feat/X") == str(tmp_path / "feat-x")


# ---- list / current_branch ---------------------------------------------------

def test_list_main_only_then_after_add(repo, tmp_path):
    w = Worktrees(repo)
    only = w.list()
    assert len(only) == 1 and only[0]["branch"] == "main" and len(only[0]["head"]) == 40

    w.add(tmp_path / "wt-x", "feat/x")
    branches = sorted(e["branch"] for e in w.list())
    assert branches == ["feat/x", "main"]


def test_current_branch(repo):
    assert Worktrees(repo).current_branch() == "main"


# ---- add: new branch, fork point, parsed entry ------------------------------

def test_add_creates_branch_and_checkout(repo, tmp_path):
    e = Worktrees(repo).add(tmp_path / "wt", "feat/pricing")
    assert e["branch"] == "feat/pricing"
    assert len(e["head"]) == 40
    assert (tmp_path / "wt" / "a.py").exists()        # the checkout is real


def test_add_existing_branch_without_new_flag(repo, tmp_path):
    _git(repo, "branch", "existing")
    e = Worktrees(repo).add(tmp_path / "wt", "existing", new_branch=False)
    assert e["branch"] == "existing"


def test_add_duplicate_path_raises_worktree_error(repo, tmp_path):
    w = Worktrees(repo)
    w.add(tmp_path / "wt", "feat/a")
    with pytest.raises(WorktreeError):
        w.add(tmp_path / "wt", "feat/b")              # path already a worktree


def test_add_bad_base_raises_unknown_sha(repo, tmp_path):
    with pytest.raises(UnknownSha):
        Worktrees(repo).add(tmp_path / "wt", "feat/x", base="deadbeefdeadbeef")


# ---- remove / prune ----------------------------------------------------------

def test_remove_drops_the_checkout(repo, tmp_path):
    w = Worktrees(repo)
    w.add(tmp_path / "wt", "feat/x")
    w.remove(tmp_path / "wt")
    assert sorted(e["branch"] for e in w.list()) == ["main"]


def test_prune_forgets_deleted_dir(repo, tmp_path):
    import shutil
    w = Worktrees(repo)
    w.add(tmp_path / "wt", "feat/x")
    shutil.rmtree(tmp_path / "wt")                     # delete the dir behind git's back
    w.prune()
    assert sorted(e["branch"] for e in w.list()) == ["main"]


# ---- error modes -------------------------------------------------------------

def test_not_a_repo_raises_typed_error(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(NotARepo):
        Worktrees(plain).list()
