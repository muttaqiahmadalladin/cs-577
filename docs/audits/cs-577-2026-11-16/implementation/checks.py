"""Read-only, offline checks of committed cs-577 graph scores; no hosted-model calls.

Run from the audited repository root:
     python3 docs/audits/cs-577-2026-11-16/implementation/checks.py .
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
from grounded_extension import ASPECTS, decide, strengths_jev

gold = {d["id"]: d["professor"] for d in map(json.loads, open(ROOT / "data/icsi_rebuilt_snippets.jsonl"))}


def optimum(j, side, mode="all", triple=False, fix=False):
    """Exact conditional objective, up to the same relation constant for A and B.

    Speaker XOR forces opposing reasons OFF. Cross-side similarity constraints
    are redundant. Each aspect's three remaining reasons permits 8 masks; the
    only cross-aspect constraint requires at least one selected reason overall.
    """
    base = 0.0
    opts = []
    for a in ASPECTS:
        r = {s: [20 * round(j[f"{a}|rv|{s}{k}"] * j[f"{a}|rg|{s}{k}"], 2) for k in range(3)] for s in "AB"}
        b = {s: [18 * round(j[f"{a}|ba|{s}{k}"] * j[f"{a}|bg|{s}{k}"] * (j[f"{a}|bv|{s}{k}"] if triple else 1), 2) if mode != "reasons" else 0 for k in range(3)] for s in "AB"}
        base += sum(b["A"]) + sum(b["B"])
        rel = [j[f"{a}|c{side}|{pair}"] for pair in ("01", "02", "12")]
        pairs = [(0, 1), (0, 2), (1, 2)]
        # Literal pairs in the pinned upstream rule file: its first aspect has
        # a repeated A2/A3 pair in the third contradiction factor.
        if a == "style" and side == "A" and not fix:
            pairs = [(0, 1), (1, 2), (1, 2)]
        opts.append([sum(r[side][k] - b[side][k] for k in range(3) if mask >> k & 1)
                     - (sum(v for v, (k, l) in zip(rel, pairs) if mask >> k & 1 and mask >> l & 1) if mode == "all" else 0)
                     for mask in range(8)])
    value = base + sum(max(x) for x in opts)
    if not any(any(x[m] == max(x) for m in range(1, 8)) for x in opts):
        value += max(max(x[1:]) - max(x) for x in opts)
    return round(value, 9)


out = {}
for folder in ("wu_graph_terra", "wu_graph_claude", "glm_run"):
    rows = list(map(json.loads, open(ROOT / "results" / folder / "jev_scores.jsonl")))
    scores = {r["id"]: r["answers"] for r in rows}
    assert set(scores) == set(gold) and len(rows) == 150
    summary = {"rows": len(rows), "models": dict(Counter(r.get("model") for r in rows))}
    for mode in ("reasons", "rr", "all"):
        obj = {i: {s: optimum(j, s, mode) for s in "AB"} for i, j in scores.items()}
        ties = [i for i, z in obj.items() if z["A"] == z["B"]]
        pred = {i: "A" if z["A"] >= z["B"] else "B" for i, z in obj.items()}
        correct = sum(pred[i] == gold[i] for i in pred)
        summary[mode] = {"correct_ties_A": correct, "speaker_objective_ties": ties,
                         "correct_range": [correct - sum(gold[i] == "A" for i in ties), correct + sum(gold[i] == "B" for i in ties)]}
        if mode == "all":
            for name, kw in (("triple_product", {"triple": True}), ("correct_inherited_pair", {"fix": True})):
                pp = {i: "A" if optimum(j, "A", mode, **kw) >= optimum(j, "B", mode, **kw) else "B" for i, j in scores.items()}
                summary[name] = {"correct": sum(pp[i] == gold[i] for i in pp), "changed_ids": [i for i in pp if pp[i] != pred[i]]}
    agree = 0
    for i, j in scores.items():
        strengths = strengths_jev(j)
        survivors = [r for r in strengths if r[0] == "reason" and strengths[r] > strengths[("rebuttal",) + r[1:]]]
        assert survivors
        simple = max(survivors, key=lambda r: strengths[r])[2]
        agree += simple == decide(strengths, "preference")[0]
    summary["grounded_equals_strongest_survivor"] = agree
    out[folder] = summary
print(json.dumps(out, indent=2))
