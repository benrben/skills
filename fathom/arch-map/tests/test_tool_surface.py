"""Interface tests for the agent-facing tool-surface guarantees added by the
mcp-design-audit pass: archmap_* MCP names, contextual all-or-nothing error
messages, unresolvedEdges surfacing, server-side edge merge + broadcast update,
slim docs list, flattened docs scope, and the tests-column truthiness rule.
"""
import pytest

import arch_map.server as srv
from arch_map.server import TableSpec


# ---- MCP names: prefixed for discovery, python names unchanged ---------------

def test_tools_are_registered_with_archmap_prefix():
    import asyncio
    expected = {
        "archmap_list_maps", "archmap_create_map", "archmap_rename_map",
        "archmap_delete_map", "archmap_show_map", "archmap_get_full_model",
        "archmap_render_view", "archmap_get_metrics", "archmap_scan_signals",
        "archmap_modules", "archmap_suggestions", "archmap_grilling",
        "archmap_plans", "archmap_docs",
        "archmap_ingest", "archmap_drift", "archmap_history",
        "archmap_verify_edges", "archmap_whatif",
    }
    names = {t.name for t in asyncio.run(srv.mcp.get_tools()).values()}
    # Lane 2 (optional prefab extra) contributes its own provider tools; only
    # the tools THIS server registers must carry the service prefix.
    ours = {n for n in names if "prefab" not in n}
    assert ours == expected                         # every tool service-prefixed


# ---- errors carry context, atomicity, and a next step ------------------------

def test_dispatcher_error_carries_context_and_atomicity(reg):
    srv.create_project(name="M", map_id="m")
    with pytest.raises(KeyError) as e:
        srv.modules(action="update", map="m", id="ghost", depth=0.1)
    msg = str(e.value)
    assert "archmap_modules(action='update', id='ghost')" in msg
    assert "Nothing was written" in msg
    assert "archmap_show_map" in msg                 # the next step


def test_bulk_add_failure_is_atomic_and_says_so(reg):
    srv.create_project(name="M", map_id="m")
    with pytest.raises((KeyError, ValueError)) as e:
        srv.modules(action="add", map="m", items=[
            {"id": "ok", "label": "OK", "domain": "d"},
            {"id": "bad"},                           # missing label/domain
        ])
    assert "Nothing was written" in str(e.value)
    assert srv.show_map(map="m")["moduleCount"] == 0  # atomic: first item not kept


def test_read_errors_have_context_but_no_atomicity_note(reg):
    srv.create_project(name="M", map_id="m")
    with pytest.raises(KeyError) as e:
        srv.modules(action="get", map="m", id="ghost")
    assert "archmap_modules(action='get'" in str(e.value)
    assert "Nothing was written" not in str(e.value)


# ---- unresolvedEdges: dangling edge targets surface in the ack ----------------

def test_ack_surfaces_dangling_edges(reg):
    ack = srv.modules(action="add", map="m", id="a", label="A", domain="d",
                      dependsOn=["typo-id"])
    assert ack["unresolvedEdges"] == ["a->typo-id"]
    srv.modules(action="add", map="m", id="typo-id", label="T", domain="d")
    ack2 = srv.modules(action="update", map="m", id="a", depth=0.5)
    assert "unresolvedEdges" not in ack2             # resolved -> key absent


# ---- edge merge + broadcast update -------------------------------------------

def test_depends_on_add_and_remove_merge_server_side(reg):
    srv.modules(action="add", map="m", items=[
        {"id": "a", "label": "A", "domain": "d"},
        {"id": "b", "label": "B", "domain": "d"},
        {"id": "c", "label": "C", "domain": "d", "dependsOn": ["a"]},
    ])
    srv.modules(action="update", map="m", id="c", dependsOnAdd=["b"])
    assert srv.modules(action="get", map="m", id="c")["dependsOn"] == ["a", "b"]
    srv.modules(action="update", map="m", id="c", dependsOnRemove=["a"])
    assert srv.modules(action="get", map="m", id="c")["dependsOn"] == ["b"]
    srv.modules(action="update", map="m", id="c",
                leaksToAdd=["a"], dependsOnAdd=["b"])   # add is idempotent
    rec = srv.modules(action="get", map="m", id="c")
    assert rec["dependsOn"] == ["b"] and rec["leaksTo"] == ["a"]


def test_broadcast_update_with_ids_and_star(reg):
    srv.modules(action="add", map="m", items=[
        {"id": "a", "label": "A", "domain": "d"},
        {"id": "b", "label": "B", "domain": "d"},
        {"id": "c", "label": "C", "domain": "d"},
    ])
    srv.modules(action="update", map="m", ids=["a", "b"], coverage=0.7)
    assert srv.modules(action="get", map="m", id="a")["coverage"] == 0.7
    assert srv.modules(action="get", map="m", id="c")["coverage"] == 0.0
    srv.modules(action="update", map="m", ids=["*"], updated=False)
    got = srv.modules(action="get", map="m", ids=["a", "b", "c"])["modules"]
    assert all(r["updated"] is False for r in got)


# ---- docs: slim list, opt-in membership, flattened scope ----------------------

def test_docs_list_is_slim_and_membership_is_opt_in(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    srv.docs(action="add", map="m", doc_id="d1", type="note", title="One",
             body="a very long body " * 50, scope_kind="system")
    listed = srv.docs(action="list", map="m")
    assert "docMembership" not in listed
    entry = listed["docs"][0]
    assert "body" not in entry and "resolvedModuleIds" not in entry
    assert entry["moduleCount"] == 1
    assert entry["scopeLabel"].startswith("Whole system")
    with_members = srv.docs(action="list", map="m", include_membership=True)
    assert with_members["docMembership"]["a"] == ["d1"]
    assert "body" in srv.docs(action="get", map="m", doc_id="d1")  # full record via get


def test_docs_flat_scope_args(reg):
    srv.modules(action="add", map="m", items=[
        {"id": "a", "label": "A", "domain": "ui", "coverage": 0.1},
        {"id": "b", "label": "B", "domain": "core", "coverage": 0.9},
    ])
    srv.docs(action="add", map="m", doc_id="dom", type="note", title="UI",
             scope_domain="ui")                       # kind inferred from the arg
    assert srv.docs(action="get", map="m", doc_id="dom")["resolvedModuleIds"] == ["a"]
    srv.docs(action="add", map="m", doc_id="ids", type="note", title="Explicit",
             scope_kind="explicit", scope_ids=["b"])
    assert srv.docs(action="get", map="m", doc_id="ids")["resolvedModuleIds"] == ["b"]
    srv.docs(action="add", map="m", doc_id="qry", type="note", title="LowCov",
             query_coverage_lte=0.4)
    assert srv.docs(action="get", map="m", doc_id="qry")["resolvedModuleIds"] == ["a"]
    srv.docs(action="update", map="m", doc_id="dom", title="UI v2")  # no scope args
    d = srv.docs(action="get", map="m", doc_id="dom")
    assert d["title"] == "UI v2" and d["scope"]["kind"] == "domain"  # scope untouched


# ---- tests column: prose saying "none" is not a checkmark ---------------------

def test_tests_column_treats_none_prose_as_untested():
    model = {"repo": "r", "orphans": [], "modules": [
        {"id": "t1", "domain": "d", "tests": "tests/test_x.py crosses the seam"},
        {"id": "t2", "domain": "d", "tests": "none — browser-only"},
        {"id": "t3", "domain": "d", "tests": "N/A"},
        {"id": "t4", "domain": "d", "tests": ""},
    ]}
    view = srv._build_view(model, TableSpec(columns=["id", "tests"]))
    cells = {r["id"]: r["tests"] for r in view["rows"]}
    assert cells == {"t1": "✓", "t2": "", "t3": "", "t4": ""}


def test_dispatcher_wraps_unexpected_error_as_valueerror(reg):
    srv.create_project(name="M", map_id="m")
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    with pytest.raises(ValueError) as e:           # TypeError surfaced, not swallowed
        srv.modules(action="update", map="m", id="a", depth="not-a-number")
    msg = str(e.value)
    assert "TypeError" in msg
    assert "Nothing was written" in msg
