#!/usr/bin/env python3
"""Measure the indicators fathom:map otherwise *judges*. Reads a map exported as
JSON (the archmap://{map}/model resource, or the studio /api/model) + its repo, and
prints per-module depthProxy / cohesion / ifaceSize, the import-implied dependsOn
(seedable/verifiable), and a depth-honesty diff (judged depth vs measured proxy).
Feed the facts back via archmap_modules(action="update").

Usage: python measure.py <repo_root> <model.json>
"""
import argparse, json, os, sys, types
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "fathom", "arch-map"))
from arch_map import measure

def load_model(path):
    data = json.load(open(path))
    mods = {m["id"]: types.SimpleNamespace(id=m["id"], plane=m.get("plane", "actual"),
            files=m.get("files", []), depth=m.get("depth", 0.0)) for m in data.get("modules", [])}
    def owners_of(paths):
        ps = {measure._norm(p) for p in paths}; out = {}
        for mid, mm in mods.items():
            own = [measure._norm(f) for f in mm.files if measure._norm(f) in ps]
            if own: out[mid] = own
        return out
    return types.SimpleNamespace(modules=mods, owners_of=owners_of)

def main():
    root, model_path = sys.argv[1], sys.argv[2]
    model = load_model(model_path)
    proxies = measure.module_proxies(model, root)
    edges = measure.observed_edges(model, root)
    print(f"{'module':24}{'depth':>6}{'proxy':>7}{'delta':>7}{'cohes':>7}{'iface':>6}")
    for mid, mm in sorted(model.modules.items()):
        p = proxies.get(mid)
        if not p: continue
        d, pr = mm.depth, p["depthProxy"]; flag = "  OVERSTATED" if pr > 0 and d - pr >= 0.3 else ""
        print(f"{mid:24}{d:6.2f}{pr:7.2f}{d-pr:+7.2f}{p['cohesion']:7}{p['ifaceSize']:6}{flag}")
    print("\n# import-implied dependsOn (seed / verify against recorded):")
    for mid, deps in sorted(edges.items()):
        print(f"  {mid} -> {deps}")

if __name__ == "__main__":
    main()
