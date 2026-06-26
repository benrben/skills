"""Accuracy gate — the measurement/signal engine must score 100% on the ground-truth
fixture (planted depth, smells, edges, category, interface-coverage). Guards against
silent regressions in measure.py / craft_ingest.py / the signal registry."""
import pytest


def test_engine_scores_100pct_on_ground_truth():
    pytest.importorskip("fastmcp")
    from evals.run_eval import evaluate
    r = evaluate()
    failed = [f"{c['check']} ({c['detail']})" for c in r["checks"] if not c["pass"]]
    assert not failed, "accuracy regressions:\n  " + "\n  ".join(failed)
    assert r["score"] == 1.0 and r["passed"] == r["total"]
