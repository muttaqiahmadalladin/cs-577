#!/usr/bin/env python3
"""Dung's grounded extension over the reasons and rebuttals of each rebuilt snippet. Standard library only.

Arguments   24 reasons (3 per speaker per aspect) and 24 rebuttals (one per reason), from
            results/wu_graph_claude/arguments/. A reason for X supports "X is the professor".
Strengths   reason   s = P(valid) * P(grounded)
            rebuttal s = P(counters its reason) * P(grounded)
            taken from the Haiku scores (scores/) or the Jev scores (jev_scores.jsonl).

Two attack relations are evaluated:

  proposed     As written in the project proposal. Every rebuttal attacks its reason, and every
               reason for A and every reason for B attack each other. Strengths are not used.
  preference   Preference-based argumentation (Amgoud and Cayrol). An attack succeeds only if the
               attacker is at least as strong as its target: a rebuttal defeats its reason when
               s(rebuttal) >= s(reason), and a reason defeats an opposing reason when it is
               strictly stronger.

Grounded labelling (the least fixed point): an argument is IN when all of its attackers are OUT
(so unattacked arguments are IN), OUT when at least one attacker is IN, and UNDECIDED otherwise.

Decision: the speaker with more IN reasons. Ties go to the larger sum of reason strengths, then to A.
Both tie rules were fixed in the proposal.

  python3 scripts/grounded_extension.py
"""
import json
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "results" / "wu_graph_claude"
ASPECTS = ["style", "content", "coordination", "engagement"]


def grounded_labels(nodes, attacks):
    attackers = {n: set() for n in nodes}
    for a, b in attacks: attackers[b].add(a)
    IN, OUT = set(), set()
    while True:
        new_in = {n for n in nodes if n not in IN and n not in OUT and attackers[n] <= OUT}
        new_out = {n for n in nodes if n not in IN and n not in OUT and attackers[n] & (IN | new_in)}
        if not new_in and not new_out: break
        IN |= new_in; OUT |= new_out
    return {n: "IN" if n in IN else "OUT" if n in OUT else "UNDECIDED" for n in nodes}


def strengths_haiku(i):
    sc = json.load(open(RUN / "scores" / f"{i}.json"))["aspects"]; s = {}
    for a in ASPECTS:
        for side in "AB":
            for j in range(3):
                v, g = sc[a]["reason"][side][j]; s[("reason", a, side, j)] = v * g
                v, g = sc[a]["rebuttal"][side][j]; s[("rebuttal", a, side, j)] = v * g
    return s


def strengths_jev(ans):
    s = {}
    for a in ASPECTS:
        for side in "AB":
            for j in range(3):
                s[("reason", a, side, j)] = ans[f"{a}|rv|{side}{j}"] * ans[f"{a}|rg|{side}{j}"]
                s[("rebuttal", a, side, j)] = ans[f"{a}|ba|{side}{j}"] * ans[f"{a}|bg|{side}{j}"]
    return s


def decide(s, relation):
    reasons = [k for k in s if k[0] == "reason"]; attacks = []
    for r in reasons:
        b = ("rebuttal",) + r[1:]
        if relation == "proposed" or s[b] >= s[r]: attacks.append((b, r))
    for r in reasons:
        for q in reasons:
            if r[2] != q[2] and (relation == "proposed" or s[r] > s[q]): attacks.append((r, q))
    lab = grounded_labels(list(s), attacks)
    n_in = {side: sum(lab[r] == "IN" for r in reasons if r[2] == side) for side in "AB"}
    total = {side: sum(s[r] for r in reasons if r[2] == side) for side in "AB"}
    pred = max("AB", key=lambda side: (n_in[side], total[side], side == "A"))
    route = "IN count" if n_in["A"] != n_in["B"] else "strength sum" if total["A"] != total["B"] else "A by default"
    return pred, route, sum(n_in.values()), sum(lab[r] == "UNDECIDED" for r in reasons)


def mcnemar(wins, losses):
    n = wins + losses
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, k) for k in range(min(wins, losses) + 1)) / 2 ** n)


def main():
    gold = {d["id"]: d["professor"] for d in map(json.loads, open(ROOT / "data" / "icsi_rebuilt_snippets.jsonl"))}
    jev = {d["id"]: d["answers"] for d in map(json.loads, open(RUN / "jev_scores.jsonl"))}
    ids = list(gold); out = {}
    print(f"{len(ids)} snippets; always A is correct in {sum(v == 'A' for v in gold.values())}")
    for scorer, get in (("Haiku scores", strengths_haiku), ("Jev scores", lambda i: strengths_jev(jev[i]))):
        S = {i: get(i) for i in ids}
        for relation in ("proposed", "preference"):
            res = {i: decide(S[i], relation) for i in ids}
            correct = sum(res[i][0] == gold[i] for i in ids)
            wins = sum(res[i][0] == gold[i] and gold[i] != "A" for i in ids); losses = sum(res[i][0] != gold[i] and gold[i] == "A" for i in ids)
            by_count = [i for i in ids if res[i][1] == "IN count"]
            row = dict(correct=correct, accuracy=round(100 * correct / len(ids), 1), vs_always_A=dict(wins=wins, losses=losses, mcnemar_p=mcnemar(wins, losses)),
                       decided_by_in_count=len(by_count), correct_among_those=sum(res[i][0] == gold[i] for i in by_count),
                       reasons_in=sum(r[2] for r in res.values()), reasons_undecided=sum(r[3] for r in res.values()), reasons_total=24 * len(ids))
            out[f"{relation}, {scorer}"] = row
            print(f"{relation:10s} {scorer:12s} {correct}/{len(ids)} = {row['accuracy']}%  vs always A +{wins}/-{losses} p={row['vs_always_A']['mcnemar_p']:.3g}  "
                  f"decided by IN count: {len(by_count)} (correct {row['correct_among_those']})  reasons IN {row['reasons_in']}/{row['reasons_total']}, undecided {row['reasons_undecided']}")
    json.dump(out, open(RUN / "grounded_results.json", "w"), indent=1)


if __name__ == "__main__":
    main()
