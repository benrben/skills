"""Interface tests for the **Store** module (store.py).

The interface a caller must know (the test surface from spine-store): a Store
wraps ONE map's JSON file. Reads always reflect what's on disk (load-before-read,
no in-memory cache). `_write(fn)` runs a full load -> mutate -> save under an
exclusive fcntl lock, so two processes sharing the file never lose an update.
The save half is atomic (temp file + os.replace), so a mutation that raises
leaves the prior file intact and never leaves a temp file behind.

In-process / local-substitutable (filesystem) — tested against tmp_path; the
cross-process locking is exercised with real child processes.
"""
import os
import multiprocessing
from pathlib import Path

import pytest

from arch_map.store import Store
from arch_map.model import ArchModel, Module


def _mod(mid: str) -> Module:
    return Module(id=mid, label=mid, domain="d", depth=0.5, size=1.0, seam="")


# ---- load-before-read -------------------------------------------------------

def test_load_missing_file_is_empty_model(tmp_path):
    store = Store(tmp_path / "ghost.json")
    assert store.to_dict()["modules"] == []
    assert store.to_dict()["repo"] == "arch-map"

def test_write_persists_and_reads_reflect_disk(tmp_path):
    path = tmp_path / "m.json"
    store = Store(path)
    store.add_module(_mod("a"))
    assert path.exists()
    # a SECOND Store on the same path sees it — reads hit disk, not a cache.
    fresh = Store(path)
    assert {m["id"] for m in fresh.to_dict()["modules"]} == {"a"}
    assert fresh.get_module("a")["label"] == "a"

def test_reads_see_an_external_write(tmp_path):
    path = tmp_path / "m.json"
    a, b = Store(path), Store(path)
    a.add_module(_mod("x"))
    b.add_module(_mod("y"))                 # b loaded a's write first, so both survive
    assert {m["id"] for m in a.to_dict()["modules"]} == {"x", "y"}


# ---- atomic save: failure isolation + no temp residue -----------------------

def test_failed_mutation_leaves_prior_state_intact(tmp_path):
    path = tmp_path / "m.json"
    store = Store(path)
    store.add_module(_mod("keep"))
    before = path.read_text()

    def boom(_m):
        raise RuntimeError("mid-write crash")

    with pytest.raises(RuntimeError):
        store._write(boom)

    assert path.read_text() == before                      # unchanged
    assert {m["id"] for m in store.to_dict()["modules"]} == {"keep"}

def test_successful_write_leaves_no_temp_file(tmp_path):
    path = tmp_path / "m.json"
    store = Store(path)
    store.add_module(_mod("a"))
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []                                 # os.replace consumed the temp

def test_write_creates_a_sidecar_lock(tmp_path):
    path = tmp_path / "m.json"
    Store(path).add_module(_mod("a"))
    assert path.with_name(path.name + ".lock").exists()


# ---- cross-process locking: no lost updates ---------------------------------

def _hammer(path_str: str, ids: list[int]) -> None:
    """Child process: append a run of distinct modules through the locked seam."""
    s = Store(Path(path_str))
    for i in ids:
        s._write(lambda m, i=i: m.add_module(_mod(f"m{i}")))


@pytest.mark.skipif(not hasattr(os, "fork"), reason="needs fork (POSIX)")
def test_concurrent_writers_do_not_lose_updates(tmp_path):
    path = tmp_path / "m.json"
    workers, per = 4, 12
    ctx = multiprocessing.get_context("fork")
    procs = [
        ctx.Process(target=_hammer, args=(str(path), list(range(w * per, w * per + per))))
        for w in range(workers)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0

    ids = {m["id"] for m in Store(path).to_dict()["modules"]}
    assert ids == {f"m{i}" for i in range(workers * per)}   # every update landed
