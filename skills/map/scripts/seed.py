#!/usr/bin/env python3
"""Fast map seed — cluster a repo's source into candidate modules with measured,
import-implied dependsOn, so fathom:map *curates a skeleton* instead of authoring
one by hand. Review the output, then commit keepers via
archmap_modules(action="add", items=[...]).

Usage: python seed.py <repo_root> [--json]
"""
import argparse, json, os, sys, types
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "fathom", "arch-map"))
from arch_map import measure

_SKIP = (".git", "node_modules", ".venv", "__pycache__", ".fathom-worktrees", ".pytest_cache")

def all_source(root):
    out = []
    for dp, dns, fs in os.walk(root):
        dns[:] = [d for d in dns if d not in _SKIP]
        for f in fs:
            if os.path.splitext(f)[1].lower() in measure._SRC_SUF:
                out.append(os.path.relpath(os.path.join(dp, f), root).replace("\\", "/"))
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("root"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    files = all_source(a.root)
    mods = measure.seed_modules(a.root, files)
    if a.json:
        print(json.dumps(mods, indent=2)); return
    print(f"# {len(mods)} candidate modules from {len(files)} source files\n")
    for m in mods:
        print(f"- {m['id']}  ({m['domain']}, {len(m['files'])} files)  dependsOn={m['dependsOn']}")
    print("\nReview, then commit keepers: archmap_modules(action='add', items=[...])")

if __name__ == "__main__":
    main()
