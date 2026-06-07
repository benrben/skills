"""Interface tests for the **MCP Tools — Signals Engine** slice (server.py).

The rules engine: _compute_signals applies ~10 hard-coded structural rules to a
module + its metrics; scan_signals runs it over a map (health-sorted, worst-first,
with a signal filter); get_metrics surfaces one module's raw numbers.
"""
import pytest

import arch_map.server as srv
from arch_map.model import Module


def mod(**kw):
    return Module(id=kw.pop("id", "a"), label="A", domain="d",
                  depth=kw.pop("depth", 0.8), size=1.0, seam="",
                  coverage=kw.pop("coverage", 0.9), leaksTo=kw.pop("leaksTo", []))


def mx(**kw):
    base = {"fanIn": 0, "fanOut": 0, "instability": 0.0, "blastRadius": 0,
            "coupling": 0, "inCycle": False, "health": 50, "churn": 0.0}
    base.update(kw)
    return base


# ---- _compute_signals: each rule fires on its trigger -----------------------

def test_clean_module_has_no_signals():
    assert srv._compute_signals(mod(), mx()) == []

def test_danger_zone():
    assert "danger-zone" in srv._compute_signals(mod(coverage=0.1), mx(churn=0.5))

def test_test_first():
    assert "test-first" in srv._compute_signals(mod(coverage=0.1), mx(blastRadius=6))

def test_critical_path_untested():
    assert "critical-path-untested" in srv._compute_signals(mod(coverage=0.5), mx(blastRadius=12))

def test_circular_dep():
    assert "circular-dep" in srv._compute_signals(mod(), mx(inCycle=True))

def test_needs_refactor():
    assert "needs-refactor" in srv._compute_signals(mod(depth=0.2), mx(fanOut=6))

def test_god_module():
    assert "god-module" in srv._compute_signals(mod(depth=0.6), mx(fanIn=8, fanOut=6))

def test_bottleneck():
    assert "bottleneck" in srv._compute_signals(mod(depth=0.3), mx(fanIn=8))

def test_unstable_api():
    assert "unstable-api" in srv._compute_signals(mod(), mx(instability=0.8, fanIn=3))

def test_split_candidate():
    assert "split-candidate" in srv._compute_signals(mod(depth=0.6), mx(fanOut=5, coupling=3))

def test_leaky_seam():
    assert "leaky-seam" in srv._compute_signals(mod(leaksTo=["x"]), mx())


# ---- scan_signals -----------------------------------------------------------

def test_scan_signals_reports_and_filters(reg):
    srv.add_module(map="m", id="a", label="A", domain="d", leaksTo=["b"])
    srv.add_module(map="m", id="b", label="B", domain="d")
    out = srv.scan_signals(map="m")
    assert {"map", "filter", "total", "signalCounts", "modules"} <= set(out)
    a = next(r for r in out["modules"] if r["id"] == "a")
    assert "leaky-seam" in a["signals"]
    assert out["signalCounts"].get("leaky-seam", 0) >= 1

    focused = srv.scan_signals(map="m", signal="leaky-seam")
    assert all("leaky-seam" in r["signals"] for r in focused["modules"])
    assert "a" in {r["id"] for r in focused["modules"]}

def test_scan_signals_sorted_worst_health_first(reg):
    # a leaks (lower health) ; c is clean and depended-on (higher health)
    srv.add_module(map="m", id="a", label="A", domain="d", depth=0.1, coverage=0.0,
                   leaksTo=["c"])
    srv.add_module(map="m", id="c", label="C", domain="d", depth=0.9, coverage=0.9)
    healths = [r["health"] for r in srv.scan_signals(map="m")["modules"]]
    assert healths == sorted(healths)          # ascending = worst-first


# ---- get_metrics ------------------------------------------------------------

def test_get_metrics_single_and_all(reg):
    srv.add_module(map="m", id="a", label="A", domain="d")
    srv.add_module(map="m", id="b", label="B", domain="d", dependsOn=["a"])
    one = srv.get_metrics(map="m", module="a")
    assert one["module"] == "a"
    assert one["metrics"]["fanIn"] == 1        # b depends on a
    allm = srv.get_metrics(map="m")
    assert set(allm["metrics"]) == {"a", "b"}

def test_get_metrics_unknown_module_raises(reg):
    srv.add_module(map="m", id="a", label="A", domain="d")
    with pytest.raises(KeyError):
        srv.get_metrics(map="m", module="ghost")
