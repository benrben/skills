"""Interface tests for the **Coverage Report Reader** (coverage_ingest.py).

Fixture reports for all three formats; weighting is asserted through the public
module_coverage result (the only place it is observable)."""
import pytest

from arch_map.coverage_ingest import UnknownFormat, module_coverage, read_report
from arch_map.model import ArchModel, Module

_LCOV = """TN:
SF:src/a.py
DA:1,1
DA:2,0
end_of_record
SF:src/lib/b.py
LF:10
LH:5
end_of_record
"""

_JSON = """{
  "files": {
    "src/a.py":     {"summary": {"covered_lines": 90, "num_statements": 100}},
    "src/lib/b.py": {"summary": {"covered_lines": 0,  "num_statements": 10}}
  }
}"""

_XML = """<?xml version="1.0" ?>
<coverage line-rate="0.5">
  <packages><package><classes>
    <class filename="src/a.py" line-rate="0.9">
      <lines><line number="1" hits="1"/><line number="2" hits="1"/></lines>
    </class>
    <class filename="src/lib/b.py" line-rate="0.0">
      <lines><line number="1" hits="0"/></lines>
    </class>
  </classes></package></packages>
</coverage>
"""


def _model():
    m1 = Module(id="m1", label="M1", domain="d", depth=0.5, size=1, seam="",
                files=["src/a.py", "src/lib"])
    return ArchModel("t", [m1])


def test_reads_lcov(tmp_path):
    p = tmp_path / "cov.info"
    p.write_text(_LCOV)
    r = read_report(p)
    assert r["src/a.py"] == pytest.approx(0.5)        # DA counting
    assert r["src/lib/b.py"] == pytest.approx(0.5)    # LF/LH override


def test_reads_coverage_py_json(tmp_path):
    p = tmp_path / "cov.json"
    p.write_text(_JSON)
    r = read_report(p)
    assert r["src/a.py"] == pytest.approx(0.9)
    assert r["src/lib/b.py"] == 0.0


def test_reads_cobertura_xml(tmp_path):
    p = tmp_path / "cov.xml"
    p.write_text(_XML)
    r = read_report(p)
    assert r["src/a.py"] == pytest.approx(0.9)
    assert r["src/lib/b.py"] == 0.0


def test_unknown_format_raises(tmp_path):
    p = tmp_path / "junk.txt"
    p.write_text("hello\nworld\n")
    with pytest.raises(UnknownFormat):
        read_report(p)
    p2 = tmp_path / "other.xml"
    p2.write_text("<notcoverage></notcoverage>")
    with pytest.raises(UnknownFormat):
        read_report(p2)


def test_module_coverage_is_line_weighted(tmp_path):
    p = tmp_path / "cov.json"
    p.write_text(_JSON)
    out = module_coverage(_model(), read_report(p))
    # m1 owns both files: (0.9*100 + 0.0*10) / 110
    assert out["m1"] == pytest.approx(90 / 110)
    assert "_unmapped" not in out


def test_module_coverage_unmapped_bucket(tmp_path):
    p = tmp_path / "cov.json"
    p.write_text("""{"files": {"elsewhere/x.py":
        {"summary": {"covered_lines": 1, "num_statements": 2}}}}""")
    out = module_coverage(_model(), read_report(p))
    assert out == {"_unmapped": pytest.approx(0.5)}


def test_module_coverage_never_mutates_model(tmp_path):
    p = tmp_path / "cov.json"
    p.write_text(_JSON)
    model = _model()
    before = model.modules["m1"].coverage
    module_coverage(model, read_report(p))
    assert model.modules["m1"].coverage == before
