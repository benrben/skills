"""The declarative signal registry is the single source of truth."""
import pytest


def test_registry_is_consistent():
    pytest.importorskip("fastmcp")
    from arch_map.server import SIGNAL_REGISTRY, _CRAFT_SIGNALS
    ids = [s[0] for s in SIGNAL_REGISTRY]
    assert len(ids) == len(set(ids)), "duplicate signal id"
    assert _CRAFT_SIGNALS == {s[0] for s in SIGNAL_REGISTRY if s[1] == "craft"}
    for sid, fam, fn, why, how in SIGNAL_REGISTRY:
        assert fam in ("architecture", "craft")
        assert why and how, f"{sid} missing why/how"


def test_compute_signals_unchanged_behaviour():
    pytest.importorskip("fastmcp")
    from arch_map.server import _compute_signals
    from arch_map.model import Module
    m = Module(id="m", label="m", domain="d", depth=0.3, size=2.5, seam="", coverage=0.2,
               leaksTo=["x"], craft={"maxFnLen": 80, "maxArgs": 5, "maxNesting": 5,
                                     "methodCount": 15, "magicNumbers": 4, "commentedOutBlocks": 1})
    mx = {"churn": 0.5, "blastRadius": 12, "inCycle": True, "fanOut": 7, "fanIn": 9,
          "instability": 0.8, "coupling": 4, "health": 10}
    sigs = _compute_signals(m, mx)
    for s in ("danger-zone", "bulky-impl", "leaky-seam", "long-function", "large-class"):
        assert s in sigs
