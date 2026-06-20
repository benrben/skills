"""worktrees — the **Git Worktree Source**: provision and tidy isolated per-task
branches via the `git worktree` CLI.

Sibling to git_facts.py: that module READS facts from git history (churn/LOC/sha),
this one ACTS on the repo — one `git worktree add` per task gives an agent its own
branch + checkout to build in, in parallel with the others, with nothing colliding
in the shared working tree. The studio board shows the branch + which agent is on it;
the spine RECORDS the worktree (model.Worktree); this module does the real git.

Same discipline as GitFacts: a thin, pure-ish layer over `git -C <root>` shelling
out; every failure raises a typed error (never partial data); local-substitutable
seam so tests run REAL git against throwaway repos in tmp dirs.

Interface (the test surface):
  list()                              -> list[dict]  one per worktree: path, branch,
                                                     head, detached, bare
  add(path, branch, base="",          -> dict        provision a worktree; -b <branch>
      new_branch=True)                               when new_branch (the default)
  remove(path, force=False)           -> None        drop a worktree checkout
  prune()                             -> None        forget worktrees whose dirs are gone
  current_branch()                    -> str         the main checkout's branch (or "")

Module helpers (no git):
  slug(name)                          -> str         a filesystem-safe branch/dir slug
  default_path(base_dir, name)        -> str         where a task's worktree should live

Error modes: NotARepo (root is not a git work tree / git missing) and UnknownSha
(bad base ref) are reused from git_facts; WorktreeError covers everything else the
git worktree subcommands reject (path exists, branch already checked out, ...).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .git_facts import NotARepo, UnknownSha


class WorktreeError(Exception):
    """A `git worktree` subcommand failed for a reason that isn't NotARepo/UnknownSha
    — the path already exists, the branch is already checked out elsewhere, etc."""


def slug(name: str) -> str:
    """A filesystem- and branch-safe slug: lowercase, non-alnum runs -> single '-'.
    ('Build pricing/engine!' -> 'build-pricing-engine')."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "task"


def default_path(base_dir: str | Path, name: str) -> str:
    """Where a task's worktree checkout should live: <base_dir>/<slug(name)>.
    base_dir defaults (in the server) to a sibling of the repo so the worktree dir
    never nests inside the main working tree."""
    return str(Path(base_dir).expanduser() / slug(name))


class Worktrees:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _run(self, *args: str) -> str:
        try:
            out = subprocess.run(["git", "-C", str(self.root), *args],
                                 capture_output=True, text=True, check=True)
        except FileNotFoundError as e:                       # no git binary at all
            raise NotARepo(f"git executable not found (root: {self.root})") from e
        except subprocess.CalledProcessError as e:
            err = (e.stderr or "").strip()
            low = err.lower()
            if "not a git repository" in low:
                raise NotARepo(f"{self.root} is not a git repository") from e
            if "invalid reference" in low or "unknown revision" in low or "not a valid" in low:
                raise UnknownSha(f"git {args[0]} {args[1] if len(args) > 1 else ''}: {err}") from e
            raise WorktreeError(f"git {' '.join(args[:2])} failed: {err}") from e
        return out.stdout

    def list(self) -> list[dict]:
        """Every worktree git knows about (the main checkout included), parsed from
        `git worktree list --porcelain`. Each entry: path, branch (short name or ""),
        head (sha or ""), detached (bool), bare (bool). Sorted by path."""
        out = self._run("worktree", "list", "--porcelain")
        entries: list[dict] = []
        cur: dict | None = None
        for line in out.splitlines():
            if line.startswith("worktree "):
                if cur is not None:
                    entries.append(cur)
                cur = {"path": line[len("worktree "):].strip(),
                       "branch": "", "head": "", "detached": False, "bare": False}
            elif cur is None:
                continue
            elif line.startswith("HEAD "):
                cur["head"] = line[len("HEAD "):].strip()
            elif line.startswith("branch "):
                ref = line[len("branch "):].strip()
                cur["branch"] = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
            elif line.strip() == "detached":
                cur["detached"] = True
            elif line.strip() == "bare":
                cur["bare"] = True
        if cur is not None:
            entries.append(cur)
        return sorted(entries, key=lambda e: e["path"])

    def add(self, path: str | Path, branch: str, base: str = "",
            new_branch: bool = True) -> dict:
        """Provision a worktree at `path`. With new_branch (default), create `branch`
        forking from `base` (or HEAD); otherwise check out an existing `branch`. Returns
        the new worktree's parsed list entry. Raises WorktreeError if the path exists
        or the branch is already checked out, UnknownSha on a bad base."""
        path = str(Path(path))
        args = ["worktree", "add"]
        if new_branch:
            args += ["-b", branch, path]
            if base:
                args += [base]
        else:
            args += [path, branch]
        self._run(*args)
        for e in self.list():
            if Path(e["path"]) == Path(path).resolve() or e["path"] == path:
                return e
        return {"path": path, "branch": branch, "head": "", "detached": False, "bare": False}

    def remove(self, path: str | Path, force: bool = False) -> None:
        """Remove the worktree checkout at `path` (the branch itself is kept). `force`
        drops it even with local changes."""
        args = ["worktree", "remove", str(Path(path))]
        if force:
            args.append("--force")
        self._run(*args)

    def prune(self) -> None:
        """Forget worktree admin entries whose directories no longer exist."""
        self._run("worktree", "prune")

    def current_branch(self) -> str:
        """The main checkout's current branch, or "" when detached."""
        out = self._run("rev-parse", "--abbrev-ref", "HEAD").strip()
        return "" if out == "HEAD" else out
