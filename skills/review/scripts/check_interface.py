#!/usr/bin/env python3
"""Review through the interface (read-only): per-module **interface-coverage** (do the
tests hit the PUBLIC surface, not just lines?) and the import-implied edges NOT recorded
on the map (a leak being born). Feeds fathom:review's seam + erosion checks.

Usage: python check_interface.py <repo_root> <model.json>   (<model.json> = archmap://{map}/model)
"""
import json, os, sys, types
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "fathom", "arch-map"))
from arch_map import measure

def load_model(path):
    data = json.load(open(path))
    mods = {m["id"]: types.SimpleNamespace(id=m["id"], plane=m.get("plane", "actual"),
            files=m.get("files", []), dependsOn=m.get("dependsOn", []),
            leaksTo=m.get("leaksTo", [])) for m in data.get("modules", [])}
    def owners_of(paths):
        ps = {measure._norm(p) for p in paths}; out = {}
        for mid, mm in mods.items():
            own = [measure._norm(f) for f in mm.files if measure._norm(f) in ps]
            if own: out[mid] = own
        return out
    return types.SimpleNamespace(modules=mods, owners_of=owners_of)

def main():
    root, model = sys.argv[1], load_model(sys.argv[2])
    ic = measure.interface_coverage(model, root)
    observed = measure.observed_edges(model, root)
    print(f"{'module':24}{'iface-cov':>10}   undeclared-edges (leaks?)")
    for mid in sorted(model.modules):
        recorded = set(model.modules[mid].dependsOn) | set(model.modules[mid].leaksTo)
        undeclared = sorted(set(observed.get(mid, [])) - recorded)
        cov = ic.get(mid)
        cov_s = f"{cov:.2f}" if cov is not None else "  -"
        print(f"{mid:24}{cov_s:>10}   {undeclared or ''}")
    print("\nLow iface-cov = tests may not assert at the interface. Undeclared edges from a")
    print("TOUCHED module = a seam crossing born in this change (route to fathom:design).")

if __name__ == "__main__":
    main()
