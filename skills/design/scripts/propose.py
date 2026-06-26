#!/usr/bin/env python3
"""Rank deepening candidates worst-first from a map's signals + metrics, with a
pre-inferred dependency category — so fathom:design grills a *measured* list instead
of finding friction by hand. Reads the archmap://{map}/model resource (it embeds
per-module metrics + craft).

Usage: python propose.py <model.json>
"""
import json, sys

def main():
    data = json.load(open(sys.argv[1])); rows = []
    for m in data.get("modules", []):
        mx = m.get("metrics", {}); depth = m.get("depth", 0.5); size = m.get("size", 1.0)
        cr = m.get("craft", {}); reasons = []
        if mx.get("fanIn", 0) >= 8 and mx.get("fanOut", 0) >= 6: reasons.append("god-module")
        if size >= 2.0 and depth < 0.5: reasons.append("bulky-impl")
        if mx.get("fanIn", 0) >= 8 and depth < 0.4: reasons.append("bottleneck")
        if mx.get("fanOut", 0) >= 6 and depth < 0.5: reasons.append("needs-refactor")
        if cr.get("maxFnLen", 0) >= 50: reasons.append("long-function")
        if size >= 2.0 and cr.get("methodCount", 0) >= 12: reasons.append("large-class")
        dp = m.get("depthProxy", 0)
        if dp and depth - dp >= 0.3: reasons.append("depth-overstated")
        if reasons:
            score = (1 - depth) * 2 + size + 0.1 * mx.get("blastRadius", 0)
            cat = "in-process" if not m.get("dependsOn") else "review-deps (classify per DEEPENING.md)"
            rows.append((round(score, 2), m["id"], depth, size, reasons, cat))
    rows.sort(reverse=True)
    print(f"# {len(rows)} deepening candidates (worst first)\n")
    for score, mid, depth, size, reasons, cat in rows:
        print(f"- {mid}  depth={depth} size={size} score={score}  [{', '.join(reasons)}]  category~{cat}")
    print("\nGrill the top candidate with fathom:design IMPROVE mode.")

if __name__ == "__main__":
    main()
