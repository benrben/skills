"""whatif-preview — metrics of a hypothetical module merge, without mutation.

Pure query beside graph-metrics: ids in, the merged module's computed metrics
out. The simulation rewrites a COPY of the edge graph (members collapse into one
node, edges between members are absorbed, outside edges re-point) and runs the
real compute_metrics over it — no duplicated math, and the model is never
mutated. The studio's "what if we merged these?" card renders this verbatim.

Interface (the test surface):
  preview_merge(model, ids) -> {
      "ids":           the distinct ids previewed,
      "merged":        {fanIn, fanOut, instability, blastRadius, health,
                        depth, coverage}   # depth/coverage size-weighted means
      "before":        {id: current metrics} for each member,
      "absorbedEdges": ["a->b", ...]  edges between members that vanish,
      "externalEdges": {"in": [ids depending on the merge],
                        "out": [ids the merge depends on]}}
  ValueError on fewer than 2 distinct ids or any unknown id.

  Note: the merged depth/coverage are size-weighted; if a member is an intended
  (not-yet-built) module its size is an estimate, so the weights mix measured and
  estimated mass.
"""
from __future__ import annotations

from .model import ArchModel, Module


def preview_merge(model, ids: list[str]) -> dict:
    want = list(dict.fromkeys(ids or []))
    if len(want) < 2:
        raise ValueError("preview_merge needs at least 2 distinct module ids")
    missing = [i for i in want if i not in model.modules]
    if missing:
        raise ValueError(f"unknown module id(s): {missing}")

    metrics = model.compute_metrics()
    before = {mid: dict(metrics[mid]) for mid in want}
    member_set = set(want)
    members = [model.modules[i] for i in want]
    merged_id = "+".join(want)

    total_size = sum(m.size for m in members) or 1.0
    depth = sum(m.depth * m.size for m in members) / total_size
    coverage = sum(m.coverage * m.size for m in members) / total_size
    churn = max(m.churn for m in members)
    merged_deps = sorted({d for m in members for d in m.dependsOn
                          if d not in member_set})
    merged_leaks = sorted({d for m in members for d in m.leaksTo
                           if d not in member_set})
    absorbed = sorted({f"{m.id}->{d}" for m in members
                       for d in (m.dependsOn + m.leaksTo) if d in member_set})

    sims = [Module(id=merged_id, label="(merged)", domain=members[0].domain,
                   depth=depth, size=total_size, seam="", coverage=coverage,
                   churn=churn, dependsOn=merged_deps, leaksTo=merged_leaks)]
    for m in model.modules.values():
        if m.id in member_set:
            continue
        repoint = lambda edges: list(dict.fromkeys(
            merged_id if d in member_set else d for d in edges))
        sims.append(Module(id=m.id, label=m.label, domain=m.domain, depth=m.depth,
                           size=m.size, seam="", coverage=m.coverage, churn=m.churn,
                           dependsOn=repoint(m.dependsOn), leaksTo=repoint(m.leaksTo)))
    sim_metrics = ArchModel(model.repo, sims).compute_metrics()[merged_id]

    return {
        "ids": want,
        "merged": {"fanIn": sim_metrics["fanIn"], "fanOut": sim_metrics["fanOut"],
                   "instability": sim_metrics["instability"],
                   "blastRadius": sim_metrics["blastRadius"],
                   "health": sim_metrics["health"],
                   "depth": round(depth, 3), "coverage": round(coverage, 3)},
        "before": before,
        "absorbedEdges": absorbed,
        "externalEdges": {
            "in": sorted({m.id for m in model.modules.values()
                          if m.id not in member_set
                          and any(d in member_set for d in m.dependsOn)}),
            "out": merged_deps},
    }
