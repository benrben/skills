"""Interface tests for the **Import Graph Verifier** (import_graph.py).

Fixture mini-packages with known imports; assertions cross extract/verify only."""
import pytest

from arch_map.import_graph import extract, verify
from arch_map.model import ArchModel, Module


@pytest.fixture
def tree(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("import pkg.b\n")
    (pkg / "b.py").write_text("x = 1\n")
    (pkg / "x.py").write_text("from pkg import b\n")
    web = tmp_path / "web"
    web.mkdir()
    (web / "app.js").write_text("import {u} from './util.js';\n")
    (web / "util.js").write_text("export const u = 1;\n")
    (tmp_path / "bad.py").write_text("def (\n")
    return tmp_path


def _model():
    ma = Module(id="ma", label="A", domain="d", depth=0.5, size=1, seam="",
                files=["pkg/a.py"], dependsOn=["mb"])
    mb = Module(id="mb", label="B", domain="d", depth=0.5, size=1, seam="",
                files=["pkg/b.py", "pkg/__init__.py"])
    mx = Module(id="mx", label="X", domain="d", depth=0.5, size=1, seam="",
                files=["pkg/x.py"], dependsOn=[])
    mweb = Module(id="mweb", label="Web", domain="w", depth=0.5, size=1, seam="",
                  files=["web/app.js", "web/util.js"], dependsOn=["ma"])
    mbad = Module(id="mbad", label="Bad", domain="d", depth=0.5, size=1, seam="",
                  files=["bad.py"])
    mdoc = Module(id="mdoc", label="Doc", domain="d", depth=0.5, size=1, seam="",
                  files=["README.md"], dependsOn=["ma"])
    return ArchModel("t", [ma, mb, mx, mweb, mbad, mdoc])


def test_extract_python_absolute_and_from_imports(tree):
    out = extract(tree, ["pkg/a.py", "pkg/b.py", "pkg/x.py"])
    assert ("pkg/a.py", "pkg/b.py") in out["edges"]
    assert ("pkg/x.py", "pkg/b.py") in out["edges"]
    assert out["unparseable"] == []


def test_extract_js_relative_imports(tree):
    out = extract(tree, ["web/app.js", "web/util.js"])
    assert ("web/app.js", "web/util.js") in out["edges"]


def test_extract_soft_skips_unparseable_and_completes(tree):
    out = extract(tree, ["bad.py", "pkg/a.py"])
    assert out["unparseable"] == ["bad.py"]
    assert ("pkg/a.py", "pkg/b.py") in out["edges"]


def test_verify_buckets_edges(tree):
    v = verify(_model(), tree)
    assert v["confirmedEdges"] == ["ma->mb"]            # recorded AND observed
    assert "mx->mb" in v["undeclaredEdges"]             # observed, not recorded
    assert v["missingEdges"] == ["mweb->ma"]            # recorded, both checkable, unobserved
    assert v["unparseable"] == ["bad.py"]
    # mdoc->ma is recorded and unobserved but mdoc owns no source -> NOT missing
    assert "mdoc->ma" not in v["missingEdges"]
    assert "mdoc" not in v["checkedModules"]
    assert v["filesAnalyzed"] == 6


def test_verify_never_mutates_model(tree):
    m = _model()
    before = {mid: list(mod.dependsOn) for mid, mod in m.modules.items()}
    verify(m, tree)
    assert {mid: list(mod.dependsOn) for mid, mod in m.modules.items()} == before
