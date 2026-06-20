"""Interface tests for the **Suggestion Queue (Candidate FSM)** module (model.py).

The per-module deepening-candidate state machine: status open -> requested ->
grilling -> grilled -> done, plus the decision verdict and the optimistic
expect_status guard. In-process — tested directly through ArchModel.
"""
import pytest

from arch_map.model import ArchModel, Module, Suggestion


def mod(id="a"):
    return Module(id=id, label=id, domain="d", depth=0.5, size=1.0, seam="")


def sugg(id="s1", **kw):
    return Suggestion(id=id, title=kw.pop("title", "T"), strength=kw.pop("strength", "Strong"),
                      category=kw.pop("category", "in-process"), problem=kw.pop("problem", "p"),
                      solution=kw.pop("solution", "s"), **kw)


def model_with(*suggs, module="a"):
    m = ArchModel("r", [mod(module)])
    for s in suggs:
        m.add_suggestion(module, s)
    return m


# ---- add / replace ----------------------------------------------------------

def test_add_suggestion_appends_to_queue():
    m = model_with(sugg("s1"), sugg("s2"))
    assert [s.id for s in m.modules["a"].suggestions] == ["s1", "s2"]


def test_reflag_same_id_replaces_in_place():
    m = model_with(sugg("s1", title="first"))
    m.add_suggestion("a", sugg("s1", title="second"))
    suggs = m.modules["a"].suggestions
    assert len(suggs) == 1                     # not duplicated
    assert suggs[0].title == "second"          # replaced in place


def test_add_suggestion_marks_module_updated():
    m = ArchModel("r", [mod("a")])
    m.modules["a"].updated = False
    m.add_suggestion("a", sugg("s1"))
    assert m.modules["a"].updated is True


# ---- decide / resolve -------------------------------------------------------

def test_decide_unknown_suggestion_raises():
    with pytest.raises(KeyError):
        model_with().decide("ghost", "accepted")


def test_decide_records_decision_note_and_adr():
    m = model_with(sugg("s1"))
    m.decide("s1", "accepted", note="because", adr="docs/adr/0007-x.md")
    s = m.modules["a"].suggestions[0]
    assert s.decision == "accepted"
    assert s.note == "because"
    assert s.adrRef == "docs/adr/0007-x.md"


def test_decide_expect_status_guard():
    m = model_with(sugg("s1"))                 # status defaults to "open"
    with pytest.raises(ValueError):
        m.decide("s1", "accepted", expect_status="grilled")   # mismatch -> refuse
    m.decide("s1", "accepted", expect_status="open")          # match -> ok
    assert m.modules["a"].suggestions[0].decision == "accepted"


def test_resolve_marks_done_but_keeps_the_record():
    m = model_with(sugg("s1"))
    m.resolve("s1")
    suggs = m.modules["a"].suggestions
    assert len(suggs) == 1                      # persists as the durable record
    assert suggs[0].status == "done"


# ---- grilling lifecycle -----------------------------------------------------

def test_request_grilling_moves_open_to_requested():
    m = model_with(sugg("s1"))
    m.request_grilling("s1")
    assert m.modules["a"].suggestions[0].status == "requested"


def test_request_grilling_is_idempotent_mid_grill():
    m = model_with(sugg("s1"))
    m.mark_grilling("s1")                       # status -> "grilling"
    m.request_grilling("s1")                    # must NOT yank it back
    assert m.modules["a"].suggestions[0].status == "grilling"


def test_mark_grilling_then_grilled():
    m = model_with(sugg("s1"))
    m.mark_grilling("s1")
    assert m.modules["a"].suggestions[0].status == "grilling"
    m.mark_grilled("s1")
    assert m.modules["a"].suggestions[0].status == "grilled"


def test_queued_for_grilling_lists_only_requested():
    m = model_with(sugg("s1"), sugg("s2"))
    m.request_grilling("s1")                    # s2 stays open
    queued = m.queued_for_grilling()
    assert [q["suggestion_id"] for q in queued] == ["s1"]
    assert queued[0]["module"] == "a"
    assert queued[0]["strength"] == "Strong"


# ---- open-candidate computation ---------------------------------------------

def test_open_ids_exclude_decided_and_resolved():
    m = model_with(sugg("s1"), sugg("s2"), sugg("s3"))
    assert m.to_dict()["openSuggestions"] == ["s1", "s2", "s3"]
    m.decide("s1", "accepted")                  # decided -> not open
    m.resolve("s2")                             # done -> not open
    assert m.to_dict()["openSuggestions"] == ["s3"]
