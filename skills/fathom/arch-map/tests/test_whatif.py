"""Interface tests for the **What-If Merge Preview** (whatif.py) — hand-built
graphs, hand-computed expectations, and the purity guarantee."""
import json

import pytest

from arch_map.model import ArchModel, Module
from arch_map.whatif import preview_merge


def _model():
    # caller -> a -> b -> base ; a -> b is the absorbed edge when merging a+b
    base = Module(id="base", label="Base", domain="d", depth=0.9, size=1, seam="")
    a = Module(id="a", label="A", domain="d", depth=0.2, size=1, seam="",
               coverage=0.0, dependsOn=["b"], leaksTo=["b"])
    b = Module(id="b", label="B", domain="d", depth=0.4, size=3, seam="",
               coverage=0.8, dependsOn=["base"])
    caller = Module(id="caller", label="C", domain="d", depth=0.5, size=1, seam="",
                    dependsOn=["a"])
    return ArchModel("t", [base, a, b, caller])


def test_merge_absorbs_internal_edges_and_repoints_external():
    out = preview_merge(_model(), ["a", "b"])
    assert out["absorbedEdges"] == ["a->b"]
    assert out["externalEdges"] == {"in": ["caller"], "out": ["base"]}
    assert out["merged"]["fanIn"] == 1          # caller
    assert out["merged"]["fanOut"] == 1         # base
    assert out["merged"]["blastRadius"] == 1    # only caller is downstream


def test_merged_depth_and_coverage_are_size_weighted():
    out = preview_merge(_model(), ["a", "b"])
    assert out["merged"]["depth"] == pytest.approx((0.2 * 1 + 0.4 * 3) / 4)
    assert out["merged"]["coverage"] == pytest.approx((0.0 * 1 + 0.8 * 3) / 4)


def test_before_carries_current_metrics_per_member():
    out = preview_merge(_model(), ["a", "b"])
    assert set(out["before"]) == {"a", "b"}
    assert out["before"]["a"]["fanIn"] == 1


def test_validates_ids():
    m = _model()
    with pytest.raises(ValueError):
        preview_merge(m, ["a"])
    with pytest.raises(ValueError):
        preview_merge(m, ["a", "a"])
    with pytest.raises(ValueError):
        preview_merge(m, ["a", "ghost"])


def test_preview_is_pure():
    m = _model()
    snap = json.dumps(m.to_dict(), sort_keys=True)
    preview_merge(m, ["a", "b"])
    assert json.dumps(m.to_dict(), sort_keys=True) == snap
