"""Interface tests for craft_ingest — the line-level craft fact reader, and the
craft signal family it feeds."""
import types

import pytest

from arch_map.craft_ingest import module_craft, scan_text
from arch_map.model import Module

_JAVA = """class Foo {
  int small(int a) { return a; }
  void big(int a, int b, int c, int d) {
    if (a) {
      for (int i=0; i<n; i++) {
        while (b) {
          if (c) { doThing(); }
        }
      }
    }
    // x = doStuff();
    int t = 42 + 7 + 9;
  }
}"""


def test_brace_facts():
    f = scan_text(_JAVA, "Foo.java")
    assert f["methodCount"] == 2
    assert f["maxArgs"] == 4
    assert f["maxNesting"] >= 4
    assert f["magicNumbers"] >= 3
    assert f["commentedOutBlocks"] >= 1


def test_long_function():
    src = "function huge(a) {\n" + "\n".join("  s();" for _ in range(60)) + "\n}\n"
    assert scan_text(src, "x.js")["maxFnLen"] >= 50


def test_python_excludes_self():
    src = ("class C:\n    def big(self, a, b, c, d):\n        if a:\n"
           "            for x in a:\n                while b:\n                    do()\n")
    f = scan_text(src, "c.py")
    assert f["maxArgs"] == 4
    assert f["maxNesting"] >= 4
    assert f["methodCount"] == 1


def test_unreadable_degrades_to_zero():
    f = scan_text("\x00 not really code", "weird.bin")
    assert f["maxFnLen"] == 0 and f["methodCount"] == 0


def test_module_craft_aggregates(tmp_path):
    (tmp_path / "a.java").write_text(_JAVA)
    mod = Module(id="m1", label="M1", domain="d", depth=0.5, size=1.0, seam="", files=["a.java"])
    model = types.SimpleNamespace(modules={"m1": mod})
    out = module_craft(model, str(tmp_path))
    assert out["m1"]["methodCount"] == 2
    assert out["m1"]["maxArgs"] == 4


def test_intended_modules_skipped(tmp_path):
    (tmp_path / "a.java").write_text(_JAVA)
    mod = Module(id="m1", label="M1", domain="d", depth=0.5, size=1.0, seam="",
                 files=["a.java"], plane="intended")
    model = types.SimpleNamespace(modules={"m1": mod})
    assert module_craft(model, str(tmp_path)) == {}


def test_craft_signals_fire():
    pytest.importorskip("fastmcp")
    from arch_map.server import _compute_signals
    m = Module(id="m", label="m", domain="d", depth=0.7, size=3.0, seam="",
               coverage=0.2,
               craft={"maxFnLen": 80, "maxArgs": 5, "maxNesting": 5,
                      "methodCount": 15, "magicNumbers": 4, "commentedOutBlocks": 2})
    mx = {"churn": 0.0, "blastRadius": 0, "inCycle": False, "fanOut": 0, "fanIn": 0,
          "instability": 0.0, "coupling": 0, "health": 1.0}
    sigs = _compute_signals(m, mx)
    for s in ("long-function", "too-many-args", "deep-nesting", "large-class",
              "untested-interface", "magic-number", "comment-smell"):
        assert s in sigs, (s, sigs)


def test_scan_cache_returns_equal_and_isolated():
    from arch_map import craft_ingest
    src = "function f(a,b,c,d){ if(x){ if(y){ if(z){} } } }\n"
    a = craft_ingest.scan_text(src, "x.js")
    b = craft_ingest.scan_text(src, "x.js")   # cache hit
    assert a == b
    a["maxArgs"] = 999                          # mutating the result must not poison the cache
    assert craft_ingest.scan_text(src, "x.js")["maxArgs"] == 4


def test_common_literals_not_magic():
    from arch_map.craft_ingest import scan_text
    src = 'function f(){ status = 404; size = 1024; timeout = 3600; }\n'
    assert scan_text(src, "x.js")["magicNumbers"] == 0
