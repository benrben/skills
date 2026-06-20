"""Interface tests for the **ArchModel Graph** module (model.py).

The interface is the test surface: these assert observable behaviour of the
mutable in-memory graph — module CRUD (single + bulk), mutation, the editable
whitelist, depth/coverage clamping, delete-cascade edge pruning across all four
edge types, orphan computation, and Module.from_dict's loose-dict construction.
ArchModel CRUD is pure in-process (no I/O), so we test through the interface
directly — no adapters.
"""
import pytest

from arch_map.model import ArchModel, Module


def mod(id, *, domain="d", depth=0.5, size=1.0, seam="", coverage=0.0, **kw):
    return Module(id=id, label=kw.pop("label", id), domain=domain, depth=depth,
                  size=size, seam=seam, coverage=coverage, **kw)


def model(*modules):
    return ArchModel("repo", list(modules))


# ---- add / get --------------------------------------------------------------

def test_add_then_get_module_roundtrips_with_computed_keys():
    m = model()
    m.add_module(mod("a"))
    got = m.get_module("a")
    assert got["id"] == "a"
    assert got["orphan"] is True          # no edges yet
    assert got["supersededBy"] == []      # computed key present

def test_add_module_marks_updated():
    m = model()
    m.add_module(mod("a", depth=0.4))
    assert m.modules["a"].updated is True

def test_add_duplicate_module_raises():
    m = model(mod("a"))
    with pytest.raises(KeyError):
        m.add_module(mod("a"))

def test_get_unknown_module_raises():
    with pytest.raises(KeyError):
        model().get_module("nope")

def test_add_module_clamps_out_of_range_fields():
    m = model()
    m.add_module(mod("hi", depth=2.0, coverage=-0.5, churn=9.0))
    rec = m.modules["hi"]
    assert rec.depth == 1.0
    assert rec.coverage == 0.0
    assert rec.churn == 1.0


# ---- update -----------------------------------------------------------------

def test_update_module_changes_editable_fields_and_sets_updated():
    m = model(mod("a"))
    m.modules["a"].updated = False
    m.update_module("a", depth=0.9, iface="does X")
    assert m.modules["a"].depth == 0.9
    assert m.modules["a"].iface == "does X"
    assert m.modules["a"].updated is True

def test_update_module_rejects_non_editable_field():
    m = model(mod("a"))
    with pytest.raises(ValueError):
        m.update_module("a", id="b")        # id is not in the _EDITABLE whitelist

def test_update_module_clamps():
    m = model(mod("a"))
    m.update_module("a", depth=5.0)
    assert m.modules["a"].depth == 1.0

def test_update_module_respects_explicit_updated_flag():
    m = model(mod("a"))
    m.update_module("a", depth=0.6, updated=False)
    assert m.modules["a"].updated is False   # not force-set when caller passes it

def test_update_unknown_module_raises():
    with pytest.raises(KeyError):
        model().update_module("ghost", depth=0.1)


# ---- delete + cascade edge pruning -----------------------------------------

def test_delete_module_prunes_all_four_edge_types():
    m = model(
        mod("y"),
        mod("x", dependsOn=["y"], leaksTo=["y"],
            intendsToDependOn=["y"], supersedes=["y"]),
    )
    m.modules["x"].updated = False
    m.delete_module("y")
    x = m.modules["x"]
    assert "y" not in x.dependsOn
    assert "y" not in x.leaksTo
    assert "y" not in x.intendsToDependOn
    assert "y" not in x.supersedes
    assert x.updated is True                 # pruning marks the survivor changed
    assert "y" not in m.modules

def test_delete_unknown_module_raises():
    with pytest.raises(KeyError):
        model().delete_module("nope")


# ---- bulk CRUD --------------------------------------------------------------

def test_add_modules_rejects_duplicate_ids_in_batch():
    with pytest.raises(KeyError):
        model().add_modules([mod("a"), mod("a")])

def test_add_modules_rejects_clash_with_existing():
    m = model(mod("a"))
    with pytest.raises(KeyError):
        m.add_modules([mod("b"), mod("a")])

def test_add_modules_adds_all_on_success():
    m = model()
    m.add_modules([mod("a"), mod("b"), mod("c")])
    assert set(m.modules) == {"a", "b", "c"}

def test_get_modules_returns_records_with_computed_keys():
    m = model(mod("a", dependsOn=["b"]), mod("b"))
    out = m.get_modules(["a", "b"])
    assert [r["id"] for r in out] == ["a", "b"]
    assert all("orphan" in r and "supersededBy" in r for r in out)

def test_get_modules_unknown_raises():
    m = model(mod("a"))
    with pytest.raises(KeyError):
        m.get_modules(["a", "ghost"])

def test_update_modules_validates_all_before_applying():
    m = model(mod("a", depth=0.1))
    # second update has no id -> the whole batch is rejected before any apply
    with pytest.raises(ValueError):
        m.update_modules([{"id": "a", "depth": 0.9}, {"depth": 0.2}])
    assert m.modules["a"].depth == 0.1       # first update was NOT applied

def test_update_modules_unknown_id_rejects_batch():
    m = model(mod("a", depth=0.1))
    with pytest.raises(KeyError):
        m.update_modules([{"id": "a", "depth": 0.9}, {"id": "ghost", "depth": 0.2}])
    assert m.modules["a"].depth == 0.1

def test_delete_modules_missing_raises_listing_missing():
    m = model(mod("a"))
    with pytest.raises(KeyError):
        m.delete_modules(["a", "ghost"])


# ---- orphans ----------------------------------------------------------------

def test_orphans_flags_only_unconnected_nodes():
    m = model(mod("a", dependsOn=["b"]), mod("b"), mod("c"))
    orphans = set(m.orphans())
    assert orphans == {"c"}                   # a has an edge; b is a target; c is alone

def test_target_of_an_edge_is_not_orphan():
    m = model(mod("a", supersedes=["b"]), mod("b"))
    assert "b" not in m.orphans()             # intended-plane edges connect too


# ---- targeted mutators ------------------------------------------------------

def test_set_depth_clamps_and_marks_updated():
    m = model(mod("a"))
    m.modules["a"].updated = False
    m.set_depth("a", 3.0)
    assert m.modules["a"].depth == 1.0
    assert m.modules["a"].updated is True

def test_set_coverage_clamps_and_marks_updated():
    m = model(mod("a"))
    m.set_coverage("a", -1.0)
    assert m.modules["a"].coverage == 0.0
    assert m.modules["a"].updated is True

def test_set_plane_sets_and_marks_updated():
    m = model(mod("a"))
    m.modules["a"].updated = False
    m.set_plane("a", "intended")
    assert m.modules["a"].plane == "intended"
    assert m.modules["a"].updated is True

def test_set_lifecycle_sets_and_marks_updated():
    m = model(mod("a"))
    m.modules["a"].updated = False
    m.set_lifecycle("a", "building")
    assert m.modules["a"].lifecycle == "building"
    assert m.modules["a"].updated is True

def test_superseded_by_lists_intended_replacements():
    m = model(mod("a"), mod("b", supersedes=["a"]))
    assert m.get_module("a")["supersededBy"] == ["b"]
    assert m.get_module("b")["supersededBy"] == []

def test_mark_updated_toggles():
    m = model(mod("a"))
    m.mark_updated("a", False)
    assert m.modules["a"].updated is False
    m.mark_updated("a", True)
    assert m.modules["a"].updated is True

def test_realize_module_without_optionals_keeps_scores():
    m = model(mod("a", depth=0.3, coverage=0.2))
    m.modules["a"].plane = "intended"
    m.modules["a"].lifecycle = "planned"
    m.realize_module("a")                     # no depth/coverage/files given
    rec = m.modules["a"]
    assert rec.plane == "actual" and rec.lifecycle == "built"
    assert rec.depth == 0.3 and rec.coverage == 0.2   # untouched

def test_realize_module_flips_plane_and_lifecycle():
    m = model(mod("a"))
    m.modules["a"].plane = "intended"
    m.modules["a"].lifecycle = "planned"
    m.realize_module("a", depth=0.88, coverage=0.5, files=["src/a.py"])
    rec = m.modules["a"]
    assert rec.plane == "actual"
    assert rec.lifecycle == "built"
    assert rec.depth == 0.88
    assert rec.coverage == 0.5
    assert rec.files == ["src/a.py"]
    assert rec.updated is True


# ---- Module.from_dict (loose-dict construction) -----------------------------

def test_from_dict_fills_defaults():
    rec = Module.from_dict({"id": "a", "label": "A", "domain": "d"})
    assert rec.depth == 0.5 and rec.size == 1.0 and rec.seam == ""

def test_from_dict_requires_core_fields():
    with pytest.raises(ValueError):
        Module.from_dict({"label": "A", "domain": "d"})   # missing id

def test_from_dict_ignores_managed_and_unknown_keys():
    rec = Module.from_dict({
        "id": "a", "label": "A", "domain": "d",
        "suggestions": [{"bogus": 1}], "orphan": True,
        "supersededBy": ["z"], "metrics": {}, "futureField": 99,
    })
    assert rec.id == "a"
    assert rec.suggestions == []              # managed key dropped, default used
