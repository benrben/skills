"""git-facts — measured facts from a repository's git history (the Git Fact Source).

The spine's churn/LOC numbers stop being agent estimates here: every value is
computed from the actual repo. Pure functional layer over the git CLI; the seam
is local-substitutable — tests run real git against throwaway repos in tmp dirs,
production shells out to the repo's own git. No timestamps are generated inside
(date math is delegated to git's own --since parsing).

Interface (the test surface):
  head_sha()                      -> str   current HEAD, full sha
  changed_files(since_sha)        -> list  repo-relative POSIX paths, sorted, deduped
  commits_since(since_sha)        -> int   commit count since_sha..HEAD
  churn(paths, window_days=90)    -> float 0..1 — share of the window's commits
                                           that touch any of `paths`
  loc(paths)                      -> int   total non-blank lines (comments kept) across the text files

Error modes: NotARepo when root isn't a git work tree (or git is missing);
UnknownSha when a revision can't be resolved (bad sha, empty repo's HEAD).
Never returns partial data — a failed call raises, a successful call is complete.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class NotARepo(Exception):
    """The configured root is not inside a git work tree (or git is unavailable)."""


class UnknownSha(Exception):
    """A revision could not be resolved — bad sha, or HEAD in an empty repo."""


class GitFacts:
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
            if "not a git repository" in err.lower():
                raise NotARepo(f"{self.root} is not a git repository") from e
            raise UnknownSha(f"git {args[0]} failed: {err}") from e
        return out.stdout

    def head_sha(self) -> str:
        return self._run("rev-parse", "HEAD").strip()

    def changed_files(self, since_sha: str) -> list[str]:
        out = self._run("diff", "--name-only", since_sha, "HEAD")
        return sorted({ln.strip() for ln in out.splitlines() if ln.strip()})

    def commits_since(self, since_sha: str) -> int:
        return int(self._run("rev-list", "--count", f"{since_sha}..HEAD").strip())

    def churn(self, paths: list[str], window_days: int = 90) -> float:
        """Share of the last `window_days`' commits that touch any of `paths`
        (files or directories, repo-relative). Empty paths or an empty window -> 0.0."""
        if not paths:
            return 0.0
        since = f"--since={int(window_days)} days ago"
        total = int(self._run("rev-list", "--count", since, "HEAD").strip())
        if total == 0:
            return 0.0
        touching = int(self._run("rev-list", "--count", since, "HEAD",
                                 "--", *paths).strip())
        return min(1.0, touching / total)

    def loc(self, paths: list[str]) -> int:
        """Total NON-BLANK line count across the given paths' existing text files;
        directory entries are counted recursively. Whitespace-only lines are skipped
        (they aren't implementation mass); comments are kept (stripping them is
        language-specific and not worth the fragility). Missing paths and binary
        files are skipped, never raised on."""
        n = 0
        for rel in paths:
            p = self.root / rel
            targets = ([p] if p.is_file()
                       else sorted(q for q in p.rglob("*") if q.is_file())
                       if p.is_dir() else [])
            for t in targets:
                try:
                    n += sum(1 for ln in t.read_text(encoding="utf-8").splitlines()
                             if ln.strip())
                except (UnicodeDecodeError, OSError):
                    continue
        return n
