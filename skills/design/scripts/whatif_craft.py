#!/usr/bin/env python3
"""Preview a craft fix: which signals a module carries now, and which would clear if its
craft smells were fixed — so fathom:design/code knows a pass is worth it before touching
code. Structural signals that remain are the real deepening work.

Usage: python whatif_craft.py <model.json> <module_id>
"""
import json, sys, types

def main():
    data = json.load(open(sys.argv[1])); mid = sys.argv[2]
    m = next((x for x in data.get("modules", []) if x["id"] == mid), None)
    if not m:
        print(f"no module '{mid}' in model"); return
    try:
        import os
        sys.path.insert(0, os.path.join(os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")), "fathom", "arch-map"))
        from arch_map.signals import SIGNAL_REGISTRY
    except Exception as e:
        print("needs the arch_map package on the path (run inside the plugin):", e); return
    mx = {"churn": 0, "blastRadius": 0, "inCycle": False, "fanOut": 0, "fanIn": 0,
          "instability": 0, "coupling": 0, "health": 100}
    mx.update(m.get("metrics", {}))
    base = dict(coverage=m.get("coverage", 0), depth=m.get("depth", 0.5), size=m.get("size", 1.0),
                leaksTo=m.get("leaksTo", []), craft=m.get("craft", {}), depthProxy=m.get("depthProxy", 0))
    def fires(d):
        ns = types.SimpleNamespace(**d)
        out = []
        for sid, fam, fn, why, how in SIGNAL_REGISTRY:
            try:
                if fn(ns, mx): out.append(sid)
            except Exception:
                pass
        return out
    cur = fires(base)
    fixed = dict(base); fixed["craft"] = {k: 0 for k in base["craft"]}
    cleared = [s for s in cur if s not in fires(fixed)]
    remaining = [s for s in cur if s not in cleared]
    print(f"module {mid}")
    print(f"  carries now            : {cur or '(clean)'}")
    print(f"  a craft pass clears    : {cleared or '(none)'}")
    print(f"  structural (-> design) : {remaining or '(none)'}")

if __name__ == "__main__":
    main()
