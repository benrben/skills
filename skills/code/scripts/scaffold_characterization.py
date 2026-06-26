#!/usr/bin/env python3
"""Scaffold characterization tests at a module's interface — list its PUBLIC symbols and
emit a test skeleton asserting each, so fathom:code has a safety net BEFORE a refactor
(mode a). Prints to stdout; review, fill the expected values, run green, then refactor.

Usage: python scaffold_characterization.py <repo_root> <file> [<file> ...]
"""
import json, os, sys, types
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "fathom", "arch-map"))
from arch_map import measure

def main():
    root, files = sys.argv[1], sys.argv[2:]
    syms = []
    for f in files:
        try:
            t = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        syms += sorted(measure._public_symbols(t, f))
    print("# Characterization tests — pin CURRENT observable behaviour at the interface.")
    print("# Fill expected values, run green, THEN refactor under them (the interface is the test surface).\n")
    for s in sorted(set(syms)):
        print(f"def test_{s}_characterization():\n"
              f"    # TODO: exercise {s}(...) and assert its CURRENT output\n"
              f"    raise NotImplementedError\n")
    if not syms:
        print("# (no public symbols found — is the seam where you think it is?)")

if __name__ == "__main__":
    main()
