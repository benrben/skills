"""Interface tests for the View Builder seam.

Covers _parse_view_spec (parse-time validation + alias resolution),
_build_view (table and bar output), and _view_filter (predicate correctness).
Tests pass TableSpec/BarSpec directly to _build_view — no dict construction
past the parse seam.
"""
import pytest

from arch_map.server import (
    BarSpec,
    TableSpec,
    _build_view,
    _parse_view_spec,
    _view_filter,
)


def mod(id, domain="d", depth=0.5, leaks=None, suggestion=None, tests=""):
    return {
        "id": id, "label": id.upper(), "domain": domain,
        "depth": depth, "coverage": 0.0,
        "leaksTo": leaks or [], "suggestion": suggestion,
        "tests": tests, "files": [], "updated": False,
    }


def model(*modules, orphans=None):
    return {"repo": "Test", "modules": list(modules), "orphans": orphans or []}


# ---- _parse_view_spec: validation -------------------------------------------

def test_parse_invalid_kind():
    with pytest.raises(ValueError, match="invalid view kind"):
        _parse_view_spec({"kind": "pizza"})


def test_parse_invalid_metric():
    with pytest.raises(ValueError, match="invalid metric"):
        _parse_view_spec({"kind": "bar", "metric": "height"})


def test_parse_invalid_groupby():
    with pytest.raises(ValueError, match="invalid groupBy"):
        _parse_view_spec({"kind": "bar", "groupBy": "widget"})


def test_parse_invalid_agg():
    with pytest.raises(ValueError, match="invalid agg"):
        _parse_view_spec({"kind": "bar", "agg": "sum"})


# ---- _parse_view_spec: alias resolution -------------------------------------

def test_parse_alias_filter_resolves_to_of():
    spec = _parse_view_spec({"filter": "shallow"})
    assert isinstance(spec, TableSpec)
    assert spec.of == "shallow"


def test_parse_alias_group_resolves_to_groupby():
    spec = _parse_view_spec({"kind": "bar", "group": "domain"})
    assert isinstance(spec, BarSpec)
    assert spec.groupBy == "domain"


def test_parse_alias_sort_resolves_to_sortby():
    spec = _parse_view_spec({"sort": "depth"})
    assert isinstance(spec, TableSpec)
    assert spec.sortBy == "depth"


def test_parse_alias_sortby_dict():
    spec = _parse_view_spec({"sortBy": {"by": "coverage", "dir": "desc"}})
    assert isinstance(spec, TableSpec)
    assert spec.sortBy == "coverage"
    assert spec.sortDir == "desc"


# ---- _parse_view_spec: defaults ---------------------------------------------

def test_parse_empty_spec_yields_table_defaults():
    spec = _parse_view_spec({})
    assert isinstance(spec, TableSpec)
    assert spec.of == "all"
    assert spec.columns == ["id", "domain", "depth", "coverage"]
    assert spec.sortBy is None
    assert spec.sortDir == "asc"


def test_parse_bar_defaults():
    spec = _parse_view_spec({"kind": "bar"})
    assert isinstance(spec, BarSpec)
    assert spec.metric == "depth"
    assert spec.groupBy == "module"
    assert spec.agg == "avg"


# ---- _build_view: table -----------------------------------------------------

def test_build_view_table_default_columns():
    m = model(mod("a", depth=0.6), mod("b", depth=0.4))
    out = _build_view(m, TableSpec())
    assert out["kind"] == "table"
    assert out["columns"] == ["id", "domain", "depth", "coverage"]
    assert len(out["rows"]) == 2


def test_build_view_table_sort_desc():
    m = model(mod("a", depth=0.3), mod("b", depth=0.8), mod("c", depth=0.5))
    out = _build_view(m, TableSpec(sortBy="depth", sortDir="desc"))
    depths = [r["depth"] for r in out["rows"]]
    assert depths == sorted(depths, reverse=True)


def test_build_view_table_unknown_columns_silently_dropped():
    m = model(mod("a"))
    out = _build_view(m, TableSpec(columns=["id", "bogus", "depth"]))
    assert out["columns"] == ["id", "depth"]


def test_build_view_table_depth_scaled_to_100():
    m = model(mod("a", depth=0.75))
    out = _build_view(m, TableSpec(columns=["id", "depth"]))
    assert out["rows"][0]["depth"] == 75


def test_build_view_table_tests_checkmark():
    m = model(mod("a", tests="some tests"), mod("b", tests=""))
    out = _build_view(m, TableSpec(columns=["id", "tests"]))
    rows = {r["id"]: r["tests"] for r in out["rows"]}
    assert rows["a"] == "✓"
    assert rows["b"] == ""


# ---- _build_view: bar -------------------------------------------------------

def test_build_view_bar_domain_avg():
    m = model(
        mod("a", domain="x", depth=0.4),
        mod("b", domain="x", depth=0.6),
        mod("c", domain="y", depth=1.0),
    )
    out = _build_view(m, BarSpec(metric="depth", groupBy="domain", agg="avg"))
    bars = {b["label"]: b["pct"] for b in out["bars"]}
    assert bars["x"] == 50   # avg(0.4, 0.6) * 100
    assert bars["y"] == 100  # avg(1.0) * 100


def test_build_view_bar_domain_count():
    m = model(
        mod("a", domain="x"),
        mod("b", domain="x"),
        mod("c", domain="y"),
    )
    out = _build_view(m, BarSpec(metric="depth", groupBy="domain", agg="count"))
    bars = {b["label"]: b["value"] for b in out["bars"]}
    assert bars["x"] == "2"
    assert bars["y"] == "1"


def test_build_view_bar_module_one_bar_per_module():
    m = model(mod("a", depth=0.5), mod("b", depth=1.0))
    out = _build_view(m, BarSpec(metric="depth", groupBy="module"))
    assert len(out["bars"]) == 2
    labels = {b["label"] for b in out["bars"]}
    assert labels == {"a", "b"}


def test_build_view_bar_sorted_desc():
    m = model(mod("a", depth=0.3), mod("b", depth=0.9))
    out = _build_view(m, BarSpec(metric="depth", groupBy="module"))
    pcts = [b["pct"] for b in out["bars"]]
    assert pcts == sorted(pcts, reverse=True)


# ---- _view_filter -----------------------------------------------------------

def test_view_filter_all_returns_all():
    modules = [mod("a"), mod("b")]
    assert len(_view_filter(modules, "all", model(*modules))) == 2


def test_view_filter_shallow_returns_depth_under_034():
    modules = [mod("a", depth=0.2), mod("b", depth=0.5)]
    result = _view_filter(modules, "shallow", model(*modules))
    assert [m["id"] for m in result] == ["a"]


def test_view_filter_deep_returns_depth_gte_067():
    modules = [mod("a", depth=0.5), mod("b", depth=0.8)]
    result = _view_filter(modules, "deep", model(*modules))
    assert [m["id"] for m in result] == ["b"]


def test_view_filter_domain_returns_matching_domain():
    modules = [mod("a", domain="model"), mod("b", domain="server")]
    result = _view_filter(modules, "model", model(*modules))
    assert [m["id"] for m in result] == ["a"]


def test_view_filter_leaks_returns_modules_with_leaksto():
    modules = [mod("a", leaks=["b"]), mod("b")]
    result = _view_filter(modules, "leaks", model(*modules))
    assert [m["id"] for m in result] == ["a"]


def test_view_filter_orphans_returns_disconnected():
    modules = [mod("a"), mod("b")]
    m = {"repo": "T", "modules": modules, "orphans": ["a"]}
    result = _view_filter(modules, "orphans", m)
    assert [r["id"] for r in result] == ["a"]
