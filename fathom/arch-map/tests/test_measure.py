"""Interface tests for measure.py — the deterministic indicator engine."""
import types

from arch_map import measure


def _model(modfiles):
    mods = {mid: types.SimpleNamespace(plane="actual", files=fs, id=mid)
            for mid, fs in modfiles.items()}

    def owners_of(paths):
        ps = {measure._norm(p) for p in paths}
        out = {}
        for mid, fs in modfiles.items():
            own = [measure._norm(f) for f in fs if measure._norm(f) in ps]
            if own:
                out[mid] = own
        return out
    return types.SimpleNamespace(modules=mods, owners_of=owners_of)


def test_interface_surface_python():
    src = "def pub():\n    pass\ndef _priv():\n    pass\nclass Pub:\n    pass\nclass _H:\n    pass\n"
    assert measure.interface_surface(src, "m.py") == 2


def test_interface_surface_js():
    src = "export function a(){}\nexport const b=1\nexport { c, d }\nfunction hid(){}\n"
    assert measure.interface_surface(src, "m.js") >= 4


def test_depth_proxy_orders_deep_above_shallow(tmp_path):
    (tmp_path / "deep.py").write_text("def go():\n" + "\n".join("    x = i%d" % i for i in range(60)) + "\n")
    (tmp_path / "shallow.py").write_text("\n".join("def f%d():\n    return f%d\n" % (i, i) for i in range(10)))
    p = measure.module_proxies(_model({"deep": ["deep.py"], "shallow": ["shallow.py"]}), str(tmp_path))
    assert p["deep"]["depthProxy"] > p["shallow"]["depthProxy"]
    assert p["deep"]["ifaceSize"] == 1 and p["shallow"]["ifaceSize"] == 10


def test_observed_edges_from_imports(tmp_path):
    (tmp_path / "a.py").write_text("import b\n")
    (tmp_path / "b.py").write_text("x = 1\n")
    oe = measure.observed_edges(_model({"A": ["a.py"], "B": ["b.py"]}), str(tmp_path))
    assert oe.get("A") == ["B"]


def test_seed_modules_clusters_by_dir(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "pkg" / "b.py").write_text("y = 1\n")
    seeded = measure.seed_modules(str(tmp_path), ["pkg/a.py", "pkg/b.py"])
    assert len(seeded) == 1 and seeded[0]["id"] == "pkg" and len(seeded[0]["files"]) == 2


def test_craft_denoise_ignores_braces_in_strings():
    from arch_map.craft_ingest import scan_text
    src = 'function f() {\n  var s = "{{{{{";\n  log(s);\n}\n'
    assert scan_text(src, "x.js")["maxNesting"] <= 1


def test_infer_category(tmp_path):
    (tmp_path / "pure.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "net.py").write_text("import requests\n")
    (tmp_path / "ext.py").write_text("import stripe\n")
    assert measure.infer_category(str(tmp_path), ["pure.py"]) == "in-process"
    assert "ports" in measure.infer_category(str(tmp_path), ["net.py"])
    assert "mock" in measure.infer_category(str(tmp_path), ["ext.py"])


def test_interface_coverage(tmp_path):
    (tmp_path / "mod.py").write_text("def public_api():\n    return 1\ndef _hidden():\n    return 2\n")
    (tmp_path / "test_mod.py").write_text("from mod import public_api\n\ndef test_it():\n    assert public_api() == 1\n")
    m = _model({"mod": ["mod.py"], "t": ["test_mod.py"]})
    ic = measure.interface_coverage(m, str(tmp_path))
    assert ic["mod"] == 1.0   # the one public symbol is referenced by the test


def test_cluster_by_imports(tmp_path):
    (tmp_path / "a.py").write_text("import b\n")
    (tmp_path / "b.py").write_text("x = 1\n")
    (tmp_path / "lone.py").write_text("y = 1\n")
    clusters = measure.cluster_by_imports(str(tmp_path), ["a.py", "b.py", "lone.py"])
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [1, 2]   # {a,b} connected, {lone} alone
