"""Interface tests for the **Model Persistence + Lock** module.

Covers ArchModel.save()/from_json() (model.py) and the Store load->mutate->save
wrapper (server.py). Persistence is local-substitutable: the dependency is the
filesystem, with a local stand-in (pytest's tmp_path). The seam stays internal —
no port at the module's external interface.
"""
import json
import threading

import pytest

from arch_map.model import ArchModel, Module, Suggestion, Plan, WorkStep
from arch_map.server import Store


def mod(id, **kw):
    return Module(id=id, label=kw.pop("label", id), domain=kw.pop("domain", "d"),
                  depth=kw.pop("depth", 0.5), size=kw.pop("size", 1.0),
                  seam=kw.pop("seam", ""), **kw)


# ---- save / from_json round trip -------------------------------------------

def test_save_then_from_json_roundtrips_modules_suggestions_plans(tmp_path):
    src = ArchModel("MyRepo", [mod("a", depth=0.7, coverage=0.3, dependsOn=[])])
    src.add_suggestion("a", Suggestion(
        id="a-strong", title="Deepen a", strength="Strong",
        category="in-process", problem="p", solution="s"))
    plan = Plan(id="p1", title="Plan one")
    plan.steps = [WorkStep(id="s1", title="Step one", targets=["a"])]
    src.create_plan(plan)

    p = tmp_path / "m.json"
    src.save(p)
    loaded = ArchModel.from_json(p)

    assert loaded.repo == "MyRepo"
    assert loaded.modules["a"].depth == 0.7
    assert loaded.modules["a"].coverage == 0.3
    assert [s.id for s in loaded.modules["a"].suggestions] == ["a-strong"]
    assert loaded.plans["p1"].steps[0].id == "s1"


def test_save_is_atomic_no_tmp_file_left_behind(tmp_path):
    p = tmp_path / "m.json"
    ArchModel("R", [mod("a")]).save(p)
    assert p.exists()
    leftovers = list(tmp_path.glob("m.json.*.tmp"))
    assert leftovers == []                    # temp file was os.replace'd into place
    assert json.loads(p.read_text())["repo"] == "R"   # valid, complete JSON


def test_from_json_drops_computed_keys(tmp_path):
    # to_dict() embeds orphan/supersededBy/metrics/suggestion — from_json must
    # round-trip its own output without choking on those computed fields.
    p = tmp_path / "m.json"
    ArchModel("R", [mod("a", dependsOn=[]), mod("b", dependsOn=["a"])]).save(p)
    loaded = ArchModel.from_json(p)
    assert set(loaded.modules) == {"a", "b"}


def test_from_json_tolerates_unknown_schema_keys(tmp_path):
    # A map written by a newer schema (extra field) must load, not explode.
    p = tmp_path / "m.json"
    p.write_text(json.dumps({
        "repo": "R",
        "modules": [{
            "id": "a", "label": "A", "domain": "d",
            "depth": 0.5, "size": 1.0, "seam": "",
            "futureField": 123, "orphan": True, "supersededBy": [],
        }],
    }))
    loaded = ArchModel.from_json(p)
    assert loaded.modules["a"].id == "a"      # unknown key dropped, no crash


def test_from_json_backcompat_single_suggestion_slot(tmp_path):
    # Pre-queue format stored one suggestion under "suggestion" (no "suggestions").
    p = tmp_path / "m.json"
    p.write_text(json.dumps({
        "repo": "R",
        "modules": [{
            "id": "a", "label": "A", "domain": "d",
            "depth": 0.5, "size": 1.0, "seam": "",
            "suggestion": {"id": "s1", "title": "T", "strength": "Strong",
                           "category": "in-process", "problem": "p", "solution": "s"},
        }],
    }))
    loaded = ArchModel.from_json(p)
    assert [s.id for s in loaded.modules["a"].suggestions] == ["s1"]


def test_from_json_defaults_missing_optional_fields(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({
        "repo": "R",
        "modules": [{"id": "a", "label": "A", "domain": "d",
                     "depth": 0.5, "size": 1.0, "seam": ""}],
    }))
    rec = ArchModel.from_json(p).modules["a"]
    assert rec.coverage == 0.0
    assert rec.plane == "actual"
    assert rec.lifecycle == "built"


# ---- Store: load-before-read, save-after-write -----------------------------

def test_store_load_returns_empty_model_when_file_absent(tmp_path):
    store = Store(tmp_path / "missing.json")
    view = store.to_dict()
    assert view["modules"] == []
    assert view["repo"] == "arch-map"         # the empty-model default repo


def test_store_write_then_read_through_disk(tmp_path):
    p = tmp_path / "m.json"
    store = Store(p)
    store.add_module(mod("a", depth=0.6))
    assert p.exists()                          # write created the file
    ids = [m["id"] for m in store.to_dict()["modules"]]
    assert ids == ["a"]


def test_store_write_takes_a_lock(tmp_path):
    p = tmp_path / "m.json"
    Store(p).add_module(mod("a"))
    assert (tmp_path / "m.json.lock").exists()  # fcntl lock file created on write


def test_store_concurrent_writes_both_committed(tmp_path):
    p = tmp_path / "m.json"
    store = Store(p)
    errors = []
    barrier = threading.Barrier(2)

    def writer(module_id):
        try:
            barrier.wait()
            store.add_module(mod(module_id))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(mid,)) for mid in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if errors:
        raise errors[0]

    ids = {m["id"] for m in store.to_dict()["modules"]}
    assert ids == {"a", "b"}


def test_store_set_coverage_persists(tmp_path):
    p = tmp_path / "m.json"
    store = Store(p)
    store.add_module(mod("a"))
    store.set_coverage("a", 0.75)
    reloaded = Store(p).get_module("a")
    assert reloaded["coverage"] == 0.75


# ---- Store delegation surface ------------------------------------------------

def test_store_delegates_reads_and_writes(tmp_path):
    """Every Store method is a locked load->mutate->save (or lock-free read)
    delegation to the same-named ArchModel method; cross the ones no other
    test reaches so the whole delegation surface stays wired."""
    from arch_map.model import Doc
    s = Store(tmp_path / "m.json")
    s.add_module(mod("a"))
    assert s.orphans() == ["a"]

    s.mark_updated("a", False)
    assert s.modules["a"].updated is False
    s.set_plane("a", "intended")
    s.set_lifecycle("a", "planned")
    s.update_module("a", label="A2")
    rec = s.get_module("a")
    assert rec["plane"] == "intended"
    assert rec["lifecycle"] == "planned"
    assert rec["label"] == "A2"

    s.create_plan(Plan(id="p1", title="P"))
    assert "p1" in s.plans
    s.delete_plan("p1")
    assert "p1" not in s.plans

    s.add_doc(Doc(id="d1", type="note", title="D"))
    assert "d1" in s.docs
    assert [d["id"] for d in s.get_docs(["d1"])] == ["d1"]
