"""Interface tests for the **Graph Metrics** module (ArchModel.compute_metrics).

Pure derived analytics over the edge set — fan-in/out, instability, transitive
blast radius (BFS over reverse adjacency), cross-domain coupling, cycle
membership, and the composite health score. In-process and deterministic, so we
assert exact values on small hand-built graphs.
"""
from arch_map.model import ArchModel, Module


def mod(id, *, domain="d", depth=0.5, size=1.0, seam="", coverage=0.0,
        churn=0.0, leaksTo=None, dependsOn=None):
    return Module(id=id, label=id, domain=domain, depth=depth, size=size,
                  seam=seam, coverage=coverage, churn=churn,
                  leaksTo=leaksTo or [], dependsOn=dependsOn or [])


def chain():
    # c -> b -> a   (x -> y means "x dependsOn y")
    return ArchModel("repo", [
        mod("a", domain="model"),
        mod("b", domain="model", dependsOn=["a"]),
        mod("c", domain="server", dependsOn=["b"]),
    ]).compute_metrics()


def test_fan_in_and_fan_out():
    mx = chain()
    assert mx["a"]["fanIn"] == 1 and mx["a"]["fanOut"] == 0
    assert mx["b"]["fanIn"] == 1 and mx["b"]["fanOut"] == 1
    assert mx["c"]["fanIn"] == 0 and mx["c"]["fanOut"] == 1


def test_instability_formula_and_isolated_default():
    mx = chain()
    assert mx["a"]["instability"] == 0.0      # 0/(1+0)
    assert mx["b"]["instability"] == 0.5      # 1/(1+1)
    assert mx["c"]["instability"] == 1.0      # 1/(0+1)
    lone = ArchModel("r", [mod("solo")]).compute_metrics()
    assert lone["solo"]["instability"] == 0.5  # total==0 -> 0.5 sentinel


def test_blast_radius_is_transitive():
    mx = chain()
    assert mx["a"]["blastRadius"] == 2        # b and c transitively depend on a
    assert mx["b"]["blastRadius"] == 1        # only c
    assert mx["c"]["blastRadius"] == 0


def test_cross_domain_coupling():
    mx = chain()
    assert mx["a"]["coupling"] == 0           # depends on nothing
    assert mx["b"]["coupling"] == 0           # b(model) -> a(model), same domain
    assert mx["c"]["coupling"] == 1           # c(server) -> b(model), cross-domain


def test_cycle_membership():
    cyc = ArchModel("r", [
        mod("a", dependsOn=["b"]),
        mod("b", dependsOn=["a"]),
        mod("c"),
    ]).compute_metrics()
    assert cyc["a"]["inCycle"] is True
    assert cyc["b"]["inCycle"] is True
    assert cyc["c"]["inCycle"] is False


def test_mutual_cycle_with_later_dependent_does_not_crash():
    # regression: the DFS early-returned on a back edge without popping,
    # leaving "b" GRAY on a corrupted stack; visiting c -> b then raised
    # ValueError("'b' is not in list") from stack.index(b)
    mx = ArchModel("r", [
        mod("a", dependsOn=["b"]),
        mod("b", dependsOn=["a"]),
        mod("c", dependsOn=["b"]),
    ]).compute_metrics()
    assert mx["a"]["inCycle"] is True
    assert mx["b"]["inCycle"] is True
    assert mx["c"]["inCycle"] is False


def test_node_on_two_cycles_marks_both():
    # the early return also stopped scanning a node's remaining deps after
    # the first back edge, so a second cycle through the same node was missed
    mx = ArchModel("r", [
        mod("d", dependsOn=["e", "f"]),
        mod("e", dependsOn=["d"]),
        mod("f", dependsOn=["d"]),
    ]).compute_metrics()
    assert mx["d"]["inCycle"] is True
    assert mx["e"]["inCycle"] is True
    assert mx["f"]["inCycle"] is True


def test_health_formula_and_bounds():
    mx = ArchModel("r", [
        mod("full", depth=1.0, coverage=1.0),                 # 40 + 40
        mod("mid", depth=0.5, coverage=0.5, churn=1.0),       # 20 + 20 - 10
        mod("bad", depth=0.0, coverage=0.0, leaksTo=["full"]),# -10 -> clamped 0
    ]).compute_metrics()
    assert mx["full"]["health"] == 80
    assert mx["mid"]["health"] == 30
    assert mx["bad"]["health"] == 0           # clamped at the 0 floor


def test_churn_is_passed_through():
    mx = ArchModel("r", [mod("a", churn=0.42)]).compute_metrics()
    assert mx["a"]["churn"] == 0.42
