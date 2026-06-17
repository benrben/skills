"""coverage-ingest — read real test-coverage reports and map them onto modules.

Pure parser: a report file in, per-file coverage out. In-process seam — tested
directly through the interface with fixture reports; no adapters. Never mutates
the model.

Interface (the test surface):
  read_report(path)            -> CoverageReport, a {file: fraction 0..1} mapping
                                  (coverage.py XML/JSON and lcov auto-detected;
                                  UnknownFormat otherwise). Line weights ride
                                  along hidden for module aggregation.
  module_coverage(model, report) -> {module_id: fraction} line-weighted via each
                                  module's files (the model's ownership rule);
                                  report files owned by NO module are aggregated
                                  under "_unmapped". Modules with no measured
                                  files are omitted, not zeroed.
"""
from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree


class UnknownFormat(Exception):
    """The report is not coverage.py XML/JSON or lcov."""


def _norm(p: str) -> str:
    p = str(p).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


class CoverageReport(dict):
    """{file: fraction 0..1}. The per-file line totals used for weighting are an
    implementation detail behind the seam — callers see a plain mapping."""

    def __init__(self, fractions: dict, lines: dict):
        super().__init__(fractions)
        self._lines = dict(lines)


def read_report(path: str | Path) -> CoverageReport:
    text = Path(path).read_text(encoding="utf-8")
    head = text.lstrip()
    if head.startswith("{"):
        return _read_coverage_json(text, path)
    if head.startswith("<"):
        return _read_cobertura_xml(text, path)
    if any(ln.startswith("SF:") for ln in text.splitlines()):
        return _read_lcov(text)
    raise UnknownFormat(f"{path}: not coverage.py XML/JSON or lcov")


def _read_coverage_json(text: str, path) -> CoverageReport:
    try:
        data = json.loads(text)
        files = data["files"]
        fractions, lines = {}, {}
        for f, rec in files.items():
            s = rec["summary"]
            total = int(s["num_statements"])
            covered = int(s["covered_lines"])
            fractions[_norm(f)] = (covered / total) if total else 1.0
            lines[_norm(f)] = total or 1
        return CoverageReport(fractions, lines)
    except (KeyError, TypeError, ValueError) as e:
        raise UnknownFormat(f"{path}: not a coverage.py JSON report ({e})") from e


def _read_cobertura_xml(text: str, path) -> CoverageReport:
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as e:
        raise UnknownFormat(f"{path}: not parseable XML ({e})") from e
    if root.tag != "coverage":
        raise UnknownFormat(f"{path}: XML but not a Cobertura coverage report")
    fractions, lines = {}, {}
    for cls in root.iter("class"):
        f = _norm(cls.get("filename") or "")
        if not f:
            continue
        fractions[f] = float(cls.get("line-rate") or 0.0)
        lines[f] = len(list(cls.iter("line"))) or 1
    return CoverageReport(fractions, lines)


def _read_lcov(text: str) -> CoverageReport:
    fractions, lines = {}, {}
    cur, total, hit = None, 0, 0
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith("SF:"):
            cur, total, hit = _norm(ln[3:]), 0, 0
        elif ln.startswith("DA:") and cur:
            total += 1
            if int(ln[3:].split(",")[1]) > 0:
                hit += 1
        elif ln.startswith("LF:") and cur:
            total = int(ln[3:])
        elif ln.startswith("LH:") and cur:
            hit = int(ln[3:])
        elif ln == "end_of_record" and cur:
            fractions[cur] = (hit / total) if total else 1.0
            lines[cur] = total or 1
            cur = None
    return CoverageReport(fractions, lines)


def module_coverage(model, report) -> dict[str, float]:
    """Line-weighted coverage per module: each module's fraction is the weighted
    mean over the report files it owns. Pure; the model is never mutated."""
    weights = getattr(report, "_lines", {})
    owned = model.owners_of(list(report.keys()))
    out: dict[str, float] = {}
    claimed: set[str] = set()
    for mid, files in owned.items():
        out[mid] = _weighted(files, report, weights)
        claimed.update(files)
    unmapped = [f for f in report if f not in claimed]
    if unmapped:
        out["_unmapped"] = _weighted(unmapped, report, weights)
    return out


def _weighted(files, report, weights) -> float:
    w = [(report[f], weights.get(f, 1)) for f in files]
    total = sum(n for _, n in w) or 1
    return max(0.0, min(1.0, sum(frac * n for frac, n in w) / total))
