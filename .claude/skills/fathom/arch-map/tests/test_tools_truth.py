"""Interface tests for the **ground-truth tool surface** (server.py): archmap_ingest /
archmap_drift / archmap_history / archmap_verify_edges / archmap_whatif, the digest
staleness line, and the /api/whatif route. Real git in throwaway repos."""
import subprocess

import pytest

import arch_map.server as srv


def _git(root, *args):
    subprocess.run(["git", "-C", str(root),
                    "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false", *args],
                   check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    # NB: a subdirectory — tmp_path itself also hosts the reg fixture's maps/,
    # which must never leak into the repo's git history.
    root = tmp_path / "repo"
    (root / "src" / "lib").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    (root / "src" / "a.py").write_text("import src.lib.b\n")
    (root / "src" / "lib" / "b.py").write_text("x = 1\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "c1")
    return root


@pytest.fixture
def truthmap(reg, repo):
    srv.create_project(name="T", map_id="t")
    srv.modules(action="add", map="t", items=[
        {"id": "a", "label": "A", "domain": "d", "files": ["src/a.py"]},
        {"id": "b", "label": "B", "domain": "d", "files": ["src/lib"]},
    ])
    return repo


def _commit_change(repo):
    (repo / "src" / "a.py").write_text("import src.lib.b\ny = 2\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "change")


def test_ingest_measures_churn_and_records_anchor(truthmap):
    srv.modules(action="update", map="t", ids=["*"], updated=False)  # clear halos
    out = srv.ingest(map="t", root=str(truthmap))
    assert out["ok"] and out["churned"] == 2
    assert out["anchor"]["moduleCount"] == 2 and len(out["anchor"]["sha"]) == 40
    assert out["loc"] == {"a": 1, "b": 1}
    assert out["sized"] == 2                         # measured LOC written to size
    rec = srv.modules(action="get", map="t", id="a")
    assert rec["churn"] == 1.0                      # every window commit touches it
    assert rec["size"] == 1.0                       # both modules at the median -> 1.0
    assert rec["updated"] is False                  # ingest never flips halos


def test_ingest_scales_size_from_loc_and_fires_bulky_impl(reg, tmp_path):
    # A big shallow module beside a small one: measured LOC should make the big
    # one's size >= 2x the median and light up the bulky-impl signal end-to-end.
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    (root / "src" / "big.py").write_text("\n".join(f"x{i} = {i}" for i in range(50)) + "\n")
    (root / "src" / "s1.py").write_text("\n".join(["a = 1"] * 5) + "\n")
    (root / "src" / "s2.py").write_text("\n".join(["b = 2"] * 5) + "\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "c1")
    srv.create_project(name="S", map_id="s")
    srv.modules(action="add", map="s", items=[
        {"id": "big", "label": "Big", "domain": "d", "files": ["src/big.py"], "depth": 0.2},
        {"id": "s1", "label": "S1", "domain": "d", "files": ["src/s1.py"], "depth": 0.2},
        {"id": "s2", "label": "S2", "domain": "d", "files": ["src/s2.py"], "depth": 0.2},
    ])
    out = srv.ingest(map="s", root=str(root))
    assert out["sized"] == 3
    assert srv.modules(action="get", map="s", id="big")["size"] >= 2.0   # 50 LOC / median 5
    assert srv.modules(action="get", map="s", id="s1")["size"] == 1.0    # at the median
    flagged = srv.scan_signals(map="s", signal="bulky-impl")
    flagged_ids = {r["id"] for r in flagged["modules"]}
    assert "big" in flagged_ids
    assert "s1" not in flagged_ids and "s2" not in flagged_ids


def test_ingest_leaves_intended_and_fileless_modules_unsized(reg, tmp_path):
    # ingest measures only actual-plane modules with files; an intended module
    # (no files) keeps the size it was given and never enters out["sized"].
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    (root / "src" / "real.py").write_text("\n".join(f"x{i} = {i}" for i in range(10)) + "\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "c1")
    srv.create_project(name="P", map_id="p")
    srv.modules(action="add", map="p", items=[
        {"id": "real", "label": "Real", "domain": "d", "files": ["src/real.py"], "depth": 0.2},
        {"id": "planned", "label": "Planned", "domain": "d", "plane": "intended", "size": 1.5, "depth": 0.2},
    ])
    out = srv.ingest(map="p", root=str(root))
    assert out["sized"] == 1                               # only the actual module with files
    assert srv.modules(action="get", map="p", id="real")["size"] == 1.0     # self-normalized
    assert srv.modules(action="get", map="p", id="planned")["size"] == 1.5  # estimate untouched


def test_ingest_patches_coverage_from_report(truthmap, tmp_path):
    (tmp_path / "cov.info").write_text(
        "SF:src/a.py\nLF:10\nLH:9\nend_of_record\n")
    srv.ingest(map="t", root=str(truthmap), coverage_report=str(tmp_path / "cov.info"))
    assert srv.modules(action="get", map="t", id="a")["coverage"] == pytest.approx(0.9)


def test_drift_clean_then_touched(truthmap):
    srv.ingest(map="t", root=str(truthmap))
    clean = srv.drift(map="t", root=str(truthmap))
    assert clean["anchored"] and clean["summary"].startswith("clean")
    _commit_change(truthmap)
    d = srv.drift(map="t", root=str(truthmap))
    assert d["modulesTouched"] == {"a": ["src/a.py"]}
    assert d["summary"] == f"1 files changed, 1 modules touched since {d['sinceSha'][:7]}"


def test_drift_never_anchored_is_degraded_not_error(truthmap):
    d = srv.drift(map="t", root=str(truthmap))
    assert d["anchored"] is False and d["reason"] == "no anchors"


def test_history_across_two_anchors(truthmap):
    srv.ingest(map="t", root=str(truthmap))
    _commit_change(truthmap)
    srv.ingest(map="t", root=str(truthmap))
    h = srv.history(map="t")
    assert len(h["anchors"]) == 2
    assert len(h["series"]["a"]["health"]) == 2
    one = srv.history(map="t", module="a", metrics=["depth"])
    assert set(one["series"]) == {"a"} and len(one["series"]["a"]["depth"]) == 2


def test_show_map_digest_carries_staleness_line(reg):
    srv.create_project(name="S", map_id="s")
    digest = srv.show_map(map="s")
    assert digest["staleness"].startswith("never anchored")


def test_verify_edges_buckets(truthmap):
    v = srv.verify_edges(map="t", root=str(truthmap))
    assert "a->b" in v["undeclaredEdges"]           # real import, no recorded edge
    assert v["confirmedEdges"] == [] and v["unparseable"] == []


def test_whatif_tool_and_error_contract(truthmap):
    out = srv.whatif(map="t", ids=["a", "b"])
    assert out["merged"]["fanIn"] == 0 and out["ids"] == ["a", "b"]
    with pytest.raises(ValueError, match="archmap_whatif"):
        srv.whatif(map="t", ids=["a"])


def test_api_whatif_route(client, truthmap):
    ok = client.get("/api/whatif?map=t&ids=a,b")
    assert ok.status_code == 200 and ok.json()["merged"]["fanOut"] == 0
    bad = client.get("/api/whatif?map=t&ids=a")
    assert bad.status_code == 400 and "error" in bad.json()
