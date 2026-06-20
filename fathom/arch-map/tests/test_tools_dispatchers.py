"""Interface tests for the **action-dispatch tools** (server.py).

The five rich resources (modules / suggestions / grilling / plans / docs) are
exposed as single action-routed tools to keep the agent's surface <=15. These
tests lock the action routing and the dispatcher-level argument guards (the
ValueError branches that tell the agent which args an action needs) — the
per-action behavior itself is covered by the resource-slice test files.
"""
import pytest

import arch_map.server as srv


# ---- modules: action routing + arg guards -----------------------------------

def test_modules_single_and_bulk_roundtrip(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    srv.modules(action="add", map="m", items=[{"id": "b", "label": "B", "domain": "d"}])
    assert srv.modules(action="get", map="m", id="a")["id"] == "a"
    assert {r["id"] for r in srv.modules(action="get", map="m", ids=["a", "b"])["modules"]} == {"a", "b"}
    srv.modules(action="update", map="m", id="a", depth=0.9)
    assert srv.modules(action="get", map="m", id="a")["depth"] == 0.9
    srv.modules(action="delete", map="m", ids=["a", "b"])
    assert srv.show_map(map="m")["moduleCount"] == 0


def test_modules_realize_flips_plane(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d",
                plane="intended", lifecycle="planned")
    srv.modules(action="realize", map="m", id="a", depth=0.8, coverage=0.5)
    rec = srv.modules(action="get", map="m", id="a")
    assert rec["plane"] == "actual" and rec["lifecycle"] == "built"
    assert rec["depth"] == 0.8


def test_modules_guards(reg):
    srv.create_project(name="M", map_id="m")
    for kw in ({"action": "get"}, {"action": "update"}, {"action": "delete"},
               {"action": "realize"}):
        with pytest.raises(ValueError):
            srv.modules(map="m", **kw)          # no id / ids -> actionable error


# ---- suggestions: flag -> decide -> dismiss ----------------------------------

def test_suggestions_lifecycle(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    srv.suggestions(action="flag", map="m", module="a", title="Deepen A",
                    strength="Strong", category="in-process", problem="p",
                    solution="s", wins=["w"])
    sid = "a-strong"                            # f"{module}-{strength}" slugged
    srv.suggestions(action="decide", map="m", suggestion_id=sid, decision="accepted", note="ok")
    assert srv.modules(action="get", map="m", id="a")["suggestions"][0]["decision"] == "accepted"
    srv.suggestions(action="dismiss", map="m", suggestion_id=sid)


def test_suggestions_guards(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    with pytest.raises(ValueError):
        srv.suggestions(action="flag", map="m", module="a")      # missing title/strength
    with pytest.raises(ValueError):
        srv.suggestions(action="decide", map="m")                # missing suggestion_id


# ---- grilling: start returns a prompt; queue; mark/finish --------------------

def test_grilling_lifecycle(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    srv.suggestions(action="flag", map="m", module="a", title="T", strength="Strong",
                    category="in-process", problem="p", solution="s", wins=[])
    out = srv.grilling(action="start", map="m", module="a")
    assert out["suggestion_id"] == "a-strong" and "grilling" in out["prompt"].lower()
    assert srv.grilling(action="queue", map="m")["queued"]       # the candidate is requested
    srv.grilling(action="mark", map="m", suggestion_id="a-strong")
    srv.grilling(action="finish", map="m", suggestion_id="a-strong", decision="rejected", note="no")
    with pytest.raises(ValueError):
        srv.grilling(action="finish", map="m", suggestion_id="a-strong")   # missing decision


# ---- plans: create / add_steps / set_step_status / update / get -------------

def test_plans_lifecycle(reg):
    srv.plans(action="create", map="m", plan_id="p1", title="P", intent="i")
    srv.plans(action="add_steps", map="m", plan_id="p1", steps=[{"id": "s1", "title": "S"}])
    srv.plans(action="set_step_status", map="m", plan_id="p1", step_id="s1", step_status="done")
    srv.plans(action="update", map="m", plan_id="p1", status="active")
    plan = srv.plans(action="get", map="m", plan_id="p1")
    assert plan["status"] == "active"
    assert plan["steps"][0]["status"] == "done"


# ---- docs: add / get / list (paged) / update / delete -----------------------

def test_docs_lifecycle_and_list(reg):
    srv.docs(action="add", map="m", doc_id="d1", type="adr", title="One")
    srv.docs(action="add", map="m", doc_id="d2", type="note", title="Two")
    assert srv.docs(action="get", map="m", doc_id="d1")["title"] == "One"
    listed = srv.docs(action="list", map="m", limit=1, offset=0)
    assert listed["total_count"] == 2 and len(listed["docs"]) == 1 and listed["has_more"] is True
    srv.docs(action="update", map="m", doc_id="d1", status="accepted")
    assert srv.docs(action="get", map="m", doc_id="d1")["status"] == "accepted"
    srv.docs(action="delete", map="m", doc_id="d1")
    with pytest.raises(KeyError):
        srv.docs(action="get", map="m", doc_id="d1")


def test_docs_add_guard(reg):
    srv.create_project(name="M", map_id="m")
    with pytest.raises(ValueError):
        srv.docs(action="add", map="m", doc_id="d1")             # missing type/title
