#!/usr/bin/env python3
"""Gradual (soft) argumentation over the stored arguments, in the style of ArgLLM (Freedman et al., AAAI 2025).

A quantitative bipolar argumentation framework (QBAF) is built for the claim "A has more power than B":
  reasons for A support the claim, reasons for B attack it, and each rebuttal attacks its own reason.
Base scores are the Jev scores already in results/: reason = P(valid) * P(grounded), rebuttal = P(counters) * P(grounded).
The strength of the claim is computed with a gradual semantics and A is predicted when it exceeds 0.5. No model is called.

Eight variants are fixed in advance and all are reported (none is selected on the test set):
  semantics   DF-QuAD (Rago et al. 2016)  or  Quadratic Energy (Potyka 2018)
  structure   flat (24 reasons on the claim)  or  by aspect (reasons -> 4 aspect arguments -> claim)
  prior       0.5  or  the direct Jev answer P(A is the professor), so the arguments update a direct answer

Also prints a simple ensemble of the direct answers as a reference for what combining judgments (not arguments) gives.

  python3 scripts/qbaf.py        # writes results/qbaf_results.json
"""
import itertools, json
from pathlib import Path
import numpy as np
from analyze import ASPECTS, jsonl, mcnemar

ROOT = Path(__file__).resolve().parent.parent


def dfquad(base, att, sup):
    f = lambda v: 1 - float(np.prod([1 - x for x in v])) if v else 0.0
    a, s = f(att), f(sup)
    return base - base * (a - s) if a >= s else base + (1 - base) * (s - a)


def qenergy(base, att, sup):
    e = sum(sup) - sum(att); h = max(e, 0) ** 2 / (1 + max(e, 0) ** 2); g = max(-e, 0) ** 2 / (1 + max(-e, 0) ** 2)
    return base + (1 - base) * h - base * g


def claim_strength(J, sem, by_aspect, prior):
    """Strength of 'A has more power'. Symmetric by construction: swapping A and B gives 1 - strength when prior is 0.5."""
    def reason(a, s, j):
        return sem(J[f"{a}|rv|{s}{j}"] * J[f"{a}|rg|{s}{j}"], [J[f"{a}|ba|{s}{j}"] * J[f"{a}|bg|{s}{j}"]], [])
    if not by_aspect:
        return sem(prior, [reason(a, "B", j) for a in ASPECTS for j in range(3)], [reason(a, "A", j) for a in ASPECTS for j in range(3)])
    asp = [sem(0.5, [reason(a, "B", j) for j in range(3)], [reason(a, "A", j) for j in range(3)]) for a in ASPECTS]
    # an aspect argument above 0.5 supports the claim with weight 2*(x-0.5); below 0.5 it attacks with the mirrored weight
    return sem(prior, [2 * (0.5 - x) for x in asp if x < 0.5], [2 * (x - 0.5) for x in asp if x > 0.5])


def main():
    D = jsonl(ROOT / "data" / "icsi_rebuilt_snippets.jsonl"); ids = [d["id"] for d in D]; gold = np.array([d["professor"] == "A" for d in D])
    a4 = {d["id"]: d["answers"] for d in jsonl(ROOT / "results" / "jev_arm4.jsonl") if d["cond"] == "fixed"}
    pj = np.array([a4[i]["professor_A"] / max(a4[i]["professor_A"] + a4[i]["professor_B"], 1e-9) for i in ids]); jev_ok = (pj >= 0.5) == gold
    runs = {"Terra": "wu_graph_terra", "GLM": "glm_run", "Haiku": "wu_graph_claude"}
    out = {}; print(f"{len(ids)} snippets; always A {int(gold.sum())}; Jev direct {int(jev_ok.sum())}\n")
    print(f"{'arguments':9s} {'semantics':8s} {'structure':9s} {'prior':10s}  correct   vs Jev direct")
    for name, folder in runs.items():
        J = {d["id"]: d["answers"] for d in jsonl(ROOT / "results" / folder / "jev_scores.jsonl")}
        for (sn, sem), by_aspect, use_prior in itertools.product((("DF-QuAD", dfquad), ("QE", qenergy)), (False, True), (False, True)):
            st = np.array([claim_strength(J[i], sem, by_aspect, pj[k] if use_prior else 0.5) for k, i in enumerate(ids)])
            ok = (st >= 0.5) == gold; w, l, p = mcnemar(ok, jev_ok)
            key = f"{name}|{sn}|{'aspect' if by_aspect else 'flat'}|{'jev' if use_prior else '0.5'}"
            out[key] = dict(correct=int(ok.sum()), accuracy=round(100 * float(ok.mean()), 1), vs_jev_direct=dict(wins=w, losses=l, mcnemar_p=p))
            print(f"{name:9s} {sn:8s} {'by aspect' if by_aspect else 'flat':9s} {'Jev direct' if use_prior else '0.5':10s}  {int(ok.sum()):3d}/150 = {100 * ok.mean():4.1f}%   +{w}/-{l} p={p:.2g}")
        print()
    # reference: combine direct judgments instead of arguments
    def zs(path): return {z["id"]: (z["prediction"] == "A" if z.get("p_A") is None else z["p_A"] >= 0.5) for z in jsonl(path)}
    glm, terra = zs(ROOT / "results" / "glm_run" / "zero_shot.jsonl"), zs(ROOT / "results" / "wu_graph_terra" / "zero_shot.jsonl")
    son = {}
    for f in sorted((ROOT / "results" / "wu_graph_claude" / "zero_sonnet").glob("*.json")): son.update({i: float(z["p_A"]) >= 0.5 for i, z in json.load(open(f)).items()})
    votes = np.array([[glm[i], terra[i], son[i], pj[k] >= 0.5] for k, i in enumerate(ids)]).sum(1)
    pred = np.where(votes == 2, pj >= 0.5, votes > 2); ok = pred == gold; w, l, p = mcnemar(ok, jev_ok)
    out["ensemble|majority of GLM, Terra, Sonnet, Jev (ties to Jev)"] = dict(correct=int(ok.sum()), accuracy=round(100 * float(ok.mean()), 1), vs_jev_direct=dict(wins=w, losses=l, mcnemar_p=p))
    print(f"Reference, no arguments: majority vote of GLM, Terra, Sonnet and Jev direct answers (ties to Jev)  {int(ok.sum())}/150 = {100 * ok.mean():.1f}%   vs Jev direct +{w}/-{l} p={p:.2g}")
    json.dump(out, open(ROOT / "results" / "qbaf_results.json", "w"), indent=1)


if __name__ == "__main__":
    main()
