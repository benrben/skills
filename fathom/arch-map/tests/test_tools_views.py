"""Interface tests for the **MCP Tools — View Builder** slice (server.py).

Declarative on-brand table/bar views: _view_filter selects modules by a keyword
or domain; _build_view shapes the selection into a payload the renderer draws
verbatim (depth/coverage scaled to 0..100, sorted/aggregated). render_view wraps
it for the tool surface.
"""
import pytest

import arch_map.server as srv
from arch_map.model import ArchModel, Module
from arch_map.server import BarSpec, TableSpec


def built_model():
    m = ArchModel("Repo", [
        Module(id="deepc", label="Deep", domain="core", depth=0.8, size=1.0, seam="",
               coverage=0.9, tests="exercised", files=["f.py"]),
        Module(id="shallowx", label="Shallow", domain="ui", depth=0.2, size=1.0, seam="",
               coverage=0.1),
        Module(id="leaky", label="Leaky", domain="ui", depth=0.5, size=1.0, seam="",
               coverage=0.0, leaksTo=["deepc"]),
        Module(id="lonely", label="Lonely", domain="core", depth=0.5, size=1.0, seam="",
               coverage=0.0),
    ])
    return m.to_dict()


# ---- _view_filter -----------------------------------------------------------

def test_filter_all_returns_everything():
    model = built_model()
    assert len(srv._view_filter(model["modules"], "all", model)) == 4

def test_filter_leaks():
    model = built_model()
    assert [m["id"] for m in srv._view_filter(model["modules"], "leaks", model)] == ["leaky"]

def test_filter_low_coverage():
    model = built_model()
    ids = {m["id"] for m in srv._view_filter(model["modules"], "low-coverage", model)}
    assert ids == {"shallowx", "leaky", "lonely"}      # coverage < 0.4

def test_filter_depth_bands():
    model = built_model()
    f = lambda of: {m["id"] for m in srv._view_filter(model["modules"], of, model)}
    assert f("shallow") == {"shallowx"}                 # depth < 0.34
    assert f("deep") == {"deepc"}                       # depth >= 0.67
    assert f("mid") == {"leaky", "lonely"}              # 0.34 <= depth < 0.67

def test_filter_by_domain_name():
    model = built_model()
    assert {m["id"] for m in srv._view_filter(model["modules"], "core", model)} == {"deepc", "lonely"}

def test_filter_orphans():
    model = built_model()
    ids = {m["id"] for m in srv._view_filter(model["modules"], "orphans", model)}
    assert ids == {"shallowx", "lonely"}               # no edge in any direction


# ---- _build_view: table -----------------------------------------------------

def test_table_scales_and_derives_columns():
    view = srv._build_view(built_model(),
                           TableSpec(columns=["id", "depth", "coverage", "tests", "files"]))
    by_id = {r["id"]: r for r in view["rows"]}
    assert by_id["deepc"]["depth"] == 80               # scaled to 0..100
    assert by_id["deepc"]["coverage"] == 90
    assert by_id["deepc"]["tests"] == "✓"              # non-empty tests prose
    assert by_id["shallowx"]["tests"] == ""            # empty -> blank marker
    assert by_id["deepc"]["files"] == 1                # files rendered as a count

def test_table_drops_unknown_columns():
    view = srv._build_view(built_model(), TableSpec(columns=["id", "xyz"]))
    assert view["columns"] == ["id"]                   # "xyz" not in _VIEW_COLS

def test_table_sorts_by_column():
    view = srv._build_view(built_model(),
                           TableSpec(columns=["id", "depth"], sortBy="depth", sortDir="desc"))
    assert view["rows"][0]["id"] == "deepc"            # highest depth first


# ---- _build_view: bar -------------------------------------------------------

def test_bar_by_module_uses_metric_pct():
    view = srv._build_view(built_model(), BarSpec(metric="depth", groupBy="module"))
    assert view["bars"][0]["label"] == "deepc"         # sorted desc by pct
    assert view["bars"][0]["pct"] == 80

def test_bar_by_domain_average():
    view = srv._build_view(built_model(),
                           BarSpec(metric="coverage", groupBy="domain", agg="avg"))
    pct = {b["label"]: b["pct"] for b in view["bars"]}
    assert pct["core"] == 45                            # avg(0.9, 0.0) = 0.45
    assert pct["ui"] == 5                               # avg(0.1, 0.0) = 0.05

def test_bar_by_domain_count():
    view = srv._build_view(built_model(),
                           BarSpec(metric="depth", groupBy="domain", agg="count"))
    val = {b["label"]: b["value"] for b in view["bars"]}
    assert val["core"] == "2" and val["ui"] == "2"


# ---- render_view tool -------------------------------------------------------

def test_render_view_tool_wraps_builder(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d", depth=0.6)
    out = srv.render_view(map="m")
    assert out["map"] == "m"
    assert out["kind"] == "table"
    assert out["rows"][0]["id"] == "a"


def test_render_view_flat_args_table_and_bar(reg):
    srv.modules(action="add", map="m", items=[
        {"id": "a", "label": "A", "domain": "d", "depth": 0.6, "coverage": 0.2},
        {"id": "b", "label": "B", "domain": "d", "depth": 0.9, "coverage": 0.8},
    ])
    table = srv.render_view(map="m", of="all", columns=["id", "depth"],
                            sort_by="depth", sort_dir="desc")
    assert table["columns"] == ["id", "depth"]
    assert table["rows"][0]["id"] == "b"            # sorted desc by depth
    bar = srv.render_view(map="m", kind="bar", metric="coverage",
                          group_by="domain", agg="avg")
    assert bar["bars"][0]["label"] == "d"
    assert bar["bars"][0]["pct"] == 50              # avg(0.2, 0.8)


# ---- remaining filters + suggestion column -----------------------------------

def test_filter_suggestions_and_updated():
    model = built_model()
    for m in model["modules"]:
        m["updated"] = (m["id"] == "deepc")            # add_module marked all fresh
        if m["id"] == "leaky":
            m["suggestion"] = {"strength": "Strong"}
    assert [m["id"] for m in srv._view_filter(model["modules"], "suggestions", model)] == ["leaky"]
    assert [m["id"] for m in srv._view_filter(model["modules"], "updated", model)] == ["deepc"]

def test_table_suggestion_column_renders_strength_or_none():
    model = built_model()
    for m in model["modules"]:
        m["suggestion"] = {"strength": "Strong"} if m["id"] == "leaky" else None
    view = srv._build_view(model, TableSpec(columns=["id", "suggestion"]))
    rows = {r["id"]: r["suggestion"] for r in view["rows"]}
    assert rows["leaky"] == {"strength": "strong", "label": "Strong"}
    assert rows["lonely"] is None
