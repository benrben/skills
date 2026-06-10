"""Interface tests for the **Git Fact Source** (git_facts.py).

Local-substitutable seam exercised as designed: REAL git, throwaway repos in
tmp dirs. Every assertion crosses the public interface only.
"""
import subprocess

import pytest

from arch_map.git_facts import GitFacts, NotARepo, UnknownSha


def _git(root, *args):
    subprocess.run(["git", "-C", str(root),
                    "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false", *args],
                   check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """c1 touches a.py + lib/b.py; c2 touches a.py; c3 touches lib/b.py."""
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.py").write_text("print(1)\n")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "b.py").write_text("x = 1\ny = 2\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "c1")
    (tmp_path / "a.py").write_text("print(2)\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "c2")
    (tmp_path / "lib" / "b.py").write_text("x = 1\ny = 2\nz = 3\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "c3")
    return tmp_path


def _sha(root, rev):
    out = subprocess.run(["git", "-C", str(root), "rev-parse", rev],
                         check=True, capture_output=True, text=True)
    return out.stdout.strip()


def test_head_sha_is_full_sha(repo):
    sha = GitFacts(repo).head_sha()
    assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)


def test_changed_files_since_sha_sorted_repo_relative(repo):
    first = _sha(repo, "HEAD~2")
    assert GitFacts(repo).changed_files(first) == ["a.py", "lib/b.py"]


def test_changed_files_since_head_is_empty(repo):
    g = GitFacts(repo)
    assert g.changed_files(g.head_sha()) == []


def test_commits_since(repo):
    g = GitFacts(repo)
    assert g.commits_since(_sha(repo, "HEAD~2")) == 2
    assert g.commits_since(g.head_sha()) == 0


def test_churn_is_share_of_window_commits_touching_paths(repo):
    g = GitFacts(repo)
    # 3 commits in the window; c1 + c3 touch lib/ -> 2/3
    assert g.churn(["lib"]) == pytest.approx(2 / 3)
    # all three commits touch something in the repo root set
    assert g.churn(["a.py", "lib"]) == pytest.approx(1.0)


def test_churn_empty_paths_is_zero(repo):
    assert GitFacts(repo).churn([]) == 0.0


def test_loc_counts_existing_text_files_and_skips_missing(repo):
    g = GitFacts(repo)
    assert g.loc(["a.py", "lib/b.py"]) == 1 + 3
    assert g.loc(["a.py", "nope.py"]) == 1
    assert g.loc(["lib"]) == 3                       # directories count recursively


def test_not_a_repo_raises_typed_error(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(NotARepo):
        GitFacts(plain).head_sha()


def test_unknown_sha_raises_typed_error(repo):
    with pytest.raises(UnknownSha):
        GitFacts(repo).changed_files("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
