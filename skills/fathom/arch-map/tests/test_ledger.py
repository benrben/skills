"""Interface tests for the **Reconcile Ledger** (ledger.py).

Every assertion crosses record_anchor / staleness_line / drift / modules_touched /
last_anchor / history — never private helpers. Persistence is proven by a real
save -> from_json round-trip (the Store contract the ledger rides)."""
import pytest

from arch_map import ledger
from arch_map.model import ArchModel, Module


def _model():
    a = Module(id="a", label="A", domain="d1", depth=0.8, size=1, seam="",
               coverage=0.5, files=["src/a.py"], dependsOn=[])
    b = Module(id="b", label="B", domain="d1", depth=0.4, size=1, seam="",
               coverage=0.0, files=["src/lib"], dependsOn=["a"])
    c = Module(id="c", label="C", domain="d2", depth=0.6, size=1, seam="",
               coverage=1.0, files=["web/app.js"], dependsOn=["a"])
    return ArchModel("t", [a, b, c])


class StubGit:
    def __init__(self, changed=None, boom=False):
        self._changed, self._boom = changed or [], boom

    def changed_files(self, since_sha):
        if self._boom:
            raise RuntimeError("kaput")
        return list(self._changed)


# ---- record ------------------------------------------------------------------
def test_record_anchor_snapshots_every_module(tmp_path):
    m = _model()
    a = ledger.record_anchor(m, "abc1234ff", "2026-06-10T12:00:00+00:00")
    assert a["sha"] == "abc1234ff" and a["moduleCount"] == 3
    snap = a["modules"]["a"]
    assert snap["depth"] == 0.8 and snap["coverage"] == 0.5 and snap["domain"] == "d1"
    assert snap["health"] == m.compute_metrics()["a"]["health"]


def test_record_anchor_persists_through_save_and_reload(tmp_path):
    m = _model()
    ledger.record_anchor(m, "abc1234ff", "2026-06-10T12:00:00+00:00")
    p = tmp_path / "map.json"
    m.save(p)
    again = ArchModel.from_json(p)
    got = ledger.last_anchor(again)
    assert got and got["sha"] == "abc1234ff" and got["ts"] == "2026-06-10T12:00:00+00:00"


def test_record_same_sha_replaces_newest_different_sha_appends():
    m = _model()
    ledger.record_anchor(m, "sha-one", "2026-06-10T12:00:00")
    ledger.record_anchor(m, "sha-one", "2026-06-10T13:00:00")   # replace
    assert len(m.anchors) == 1 and m.anchors[0]["ts"] == "2026-06-10T13:00:00"
    ledger.record_anchor(m, "sha-two", "2026-06-10T14:00:00")   # append
    assert [a["sha"] for a in m.anchors] == ["sha-one", "sha-two"]


def test_record_ring_buffer_drops_oldest():
    m = _model()
    for i in range(5):
        ledger.record_anchor(m, f"sha-{i}", "2026-06-10T12:00:00", max_anchors=3)
    assert [a["sha"] for a in m.anchors] == ["sha-2", "sha-3", "sha-4"]


def test_record_validates_inputs_and_leaves_model_untouched():
    m = _model()
    with pytest.raises(ValueError):
        ledger.record_anchor(m, "", "2026-06-10T12:00:00")
    with pytest.raises(ValueError):
        ledger.record_anchor(m, "sha", "not-a-time")
    with pytest.raises(ValueError):
        ledger.record_anchor(m, "sha", "2026-06-10T12:00:00", max_anchors=0)
    assert m.anchors == []


def test_returned_anchor_is_a_copy():
    m = _model()
    a = ledger.record_anchor(m, "sha-one", "2026-06-10T12:00:00")
    a["modules"]["a"]["depth"] = 999
    assert m.anchors[0]["modules"]["a"]["depth"] == 0.8


# ---- drift -------------------------------------------------------------------
def test_drift_never_anchored():
    d = ledger.drift(_model(), StubGit())
    assert d["anchored"] is False and d["reason"] == "no anchors"
    assert d["summary"].startswith("never anchored")
    assert set(d) == {"anchored", "sinceSha", "sinceTs", "changedFiles",
                      "modulesTouched", "unmappedFiles", "summary", "reason"}


def test_drift_clean_and_touched():
    m = _model()
    ledger.record_anchor(m, "abc1234ff", "2026-06-10T12:00:00")
    clean = ledger.drift(m, StubGit(changed=[]))
    assert clean["anchored"] and clean["summary"] == "clean — no changes since abc1234"
    d = ledger.drift(m, StubGit(changed=["src/a.py", "src/lib/x.py", "rogue.txt"]))
    assert d["modulesTouched"] == {"a": ["src/a.py"], "b": ["src/lib/x.py"]}
    assert d["unmappedFiles"] == ["rogue.txt"]
    assert d["summary"] == "3 files changed, 2 modules touched since abc1234"
    assert d["sinceSha"] == "abc1234ff" and d["sinceTs"] == "2026-06-10T12:00:00"


def test_drift_degrades_without_raising():
    m = _model()
    ledger.record_anchor(m, "abc1234ff", "2026-06-10T12:00:00")
    no_git = ledger.drift(m, None)
    assert no_git["anchored"] is False and no_git["reason"] == "no git repo"
    boom = ledger.drift(m, StubGit(boom=True))
    assert boom["anchored"] is False and boom["reason"].startswith("git error")
    assert "git unavailable" in boom["summary"]


def test_drift_explicit_since_sha_overrides_last_anchor():
    m = _model()
    ledger.record_anchor(m, "newer-sha", "2026-06-10T12:00:00")
    d = ledger.drift(m, StubGit(changed=["web/app.js"]), since_sha="older-sha")
    assert d["sinceSha"] == "older-sha" and d["modulesTouched"] == {"c": ["web/app.js"]}


def test_modules_touched_is_pure_and_multi_owner():
    m = _model()
    m.modules["a"].files = ["src/a.py", "src/lib"]   # src/lib owned by a AND b
    t = ledger.modules_touched(m, ["./src/lib/x.py"])
    assert t == {"a": ["src/lib/x.py"], "b": ["src/lib/x.py"]}
    assert ledger.modules_touched(m, ["nope"]) == {}


def test_staleness_line_is_total():
    m = _model()
    assert ledger.staleness_line(m, None).startswith("never anchored")
    ledger.record_anchor(m, "abc1234ff", "2026-06-10T12:00:00")
    assert ledger.staleness_line(m, StubGit(boom=True)) == \
        "anchored at abc1234 — git unavailable"
    assert ledger.staleness_line(m, StubGit(changed=[])).startswith("clean")


# ---- history -----------------------------------------------------------------
def test_history_series_align_with_anchors():
    m = _model()
    ledger.record_anchor(m, "s1", "2026-06-01T00:00:00")
    m.modules["a"].depth = 0.9
    m.modules["d"] = Module(id="d", label="D", domain="d2", depth=0.1, size=1, seam="")
    ledger.record_anchor(m, "s2", "2026-06-08T00:00:00")
    h = ledger.history(m)
    assert [x["sha"] for x in h["anchors"]] == ["s1", "s2"]
    assert h["series"]["a"]["depth"] == [0.8, 0.9]
    assert h["series"]["d"]["depth"] == [None, 0.1]        # absent at s1 -> None gap


def test_history_domain_mean_and_filters():
    m = _model()
    ledger.record_anchor(m, "s1", "2026-06-01T00:00:00")
    h = ledger.history(m, domain="d1", metrics=("depth",))
    assert h["series"]["d1"]["depth"] == [pytest.approx((0.8 + 0.4) / 2)]
    with pytest.raises(ValueError):
        ledger.history(m, module_id="a", domain="d1")
    with pytest.raises(ValueError):
        ledger.history(m, module_id="ghost")
    with pytest.raises(ValueError):
        ledger.history(m, metrics=("bogus",))


def test_history_zero_anchors_is_empty_not_error():
    assert ledger.history(_model()) == {"anchors": [], "series": {}}


def test_tolerant_reader_skips_malformed_anchor_entries():
    m = _model()
    ledger.record_anchor(m, "good", "2026-06-01T00:00:00")
    m.anchors.append({"sha": "no-modules", "ts": "2026-06-02T00:00:00"})
    assert ledger.last_anchor(m)["sha"] == "good"
    assert len(ledger.history(m)["anchors"]) == 1
