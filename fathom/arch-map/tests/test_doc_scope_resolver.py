"""Interface tests for the **Doc Scope Resolver** module (model.py).

The interface is the test surface: resolve(scope, model) and resolve_all(docs,
model) only. These assert the four scope-kind semantics, the explicit-only drift
split, deterministic sorted output, errors-as-data (empty is a value, malformed
soft-fails in the batch), the query predicate over every field, and that
resolve_all's inverted MembershipIndex is the transpose of byDoc. Pure function
of (scope/docs, model) — fixtures are literal models, no mocks.
"""
from arch_map.model import (ArchModel, Doc, Module, Scope, Suggestion,
                            MembershipIndex, resolve, resolve_all)


def mod(id, *, domain="d", depth=0.5, coverage=0.0, **kw):
    return Module(id=id, label=id, domain=domain, depth=depth, size=1.0,
                  seam="", coverage=coverage, **kw)


def model(*modules):
    return ArchModel("repo", list(modules))


def scope(kind, **kw):
    return Scope(kind=kind, **kw)


# ---- system -----------------------------------------------------------------

def test_system_resolves_to_all_sorted():
    m = model(mod("c"), mod("a"), mod("b"))
    r = resolve(scope("system"), m)
    assert r.ids == ["a", "b", "c"]            # sorted, all
    assert r.missing == []
    assert r.count == 3 and r.empty is False
    assert "Whole system" in r.label

def test_system_on_empty_model_is_empty_not_error():
    r = resolve(scope("system"), model())
    assert r.ids == [] and r.empty is True


# ---- explicit (the only kind that drifts) -----------------------------------

def test_explicit_splits_present_and_missing():
    m = model(mod("a"), mod("b"))
    r = resolve(scope("explicit", ids=["b", "a", "ghost"]), m)
    assert r.ids == ["a", "b"]                 # present, sorted
    assert r.missing == ["ghost"]             # drift
    assert r.count == 2                        # count excludes missing
    assert "1 missing" in r.label

def test_explicit_dedupes():
    m = model(mod("a"))
    r = resolve(scope("explicit", ids=["a", "a", "a"]), m)
    assert r.ids == ["a"]

def test_explicit_empty_list_is_empty():
    r = resolve(scope("explicit", ids=[]), model(mod("a")))
    assert r.ids == [] and r.missing == [] and r.empty is True


# ---- domain (containment == same domain) ------------------------------------

def test_domain_selects_same_domain():
    m = model(mod("a", domain="ui"), mod("b", domain="ui"), mod("c", domain="srv"))
    r = resolve(scope("domain", domain="ui"), m)
    assert r.ids == ["a", "b"]
    assert r.missing == []                     # live scopes never drift

def test_unknown_domain_is_empty_not_error():
    r = resolve(scope("domain", domain="ghost"), model(mod("a", domain="ui")))
    assert r.ids == [] and r.empty is True


# ---- query (predicate over module fields) -----------------------------------

def test_query_empty_predicate_matches_all():
    m = model(mod("a"), mod("b"))
    assert resolve(scope("query", predicate={}), m).ids == ["a", "b"]

def test_query_by_domain_plane_lifecycle():
    m = model(mod("a", domain="ui"), mod("b", domain="srv", plane="intended"),
              mod("c", domain="ui"))
    assert resolve(scope("query", predicate={"domain": "ui"}), m).ids == ["a", "c"]
    assert resolve(scope("query", predicate={"plane": "intended"}), m).ids == ["b"]

def test_query_lifecycle_rejects_mismatch():
    m = model(mod("a", lifecycle="built"), mod("b", lifecycle="planned"))
    assert resolve(scope("query", predicate={"lifecycle": "planned"}), m).ids == ["b"]

def test_query_depth_thresholds_are_and():
    m = model(mod("a", depth=0.2), mod("b", depth=0.5), mod("c", depth=0.9))
    r = resolve(scope("query", predicate={"depthGte": 0.4, "depthLte": 0.7}), m)
    assert r.ids == ["b"]

def test_query_has_leak():
    m = model(mod("a", leaksTo=["b"]), mod("b"))
    assert resolve(scope("query", predicate={"hasLeak": True}), m).ids == ["a"]

def test_query_tag_membership():
    m = model(mod("a", tags=["pii"]), mod("b", tags=["core"]))
    assert resolve(scope("query", predicate={"tag": "pii"}), m).ids == ["a"]

def test_query_has_open_candidate():
    a = mod("a"); a.suggestions = [Suggestion("s1", "t", "Strong", "in-process", "p", "s")]
    m = model(a, mod("b"))
    assert resolve(scope("query", predicate={"hasOpenCandidate": True}), m).ids == ["a"]

def test_query_unknown_key_is_ignored_tolerantly():
    m = model(mod("a", domain="ui"), mod("b", domain="srv"))
    # unknown 'galaxy' key ignored; only the domain constraint applies
    assert resolve(scope("query", predicate={"domain": "ui", "galaxy": 1}), m).ids == ["a"]


# ---- unknown kind = empty (errors as data) ----------------------------------

def test_unknown_scope_kind_resolves_empty():
    r = resolve(Scope(kind="???"), model(mod("a")))
    assert r.ids == [] and r.empty is True


# ---- determinism ------------------------------------------------------------

def test_determinism_ids_sorted_regardless_of_insertion_order():
    m1 = model(mod("z"), mod("a"), mod("m"))
    m2 = model(mod("a"), mod("m"), mod("z"))
    assert resolve(scope("system"), m1).ids == resolve(scope("system"), m2).ids == ["a", "m", "z"]


# ---- resolve_all + MembershipIndex ------------------------------------------

def doc(id, sc, type="note"):
    return Doc(id=id, type=type, title=id, scope=sc)

def test_resolve_all_batches_and_builds_inverted_index():
    m = model(mod("a", domain="ui"), mod("b", domain="ui"), mod("c", domain="srv"))
    docs = [doc("d1", scope("domain", domain="ui")),
            doc("d2", scope("explicit", ids=["c"])),
            doc("d3", scope("system"))]
    out = resolve_all(docs, m)
    assert out["byDoc"]["d1"].ids == ["a", "b"]
    assert out["byDoc"]["d2"].ids == ["c"]
    assert out["byDoc"]["d3"].ids == ["a", "b", "c"]
    idx = out["membership"]
    assert isinstance(idx, MembershipIndex)
    # transpose: docsForModule(m) contains d IFF m in byDoc[d].ids
    assert idx.docsForModule("a") == ["d1", "d3"]      # sorted
    assert idx.docsForModule("c") == ["d2", "d3"]
    assert idx.isMember("a", "d1") is True
    assert idx.isMember("a", "d2") is False

def test_resolve_all_soft_fails_one_bad_doc_without_sinking_others():
    m = model(mod("a", domain="ui"))

    class Boom:
        # a scope whose attribute access explodes during _resolve
        kind = "query"
        @property
        def predicate(self):
            raise RuntimeError("kaboom")

    good = doc("good", scope("system"))
    bad = Doc(id="bad", type="note", title="bad")
    bad.scope = Boom()
    out = resolve_all([good, bad], m)
    assert out["byDoc"]["good"].ids == ["a"]            # good doc unaffected
    assert out["byDoc"]["bad"].empty is True
    assert "invalid" in out["byDoc"]["bad"].label
