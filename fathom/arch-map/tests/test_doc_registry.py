"""Interface tests for the **Doc Registry** module (model.py).

The interface is the test surface: these assert observable behaviour of the
top-level Doc store — Doc/Scope.from_dict construction (required fields, type
validation, managed-key dropping, nested-Scope reification), the doc CRUD
methods + the _DOC_EDITABLE whitelist, the new Module.tags field, and that docs
round-trip through to_dict / to_view / from_json (including back-compat on a
pre-docs map). Doc CRUD is pure in-process, so we test through the interface
directly — no adapters.
"""
import json

import pytest

from arch_map.model import ArchModel, Doc, Module, Scope, Suggestion


def mod(id, *, domain="d", depth=0.5, size=1.0, seam="", coverage=0.0, **kw):
    return Module(id=id, label=kw.pop("label", id), domain=domain, depth=depth,
                  size=size, seam=seam, coverage=coverage, **kw)


def doc(id="d1", *, type="note", title="T", **kw):
    return Doc(id=id, type=type, title=title, **kw)


def model(*modules, docs=None):
    return ArchModel("repo", list(modules), docs=list(docs or []))


# ---- Scope.from_dict --------------------------------------------------------

def test_scope_from_dict_defaults_to_system():
    assert Scope.from_dict(None).kind == "system"
    assert Scope.from_dict({}).kind == "system"

def test_scope_from_dict_each_kind():
    assert Scope.from_dict({"kind": "explicit", "ids": ["a", "b"]}).ids == ["a", "b"]
    assert Scope.from_dict({"kind": "domain", "domain": "ui"}).domain == "ui"
    assert Scope.from_dict({"kind": "query", "predicate": {"domain": "ui"}}).predicate == {"domain": "ui"}

def test_scope_from_dict_rejects_unknown_kind():
    with pytest.raises(ValueError):
        Scope.from_dict({"kind": "galaxy"})


# ---- Doc.from_dict ----------------------------------------------------------

def test_doc_from_dict_requires_core_fields():
    for bad in ({"type": "note", "title": "T"},          # no id
                {"id": "d", "title": "T"},               # no type
                {"id": "d", "type": "note"}):            # no title
        with pytest.raises(ValueError):
            Doc.from_dict(bad)

def test_doc_from_dict_validates_type():
    with pytest.raises(ValueError):
        Doc.from_dict({"id": "d", "type": "memo", "title": "T"})
    # all eleven cycle types: the original five plus the v2 additions
    for t in ("adr", "note", "rule", "rfc", "glossary",
              "spec", "ceiling", "risk", "runbook", "postmortem", "diagram"):
        assert Doc.from_dict({"id": "d", "type": t, "title": "T"}).type == t

def test_doc_from_dict_reifies_scope_and_drops_computed_keys():
    d = Doc.from_dict({
        "id": "d", "type": "rule", "title": "T",
        "scope": {"kind": "domain", "domain": "ui"},
        "resolvedModuleIds": ["x"], "drift": ["y"], "scopeLabel": "stale",
    })
    assert isinstance(d.scope, Scope) and d.scope.domain == "ui"
    # computed keys never become attributes
    assert not hasattr(d, "resolvedModuleIds")

def test_doc_from_dict_default_scope_is_system():
    assert Doc.from_dict({"id": "d", "type": "note", "title": "T"}).scope.kind == "system"


# ---- add / get / duplicate --------------------------------------------------

def test_add_then_get_doc_bakes_resolved_scope():
    m = model(mod("a", domain="ui"), mod("b", domain="srv"), docs=[
        doc("d1", scope=Scope(kind="domain", domain="ui"))])
    got = m.get_doc("d1")
    assert got["id"] == "d1"
    assert got["resolvedModuleIds"] == ["a"]      # baked, only ui modules
    assert got["drift"] == []
    assert "Domain: ui" in got["scopeLabel"]

def test_add_duplicate_doc_raises():
    m = model(docs=[doc("d1")])
    with pytest.raises(KeyError):
        m.add_doc(doc("d1"))

def test_get_unknown_doc_raises():
    with pytest.raises(KeyError):
        model().get_doc("nope")

def test_get_docs_bulk():
    m = model(docs=[doc("d1"), doc("d2", type="adr")])
    out = m.get_docs(["d1", "d2"])
    assert [r["id"] for r in out] == ["d1", "d2"]


# ---- update + whitelist -----------------------------------------------------

def test_update_doc_changes_editable_fields():
    m = model(docs=[doc("d1", status="draft")])
    m.update_doc("d1", status="current", title="New")
    assert m.docs["d1"].status == "current"
    assert m.docs["d1"].title == "New"

def test_update_doc_rejects_non_editable_field():
    m = model(docs=[doc("d1")])
    with pytest.raises(ValueError):
        m.update_doc("d1", id="d2")               # id is not editable

def test_update_doc_rejects_bad_type():
    m = model(docs=[doc("d1")])
    with pytest.raises(ValueError):
        m.update_doc("d1", type="memo")

def test_update_doc_reifies_scope_dict():
    m = model(mod("a", domain="ui"), docs=[doc("d1")])
    m.update_doc("d1", scope={"kind": "domain", "domain": "ui"})
    assert isinstance(m.docs["d1"].scope, Scope)
    assert m.get_doc("d1")["resolvedModuleIds"] == ["a"]

def test_update_unknown_doc_raises():
    with pytest.raises(KeyError):
        model().update_doc("ghost", status="x")


# ---- delete -----------------------------------------------------------------

def test_delete_doc_removes_it():
    m = model(docs=[doc("d1")])
    m.delete_doc("d1")
    assert "d1" not in m.docs

def test_delete_unknown_doc_raises():
    with pytest.raises(KeyError):
        model().delete_doc("nope")


# ---- Module.tags ------------------------------------------------------------

def test_module_tags_default_empty_and_roundtrip():
    m = model()
    m.add_module(mod("a"))
    assert m.modules["a"].tags == []
    m.update_module("a", tags=["pii", "core"])
    assert m.modules["a"].tags == ["pii", "core"]
    assert m.get_module("a")["tags"] == ["pii", "core"]

def test_module_from_dict_accepts_tags():
    rec = Module.from_dict({"id": "a", "label": "A", "domain": "d", "tags": ["x"]})
    assert rec.tags == ["x"]


# ---- serialization: to_dict / to_view --------------------------------------

def test_to_dict_serializes_docs_with_membership():
    m = model(mod("a", domain="ui"), mod("b", domain="ui"), mod("c", domain="srv"), docs=[
        doc("d1", type="rule", scope=Scope(kind="domain", domain="ui"))])
    out = m.to_dict()
    assert [d["id"] for d in out["docs"]] == ["d1"]
    d1 = out["docs"][0]
    assert d1["resolvedModuleIds"] == ["a", "b"]
    assert d1["scope"]["kind"] == "domain"          # nested Scope serialized to a dict
    # inverted membership: both ui modules point back at d1
    assert out["docMembership"]["a"] == ["d1"]
    assert out["docMembership"]["b"] == ["d1"]
    assert "c" not in out["docMembership"]

def test_to_view_lists_docs_lightweight():
    m = model(docs=[doc("d1", type="adr", status="accepted",
                        scope=Scope(kind="system"))])
    v = m.to_view()
    assert v["docs"] == [{"id": "d1", "type": "adr", "title": "T",
                          "status": "accepted", "scopeKind": "system"}]

def test_to_dict_absent_docs_is_empty_list():
    assert model().to_dict()["docs"] == []


# ---- from_json round-trip + back-compat ------------------------------------

def test_from_json_roundtrips_docs(tmp_path):
    m = model(mod("a", domain="ui"), docs=[
        doc("d1", type="rule", title="No db in ui", tags=["arch"],
            scope=Scope(kind="domain", domain="ui"), supersedes=["d0"])])
    p = tmp_path / "m.json"
    m.save(p)
    again = ArchModel.from_json(p)
    assert again.docs["d1"].type == "rule"
    assert again.docs["d1"].scope.kind == "domain"
    assert again.docs["d1"].scope.domain == "ui"
    assert again.docs["d1"].tags == ["arch"]
    assert again.docs["d1"].supersedes == ["d0"]
    # computed keys did not leak back in as attributes
    assert again.get_doc("d1")["resolvedModuleIds"] == ["a"]

def test_from_json_backcompat_no_docs_key(tmp_path):
    # a pre-docs map file has no "docs" key at all (modules written as to_dict does)
    p = tmp_path / "old.json"
    p.write_text(json.dumps({"repo": "R", "modules": [
        {"id": "a", "label": "A", "domain": "d", "depth": 0.5, "size": 1.0, "seam": ""}]}))
    again = ArchModel.from_json(p)
    assert again.docs == {}
    assert again.modules["a"].tags == []            # tags defaults on old modules too
