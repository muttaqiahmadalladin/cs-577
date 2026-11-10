#!/usr/bin/env python3
"""Search over grounded-extension policies on the rebuilt snippets, with honest model selection.

Every policy uses the Jev scores already collected (results/wu_graph_claude/jev_scores.jsonl):
  reasons    rv = P(valid), rg = P(grounded)
  rebuttals  ba = P(counters its reason), bg = P(grounded)
  pairs      sim = P(an A reason and a B reason describe the same behavior with the same reasoning)

A policy is a choice of:
  reason strength    rv*rg | rg | rv
  rebuttal strength  ba*bg | ba | bg
  rebuttal rule      pref (attack succeeds if rebuttal >= reason) | gate at 0.3, 0.5 or 0.7 (rebuttal attacks if its strength clears the threshold)
  cross-side rule    none | pref (stronger reason defeats any opposing reason) | aspect (same, within an aspect only) | similar (only pairs with sim >= 0.5; stronger wins)
  decision           count of IN reasons | summed strength of IN reasons
The labelling is always Dung's grounded labelling. Ties go to the summed strength of all reasons, then to A.

Selection protocol: meetings are split at random into a development half and a test half. The policy with the best
development accuracy is chosen and scored on the test half, next to the direct Jev question on the same test half.
This is repeated over many splits, so the reported gain does not come from picking a policy on the snippets it is scored on.

  python3 scripts/grounded_policy_search.py
"""
import itertools, json, random, statistics
from pathlib import Path
from grounded_extension import grounded_labels, ASPECTS, ROOT, RUN, mcnemar

R_STR = {"rv*rg": lambda a, k: a[k("rv")] * a[k("rg")], "rg": lambda a, k: a[k("rg")], "rv": lambda a, k: a[k("rv")]}
B_STR = {"ba*bg": lambda a, k: a[k("ba")] * a[k("bg")], "ba": lambda a, k: a[k("ba")], "bg": lambda a, k: a[k("bg")]}
POLICIES = list(itertools.product(R_STR, B_STR, ("pref", 0.3, 0.5, 0.7), ("none", "pref", "aspect", "similar"), ("count", "strength")))


def decide(ans, policy):
    rs, bs, reb_rule, cross, decision = policy
    reasons = [(a, s, j) for a in ASPECTS for s in "AB" for j in range(3)]
    sr = {r: R_STR[rs](ans, lambda t, r=r: f"{r[0]}|{t}|{r[1]}{r[2]}") for r in reasons}
    sb = {r: B_STR[bs](ans, lambda t, r=r: f"{r[0]}|{t}|{r[1]}{r[2]}") for r in reasons}
    attacks = [(("b",) + r, r) for r in reasons if (sb[r] >= sr[r] if reb_rule == "pref" else sb[r] >= reb_rule)]
    if cross != "none":
        for r in reasons:
            for q in reasons:
                if r[1] == q[1] or sr[r] <= sr[q]: continue
                if cross == "aspect" and r[0] != q[0]: continue
                if cross == "similar":
                    if r[0] != q[0]: continue
                    i, j = (r[2], q[2]) if r[1] == "A" else (q[2], r[2])
                    if j < i or ans[f"{r[0]}|sim|{i}{j}"] < 0.5: continue
                attacks.append((r, q))
    lab = grounded_labels(reasons + [("b",) + r for r in reasons], attacks)
    IN = [r for r in reasons if lab[r] == "IN"]
    val = {s: (sum(1 for r in IN if r[1] == s) if decision == "count" else sum(sr[r] for r in IN if r[1] == s)) for s in "AB"}
    tot = {s: sum(sr[r] for r in reasons if r[1] == s) for s in "AB"}
    return max("AB", key=lambda s: (val[s], tot[s], s == "A")), len(IN), val["A"] != val["B"]


def main():
    data = [json.loads(l) for l in open(ROOT / "data" / "icsi_rebuilt_snippets.jsonl")]
    gold = {d["id"]: d["professor"] for d in data}; meeting = {d["id"]: d["meeting"] for d in data}; ids = list(gold)
    jev = {d["id"]: d["answers"] for d in map(json.loads, open(RUN / "jev_scores.jsonl"))}
    a4 = {d["id"]: d["answers"] for d in map(json.loads, open(ROOT / "results" / "jev_arm4.jsonl")) if d["cond"] == "fixed"}
    direct = {i: ("A" if a4[i]["professor_A"] >= a4[i]["professor_B"] else "B") == gold[i] for i in ids}
    res = {p: {i: decide(jev[i], p) for i in ids} for p in POLICIES}
    ok = {p: {i: res[p][i][0] == gold[i] for i in ids} for p in POLICIES}
    full = sorted(POLICIES, key=lambda p: -sum(ok[p].values()))
    print(f"{len(POLICIES)} policies. Accuracy on all 150 (optimistic, selected on the same snippets): best {sum(ok[full[0]].values())}, median {sorted(sum(v.values()) for v in ok.values())[len(POLICIES)//2]}, worst {sum(ok[full[-1]].values())}; Jev direct {sum(direct.values())}")
    for p in full[:5]:
        r = res[p]; print(f"   {sum(ok[p].values())}/150  {p}  reasons IN {sum(v[1] for v in r.values())}/3600, decided without tie-break {sum(v[2] for v in r.values())}")
    rng = random.Random(2026); meetings = sorted(set(meeting.values())); gains, chosen, tests, dtests = [], {}, [], []
    for _ in range(500):
        rng.shuffle(meetings); dev_m = set(meetings[: len(meetings) // 2])
        dev = [i for i in ids if meeting[i] in dev_m]; test = [i for i in ids if meeting[i] not in dev_m]
        best = max(POLICIES, key=lambda p: sum(ok[p][i] for i in dev)); chosen[best] = chosen.get(best, 0) + 1
        t = sum(ok[best][i] for i in test) / len(test); d = sum(direct[i] for i in test) / len(test); tests.append(t); dtests.append(d); gains.append(t - d)
    q = sorted(gains)
    print(f"\nSelection on a development half of meetings, scored on the other half (500 splits):")
    print(f"   selected policy, test accuracy: mean {100*statistics.mean(tests):.1f}%   Jev direct on the same test halves: mean {100*statistics.mean(dtests):.1f}%")
    print(f"   gain over direct: mean {100*statistics.mean(gains):+.1f} points, middle 95% of splits {100*q[12]:+.1f} to {100*q[487]:+.1f}; selected policy ahead in {sum(g > 0 for g in gains)} of 500 splits")
    top = sorted(chosen.items(), key=lambda kv: -kv[1])[:3]
    for p, n in top: print(f"   chosen in {n} splits: {p}")
    json.dump(dict(policies=len(POLICIES), best_full=dict(policy=list(map(str, full[0])), correct=sum(ok[full[0]].values())), direct_full=sum(direct.values()),
                   split_selection=dict(mean_test=statistics.mean(tests), mean_direct=statistics.mean(dtests), mean_gain=statistics.mean(gains), gain_95=[q[12], q[487]], ahead=sum(g > 0 for g in gains), splits=500),
                   most_chosen=[dict(policy=list(map(str, p)), splits=n) for p, n in top]), open(RUN / "grounded_policy_search.json", "w"), indent=1)


if __name__ == "__main__":
    main()
