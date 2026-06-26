#!/usr/bin/env python3
"""Accuracy eval — grade the measurement/signal engine against a fixture with KNOWN
ground truth (planted depth, smells, edges, category, interface-coverage). Deterministic.

  python evals/run_eval.py            # human report, exits non-zero on any miss
  from evals.run_eval import evaluate # -> results dict (used by tests/test_eval_accuracy.py)
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from arch_map.model import ArchModel, Module
from arch_map import measure, craft_ingest
from arch_map.server import _compute_signals, _CRAFT_SIGNALS

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixture")
_RELEVANT = _CRAFT_SIGNALS | {"depth-overstated"}   # the layer this eval grades

# planted ground truth: module -> exactly these craft/honesty signals
EXPECT_SIGNALS = {
    "long_function.py": {"long-function"},
    "many_params.py": {"too-many-args"},
    "deep_nest.py": {"deep-nesting"},
    "dead_comments.py": {"comment-smell"},
    "magic_values.py": {"magic-number"},
    "overstated.py": {"depth-overstated"},
    "untested.py": {"untested-interface"},
}

def _build():
    files = sorted(f for f in os.listdir(FIX) if f.endswith(".py"))
    mods = [Module(id=f, label=f, domain="fix", depth=0.5, size=1.0, seam="", files=[f]) for f in files]
    model = ArchModel(repo="eval", modules=mods)
    for mid, deps in measure.observed_edges(model, FIX).items():
        model.modules[mid].dependsOn = [d for d in deps if d in model.modules]
    for mid, fa in craft_ingest.module_craft(model, FIX).items():
        model.modules[mid].craft = fa
    proxies = measure.module_proxies(model, FIX)
    for mid, pr in proxies.items():
        m = model.modules[mid]
        m.depthProxy = pr["depthProxy"]; m.cohesion = pr["cohesion"]; m.ifaceSize = pr["ifaceSize"]
        m.depth = pr["depthProxy"]    # judged == measured -> no spurious honesty/coverage hits
        m.coverage = 1.0              # assume covered; isolate untested-interface below
    model.modules["overstated.py"].depth = 0.9   # planted: judged >> measured proxy
    model.modules["untested.py"].coverage = 0.0   # planted: deep interface, no tests
    return model

def evaluate() -> dict:
    model = _build()
    mx = model.compute_metrics()
    checks = []
    def chk(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    # 1) per-module craft/honesty signals match exactly
    for mid, m in model.modules.items():
        fired = {s for s in _compute_signals(m, mx[mid]) if s in _RELEVANT}
        exp = EXPECT_SIGNALS.get(mid, set())
        chk(f"signals[{mid}]", fired == exp, f"fired={sorted(fired)} expected={sorted(exp)}")
    # 2) depthProxy: deep > shallow
    dp = model.modules
    chk("depthProxy deep>shallow",
        dp["deep_service.py"].depthProxy > dp["shallow_wrappers.py"].depthProxy,
        f"{dp['deep_service.py'].depthProxy} vs {dp['shallow_wrappers.py'].depthProxy}")
    # 3) edge seeded consumer->provider
    chk("edge consumer->provider", "provider.py" in dp["consumer.py"].dependsOn,
        str(dp["consumer.py"].dependsOn))
    # 4) category inference
    chk("category net_client = ports&adapters", "ports" in measure.infer_category(FIX, ["net_client.py"]))
    chk("category provider = in-process", measure.infer_category(FIX, ["provider.py"]) == "in-process")
    # 5) interface-coverage of the tested module
    ic = measure.interface_coverage(model, FIX)
    chk("iface-coverage tested_mod = 1.0", ic.get("tested_mod.py") == 1.0, str(ic.get("tested_mod.py")))

    passed = sum(c["pass"] for c in checks); total = len(checks)
    return {"passed": passed, "total": total, "score": round(passed / total, 3), "checks": checks}

if __name__ == "__main__":
    r = evaluate()
    print(f"\nFathom accuracy eval — {r['passed']}/{r['total']} ({r['score']*100:.0f}%)\n")
    for c in r["checks"]:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['check']:32} {c['detail'] if not c['pass'] else ''}")
    sys.exit(0 if r["passed"] == r["total"] else 1)
