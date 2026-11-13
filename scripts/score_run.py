#!/usr/bin/env python3
"""Score one run of wu_pipeline.py (any model) on the rebuilt snippets. Needs numpy and PuLP.

Reads work/<run>/ (gen, zero, jev and optionally llm) and work/<run>_ctx15, work/<run>_ctx60 (zero only), and prints the
same rows as Table 3 of the report for that model: the model asked directly, the three variants of the Wu factor graph,
the sum of reason scores, and the grounded extension under both attack relations. Every row is compared with always
answering A and with the direct Jev question at the same context length (results/jev_arm4.jsonl) by the exact McNemar test.

  python3 scripts/score_run.py --run glm_run --name "GLM-5.3"

With no work/<run>/ folder it rescores the committed results/<run>/ files instead, which is how reproduce.py checks a
stored run. Writes results/<run>/ (arguments.jsonl, jev_scores.jsonl, zero_shot*.jsonl, results.json) so the run can be committed.
"""
import argparse, json, math
from pathlib import Path
import numpy as np
from analyze import ASPECTS, L, jsonl, mcnemar
from factor_graph import xor
from grounded_extension import decide, strengths_jev

ROOT = Path(__file__).resolve().parent.parent


def load(d, stored=None):
    """One JSON per snippet from a work folder; if that is absent, the committed results/<run>/<stored>.jsonl."""
    if d.exists(): return {f.stem: json.loads(f.read_text()) for f in sorted(d.glob("*.json"))}
    return {r["id"]: r for r in jsonl(stored)} if stored and stored.exists() else {}


def graph_rows(J, mode, own=None):
    """Same layout as analyze.py. Jev scores unless `own` (the model's own yes/no scores from the llm stage) is given."""
    args, rels = [], []
    for ai, a in enumerate(ASPECTS):
        base = 2 + 24 * ai
        for si, s in enumerate("AB"):
            for j in range(3):
                v, g = own[a]["reason"][s][j] if own else (J[f"{a}|rv|{s}{j}"], J[f"{a}|rg|{s}{j}"])
                args.append(dict(variable=base + 3 * si + j, kind="reason", side=s, validity=L(v), grounding=L(g)))
                if mode != "reasons":
                    v, g = own[a]["rebuttal"][s][j] if own else (J[f"{a}|ba|{s}{j}"], J[f"{a}|bg|{s}{j}"])
                    args.append(dict(variable=base + 6 + 3 * si + j, kind="rebuttal", side=s, validity=L(v), grounding=L(g)))
        if mode == "all":
            sc = own[a]["similar"] + own[a]["contra_A"] + own[a]["contra_B"] if own else \
                [J[f"{a}|sim|{p}{q}"] for p in range(3) for q in range(p, 3)] + [J[f"{a}|cA|{pq}"] for pq in ("01", "02", "12")] + [J[f"{a}|cB|{pq}"] for pq in ("01", "02", "12")]
            rels += [dict(variable=base + 12 + k, score=v) for k, v in enumerate(sc)]
    return args, rels


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--run", default="glm_run"); ap.add_argument("--name", default="GLM"); a = ap.parse_args()
    W = ROOT / "work"; run = W / a.run; out = ROOT / "results" / a.run; out.mkdir(parents=True, exist_ok=True)
    D = jsonl(ROOT / "data" / "icsi_rebuilt_snippets.jsonl"); gold_of = {d["id"]: d["professor"] for d in D}
    rules = (W / "rules.txt").read_text()   # written by convert_released_cache.py
    jev_all = {c: {d["id"]: d["answers"] for d in jsonl(ROOT / "results" / "jev_arm4.jsonl") if d["cond"] == c} for c in ("fixed", "ctx15", "ctx60")}
    jev_direct = jev_all["fixed"]
    R = {}

    def row(label, pred, ids, jev_direct=jev_direct):
        """pred: dict id -> 'A'/'B'. Reports on the ids present; says so if any of the 150 are missing.
        jev_direct: the direct Jev answers at the same context length as pred."""
        ids = [i for i in ids if i in pred]
        if not ids: return
        gold = np.array([gold_of[i] == "A" for i in ids]); ok = np.array([pred[i] == gold_of[i] for i in ids])
        w, l, p = mcnemar(ok, gold)
        jok = np.array([(jev_direct[i]["professor_A"] >= jev_direct[i]["professor_B"]) == (gold_of[i] == "A") for i in ids]); jw, jl, jp = mcnemar(ok, jok)
        R[label] = dict(correct=int(ok.sum()), n=len(ids), accuracy=round(100 * float(ok.mean()), 1), vs_always_A=dict(wins=w, losses=l, mcnemar_p=p), vs_jev_direct=dict(wins=jw, losses=jl, mcnemar_p=jp))
        note = "" if len(ids) == len(gold_of) else f"   [only {len(ids)} of {len(gold_of)} snippets present]"
        print(f"  {label:44s} {int(ok.sum()):3d}/{len(ids)} = {100 * ok.mean():5.1f}%   vs always A +{w}/-{l} p={p:.2g}   vs Jev direct +{jw}/-{jl} p={jp:.2g}{note}")

    all_ids = list(gold_of)
    print(f"{a.name}: {len(all_ids)} rebuilt snippets, always A is correct in {sum(v == 'A' for v in gold_of.values())}, Jev direct in "
          f"{sum((jev_direct[i]['professor_A'] >= jev_direct[i]['professor_B']) == (gold_of[i] == 'A') for i in all_ids)}")
    for cond, tag in (("", "original span"), ("_ctx15", "15 extra segments"), ("_ctx60", "60 extra segments")):
        Z = load(W / (a.run + cond) / "zero", out / f"zero_shot{cond}.jsonl")
        if not Z: continue
        undecided = [i for i, z in Z.items() if z["p_A"] == 0.5]
        if undecided: print(f"  note: {len(undecided)} answers named neither A nor B ({tag}); they are counted as A")
        row(f"{a.name} asked directly, {tag}", {i: "A" if z["p_A"] >= 0.5 else "B" for i, z in Z.items()}, all_ids, jev_all[cond[1:] or "fixed"])
        if (W / (a.run + cond) / "zero").exists():
            with open(out / f"zero_shot{cond}.jsonl", "w") as f:
                for i in all_ids:
                    if i in Z: f.write(json.dumps(Z[i]) + "\n")
    G, J, OWN = load(run / "gen", out / "arguments.jsonl"), {i: d["answers"] for i, d in load(run / "jev", out / "jev_scores.jsonl").items()}, {i: d["aspects"] for i, d in load(run / "llm", out / "own_scores.jsonl").items()}
    if J:
        for mode, nm in (("reasons", "reasons only"), ("rr", "reasons + rebuttals"), ("all", "all relations")):
            row(f"Wu graph, {nm} (Jev scores)", {i: xor(*graph_rows(J[i], mode), rules) for i in J}, all_ids)
        row("Sum of reason scores, no graph (Jev scores)", {i: "A" if sum(math.exp(x["validity"] + x["grounding"]) * (1 if x["side"] == "A" else -1) for x in graph_rows(J[i], "reasons")[0]) >= 0 else "B" for i in J}, all_ids)
        for rel in ("proposed", "preference"):
            res = {i: decide(strengths_jev(J[i]), rel) for i in J}
            row(f"Grounded extension, {rel} (Jev scores)", {i: r[0] for i, r in res.items()}, all_ids)
            R[f"Grounded extension, {rel} (Jev scores)"].update(decided_by_in_count=sum(r[1] == "IN count" for r in res.values()), reasons_in=sum(r[2] for r in res.values()), reasons_total=24 * len(res))
    if OWN:
        for mode, nm in (("reasons", "reasons only"), ("rr", "reasons + rebuttals"), ("all", "all relations")):
            row(f"Wu graph, {nm} ({a.name} scores)", {i: xor(*graph_rows(None, mode, OWN[i]), rules) for i in OWN}, all_ids)
    for name, src in (("arguments", G), ("jev_scores", {i: dict(id=i, answers=v) for i, v in J.items()}), ("own_scores", {i: dict(id=i, aspects=v) for i, v in OWN.items()})):
        if src and run.exists():
            with open(out / f"{name}.jsonl", "w") as f:
                for i in all_ids:
                    if i in src: f.write(json.dumps(src[i]) + "\n")
    stored = out / "results.json"
    if not run.exists() and stored.exists():   # rescoring committed files: report whether the stored numbers come back
        old = json.loads(stored.read_text())["rows"]; same = sum(json.loads(json.dumps(R[k])) == old.get(k) for k in R)
        print(f"check: {same} of {len(old)} stored rows reproduced")
        if same != len(old) or len(R) != len(old): raise SystemExit(1)
        return
    json.dump(dict(model=a.name, rows=R), open(stored, "w"), indent=1)
    print(f"wrote results/{a.run}/")


if __name__ == "__main__":
    main()
