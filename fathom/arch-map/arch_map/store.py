"""The file-backed Store — the only writer to one map's JSON file.

Extracted from server.py per adr-split-spine-hub. The interface (the seam every
tool and route crosses to touch a map): read pass-throughs that always reflect
disk, and `_write(fn)` which serializes a full load -> mutate -> save under an
exclusive `fcntl` lock so the stdio server, the HTTP studio, and other processes
can share one file without clobbering each other. The atomic-replace half of the
durability promise lives in `ArchModel.save` (temp file + os.replace); this module
owns the lock + the load-before-read discipline. See adr-file-backed-store.
"""
from __future__ import annotations

import fcntl
from pathlib import Path

from .model import ArchModel
from . import ledger


class Store:
    """File-backed ArchModel: load-before-read, save-after-write. Same method
    surface the tools already call, so store.<op>(...) works unchanged."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> ArchModel:
        return ArchModel.from_json(self.path) if self.path.exists() else ArchModel("arch-map", [])

    def _write(self, fn) -> None:
        # Serialize read-modify-write across processes (web app + desktop stdio
        # server share one file) so concurrent writers can't clobber each other.
        lock = self.path.with_name(self.path.name + ".lock")
        with open(lock, "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            m = self._load()
            fn(m)
            m.save(self.path)

    # reads
    def to_dict(self) -> dict: return self._load().to_dict()
    def to_view(self) -> dict: return self._load().to_view()
    def orphans(self): return self._load().orphans()
    def get_module(self, mid): return self._load().get_module(mid)
    def get_modules(self, ids): return self._load().get_modules(ids)
    def get_plan(self, pid): return self._load().get_plan(pid)
    def get_doc(self, did): return self._load().get_doc(did)
    def get_docs(self, ids): return self._load().get_docs(ids)
    def get_worktree(self, wid): return self._load().get_worktree(wid)
    def board(self, running=None): return self._load().board(running)
    def queued_for_grilling(self): return self._load().queued_for_grilling()
    @property
    def modules(self): return self._load().modules
    @property
    def plans(self): return self._load().plans
    @property
    def docs(self): return self._load().docs
    @property
    def worktrees(self): return self._load().worktrees

    # writes (load -> mutate -> save)
    def set_depth(self, mid, s): self._write(lambda m: m.set_depth(mid, s))
    def set_coverage(self, mid, f): self._write(lambda m: m.set_coverage(mid, f))
    def mark_updated(self, mid, u=True): self._write(lambda m: m.mark_updated(mid, u))
    def set_plane(self, mid, p): self._write(lambda m: m.set_plane(mid, p))
    def set_lifecycle(self, mid, lc): self._write(lambda m: m.set_lifecycle(mid, lc))
    def realize_module(self, mid, depth=None, coverage=None, files=None):
        self._write(lambda m: m.realize_module(mid, depth, coverage, files))
    def add_suggestion(self, mid, s): self._write(lambda m: m.add_suggestion(mid, s))
    def resolve(self, sid): self._write(lambda m: m.resolve(sid))
    def decide(self, sid, d, n="", adr="", expect=None):
        self._write(lambda m: m.decide(sid, d, n, adr, expect))
    def request_grilling(self, sid): self._write(lambda m: m.request_grilling(sid))
    def mark_grilling(self, sid): self._write(lambda m: m.mark_grilling(sid))
    def mark_grilled(self, sid): self._write(lambda m: m.mark_grilled(sid))
    def add_module(self, mod): self._write(lambda m: m.add_module(mod))
    def update_module(self, mid, **ch): self._write(lambda m: m.update_module(mid, **ch))
    def delete_module(self, mid): self._write(lambda m: m.delete_module(mid))
    def add_modules(self, mods): self._write(lambda m: m.add_modules(mods))
    def update_modules(self, ups): self._write(lambda m: m.update_modules(ups))
    def delete_modules(self, ids): self._write(lambda m: m.delete_modules(ids))
    def create_plan(self, plan): self._write(lambda m: m.create_plan(plan))
    def update_plan(self, pid, **ch): self._write(lambda m: m.update_plan(pid, **ch))
    def add_work_steps(self, pid, steps): self._write(lambda m: m.add_work_steps(pid, steps))
    def set_step_status(self, pid, sid, st): self._write(lambda m: m.set_step_status(pid, sid, st))
    def set_step_fields(self, pid, sid, **ch): self._write(lambda m: m.set_step_fields(pid, sid, **ch))
    def delete_plan(self, pid): self._write(lambda m: m.delete_plan(pid))
    def add_worktree(self, wt): self._write(lambda m: m.add_worktree(wt))
    def update_worktree(self, wid, **ch): self._write(lambda m: m.update_worktree(wid, **ch))
    def delete_worktree(self, wid): self._write(lambda m: m.delete_worktree(wid))
    def link_step_worktree(self, pid, sid, wid): self._write(lambda m: m.link_step_worktree(pid, sid, wid))
    def add_doc(self, doc): self._write(lambda m: m.add_doc(doc))
    def update_doc(self, did, **ch): self._write(lambda m: m.update_doc(did, **ch))
    def delete_doc(self, did): self._write(lambda m: m.delete_doc(did))
    def record_anchor(self, sha, ts, keep=200):
        self._write(lambda m: ledger.record_anchor(m, sha, ts, keep))
