"""Read-only forensic checks of the pinned cs-577 predictions; no model calls."""
import collections
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(sys.argv[1])


def jl(p):
    return [json.loads(x) for x in (ROOT / p).read_text().splitlines() if x.strip()]


D = jl("data/icsi_rebuilt_snippets.jsonl")
ids = [d["id"] for d in D]
gold = np.array([d["professor"] == "A" for d in D])
relgold = np.array([d["released_label"] == "A" for d in D])
meet = np.array([d["meeting"] for d in D])
prof = np.array([d["speakers"][d["professor"]] for d in D])
kept = np.array([d["letters_from_released"] for d in D])
A = {(r["cond"], r["id"]): r["answers"] for r in jl("results/jev_arm4.jsonl")}
AR = {r["id"]: r["answers"] for r in jl("results/jev_arm1.jsonl")}
pred = {c: np.array([A[c, i]["professor_A"] >= A[c, i]["professor_B"] for i in ids]) for c in ("fixed", "ctx15", "ctx60")}
ok = {c: p == gold for c, p in pred.items()}
relpred = np.array([AR[i]["professor_A"] >= AR[i]["professor_B"] for i in ids])
relok = relpred == relgold


def compare(name, a, b, mask=None):
    mask = np.ones(len(D), dtype=bool) if mask is None else mask
    delta = a[mask].astype(int) - b[mask].astype(int)
    groups = meet[mask]
    ms = sorted(set(groups))
    counts = np.array([(groups == m).sum() for m in ms])
    sums = np.array([delta[groups == m].sum() for m in ms])
    rng = np.random.default_rng(2026)
    sample = rng.integers(0, len(ms), size=(100000, len(ms)))
    bs = sums[sample].sum(1) / counts[sample].sum(1)
    w, l = (delta == 1).sum(), (delta == -1).sum()
    n = int(w + l)
    p = min(1., 2 * sum(math.comb(n, k) for k in range(int(min(w, l)) + 1)) / 2 ** n) if n else 1.
    return dict(name=name, n=int(mask.sum()), meetings=len(ms), a_correct=int(a[mask].sum()), b_correct=int(b[mask].sum()), wins=int(w), losses=int(l), exact_mcnemar=p, delta_pp=round(100*float(delta.mean()), 3), meeting_bootstrap_95_pp=[round(100*float(v), 3) for v in np.percentile(bs, [2.5, 97.5])])


out = dict(meetings=dict(collections.Counter(meet)), professors=dict(collections.Counter(prof)), label_changes=[i for i, a, b in zip(ids, gold, relgold) if a != b])
out["comparisons"] = [compare("fixed versus released", ok["fixed"], relok), compare("fixed versus released, letters kept", ok["fixed"], relok, kept), compare("fixed versus released, labels unchanged", ok["fixed"], relok, gold == relgold), compare("fixed versus always A", ok["fixed"], gold), compare("ctx15 versus fixed", ok["ctx15"], ok["fixed"]), compare("ctx60 versus fixed", ok["ctx60"], ok["fixed"])]
for c in ["fixed", "ctx15", "ctx60"]:
    out[c+"_by_professor"] = {p: dict(n=int((prof == p).sum()), correct=int(ok[c][prof == p].sum())) for p in sorted(set(prof))}
for f in ["results/jev_arm1.jsonl", "results/jev_arm4.jsonl", "results/glm_run/zero_shot.jsonl", "results/glm_run/judge.jsonl", "results/wu_graph_terra/zero_shot.jsonl", "results/wu_graph_terra/jev_scores.jsonl", "results/glm_run/jev_scores.jsonl", "results/wu_graph_claude/jev_scores.jsonl"]:
    rows = jl(f)
    keys = [(r.get("cond", ""), r["id"]) for r in rows]
    out.setdefault("coverage", {})[f] = dict(rows=len(rows), unique_keys=len(set(keys)), ids=len(set(r["id"] for r in rows)))
J = {r["id"]: r for r in jl("results/glm_run/judge.jsonl")}
Z = {r["id"]: r for r in jl("results/glm_run/zero_shot.jsonl")}
direct = np.array([Z[i]["p_A"] >= .5 for i in ids]) == gold
pa = np.array([J[i]["A_first"] == "A" for i in ids])
pb = np.array([J[i]["B_first"] == "A" for i in ids])
out["comparisons"].extend([compare("judge A-first versus GLM direct", pa == gold, direct), compare("judge B-first versus GLM direct", pb == gold, direct), compare("judge A-first versus B-first", pa == gold, pb == gold)])
out["judge_order_disagreement_ids"] = [i for i, a, b in zip(ids, pa, pb) if a != b]
out["relabelled_case_summary"] = dict(n=int((gold != relgold).sum()), original_predictions_released_gold=int(relok[gold != relgold].sum()), original_predictions_rebuilt_gold=int((relpred == gold)[gold != relgold].sum()), rebuilt_predictions_rebuilt_gold=int(ok["fixed"][gold != relgold].sum()))
print(json.dumps(out, indent=2))
