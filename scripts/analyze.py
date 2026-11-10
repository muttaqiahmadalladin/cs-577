#!/usr/bin/env python3
"""Recompute every number in the report from the committed model outputs. Needs numpy and PuLP; makes no API calls.

  python3 scripts/analyze.py            # prints the tables, writes results/report_numbers.json
  python3 scripts/analyze.py --check    # also compares against the values quoted in the report

Inputs
  work/snippets.jsonl, work/rules.txt        from convert_released_cache.py (released snippets, cached arguments, rules)
  work/rows.json, sources/                   from build_dataset.py and get_sources.py (where each released snippet sits in the corpus)
  data/icsi_rebuilt_snippets.jsonl           from build_dataset.py
  results/jev_arm1..4.jsonl                  Jev answers (see docs/EXPERIMENTS.md)
  results/wu_graph_terra/                    arguments written call by call by GPT-6.1 Terra, their Jev scores, Terra zero-shot answers
  results/wu_graph_claude/                   arguments written by Claude Haiku, Haiku scores, Jev scores, Haiku and Sonnet zero-shot answers

Statistics
  accuracy            share of snippets where the predicted letter is the gold letter
  paired test         exact two-sided McNemar test on the discordant pairs (wins and losses)
  bootstrap interval  10,000 resamples of whole meetings with replacement, seed 2026; 2.5th and 97.5th percentiles
                      of the accuracy difference against always answering A
  AUC                 probability that a randomly chosen A-professor snippet scores higher than a B-professor one
  Brier score         mean squared error of P(A is the professor) against the 0/1 label
"""
import json, math, re, sys
from math import comb
from pathlib import Path
import numpy as np
from factor_graph import xor
from grounded_extension import grounded_labels

ROOT = Path(__file__).resolve().parent.parent
RES, RUN = ROOT / "results", ROOT / "results" / "wu_graph_claude"
ASPECTS = ["style", "content", "coordination", "engagement"]
OUT = {}


def jsonl(path): return [json.loads(l) for l in open(path) if l.strip()]
def L(p): return math.log(max(p, 1e-6))
def mcnemar(a_ok, b_ok):
    w = int((a_ok & ~b_ok).sum()); l = int((~a_ok & b_ok).sum()); n = w + l
    return w, l, (1.0 if n == 0 else min(1.0, 2 * sum(comb(n, k) for k in range(min(w, l) + 1)) / 2 ** n))
def auc(y, s):
    pos, neg = s[y], s[~y]
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def record(table, name, pred, gold, score=None, meet=None):
    ok = pred == gold; c = int(ok.sum()); e = dict(correct=c, n=len(gold), accuracy=round(100 * c / len(gold), 1))
    w, l, p = mcnemar(ok, gold); e["vs_always_A"] = dict(wins=w, losses=l, mcnemar_p=p)   # always-A is correct exactly where gold is True
    if meet is not None:
        rng = np.random.default_rng(2026); ms = sorted(set(meet)); idx = {m: np.where(meet == m)[0] for m in ms}; d = []
        for _ in range(10000):
            s = np.concatenate([idx[m] for m in rng.choice(ms, len(ms))]); d.append(ok[s].mean() - gold[s].mean())
        e["vs_always_A"]["meeting_bootstrap_95"] = [round(100 * float(np.percentile(d, 2.5)), 1), round(100 * float(np.percentile(d, 97.5)), 1)]
    if score is not None: e["auc"] = round(auc(gold, np.asarray(score, float)), 3)
    OUT.setdefault(table, {})[name] = e
    print(f"  {name:46s} {c:3d}/{len(gold)} = {e['accuracy']:5.1f}%   vs always A: +{w}/-{l} p={p:.2g}" + (f"   AUC {e['auc']}" if score is not None else ""))
    return ok


def typed_arguments(ans):
    """Typed-statement graph: Jev's P(statement about X) is a reason for X; the same statement about the other speaker is its rebuttal."""
    args = []
    for ai, a in enumerate(ASPECTS):
        base = 2 + 24 * ai
        for si, s in enumerate("AB"):
            o = "B" if s == "A" else "A"
            for j in range(3):
                args.append(dict(variable=base + 3 * si + j, kind="reason", side=s, validity=L(ans[f"{a}{j}_{s}"]), grounding=0.0))
                args.append(dict(variable=base + 6 + 3 * si + j, kind="rebuttal", side=s, validity=L(ans[f"{a}{j}_{o}"]), grounding=0.0))
    return args


def preference_grounded(arguments):
    """Preference-based grounded extension on released-format arguments: strength = P(valid) * P(grounded)."""
    s = {a["id"]: math.exp(a["validity"] + a["grounding"]) for a in arguments}; reasons = [a for a in arguments if a["kind"] == "reason"]
    att = [(a["id"], a["target"]) for a in arguments if a["kind"] == "rebuttal" and s[a["id"]] >= s[a["target"]]]
    att += [(a["id"], b["id"]) for a in reasons for b in reasons if a["side"] != b["side"] and s[a["id"]] > s[b["id"]]]
    lab = grounded_labels(list(s), att)
    n = {x: sum(lab[a["id"]] == "IN" for a in reasons if a["side"] == x) for x in "AB"}
    if n["A"] != n["B"]: return "A" if n["A"] > n["B"] else "B"
    return "A" if sum(s[a["id"]] * (1 if a["side"] == "A" else -1) for a in reasons) >= 0 else "B"


def main():
    rules = (ROOT / "work" / "rules.txt").read_text(); R = jsonl(ROOT / "work" / "snippets.jsonl")
    A1 = {d["id"]: d["answers"] for d in jsonl(RES / "jev_arm1.jsonl")}; A2 = {d["id"]: d["answers"] for d in jsonl(RES / "jev_arm2.jsonl")}
    A3 = {d["id"]: d["answers"] for d in jsonl(RES / "jev_arm3.jsonl")}; A4 = {}
    for d in jsonl(RES / "jev_arm4.jsonl"): A4.setdefault(d["cond"], {})[d["id"]] = d["answers"]

    # ---------------------------------------------------------------- Table 1: the 151 released snippets
    print("Table 1. Released snippets (151)")
    g1 = np.array([r["label"] == "A" for r in R]); rid = [r["id"] for r in R]
    record("released_151", "Always A", np.ones(len(R), bool), g1)
    record("released_151", "XOR graph, cached GPT-3.5 scores", np.array([xor(r["arguments"], r["relations"], rules) == "A" for r in R]), g1)
    pa = np.array([A1[i]["professor_A"] for i in rid]); pb = np.array([A1[i]["professor_B"] for i in rid])
    record("released_151", "Jev, is X the professor", pa >= pb, g1, pa / (pa + pb))
    def rescored(r):   # arguments keep their text and graph position; scores come from Jev (arm 2)
        out = []
        for a in r["arguments"]:
            ans = A2[r["id"]]; v = ans[f"v{a['variable']}"]; g = ans[f"g{a['variable']}" if a["kind"] == "reason" else f"r{a['variable']}"]
            out.append(dict(a, validity=L(v), grounding=L(g)))
        return out
    record("released_151", "XOR graph, Jev scores", np.array([xor(rescored(r), r["relations"], rules) == "A" for r in R]), g1)
    record("released_151", "Preference grounded, cached scores", np.array([preference_grounded(r["arguments"]) == "A" for r in R]), g1)
    record("released_151", "Preference grounded, Jev scores", np.array([preference_grounded(rescored(r)) == "A" for r in R]), g1)
    record("released_151", "Typed-statement graph (Jev)", np.array([xor(typed_arguments(A3[i]), [], rules) == "A" for i in rid]), g1)
    print("  (Grounded extension as proposed, the quote filter and Gemma 4 zero-shot are results of KrishMay05/nlp_research.)")

    # ---------------------------------------------------------------- Data section: released text against corpus speakers
    print("\nData section. Released text against ICSI participant IDs")
    from build_dataset import load_corpus, load_education, released_turns
    src = ROOT / "sources"; M = load_corpus(src); edu = load_education(src); rows = json.load(open(ROOT / "work" / "rows.json"))
    n_cons = lab_ok = wrong = total = heavy = maj_ok = 0
    for r, x in zip(R, rows):
        if not (x["consistent"] and len(x["profs"]) == 1): continue        # each letter is one participant, and exactly one is a professor
        n_cons += 1; turns, lines = released_turns(r["transcript"]); spk = [g[1] for g in M[x["meeting"]][x["start"]:x["start"] + x["n"]]]
        who = {"A": x["mapA"], "B": x["mapB"]}; prof = x["profs"][0]
        lab_ok += ("A" if who["A"] == prof else "B") == r["label"]             # reading 1: a letter is the speaker of the last line of its turns
        w_bad = w_all = 0; prof_words = {"A": 0, "B": 0}
        for letter, idx in turns:
            for k in idx:
                n = len(lines[k].split()); w_all += n; w_bad += n * (spk[k] != who[letter])
                if spk[k] == prof: prof_words[letter] += n
        wrong += w_bad; total += w_all; heavy += w_bad / w_all > 0.5
        maj_ok += ("A" if prof_words["A"] >= prof_words["B"] else "B") == r["label"]   # reading 2: a letter is whoever says most of its words
    OUT["data_audit"] = dict(released_snippets=len(R), located_exactly_once=len(rows), meetings=len({x["meeting"] for x in rows}), one_to_one_with_one_professor=n_cons,
                             label_names_professor_under_last_line_reading=lab_ok, words_under_other_letter=wrong, words_total=total,
                             percent_words_under_other_letter=round(100 * wrong / total, 1), snippets_majority_of_words_under_other_letter=heavy,
                             label_names_letter_with_most_professor_words=maj_ok)
    for k, v in OUT["data_audit"].items(): print(f"  {k}: {v}")

    # ---------------------------------------------------------------- Table 2: the 150 rebuilt snippets
    D = jsonl(ROOT / "data" / "icsi_rebuilt_snippets.jsonl"); ids = [d["id"] for d in D]
    gold = np.array([d["professor"] == "A" for d in D]); rel_gold = np.array([d["released_label"] == "A" for d in D]); meet = np.array([d["meeting"] for d in D])
    byid = {r["id"]: r for r in R}; ok = {}
    print("\nTable 2. Same 150 snippets, released text and labels")
    def direct(A, key):
        a = np.array([A[i][key + "_A"] for i in ids]); b = np.array([A[i][key + "_B"] for i in ids]); return a / (a + b)
    def words_released(i):
        t = re.split(r"(?m)^\s*([AB]):", byid[i]["transcript"]); w = {"A": 0, "B": 0}
        for j in range(1, len(t) - 1, 2): w[t[j]] += len(t[j + 1].split())
        return w["A"] - w["B"]
    w = np.array([words_released(i) for i in ids]); record("released_150", "More words", w >= 0, rel_gold, w)
    p = direct(A1, "professor"); ok["rel_prof"] = record("released_150", "Jev, professor", p >= .5, rel_gold, p)
    p = direct(A1, "more_power"); record("released_150", "Jev, more power", p >= .5, rel_gold, p)
    ok["rel_graph"] = record("released_150", "Typed-statement graph", np.array([xor(typed_arguments(A3[i]), [], rules) == "A" for i in ids]), rel_gold)
    for cond, field, title in (("fixed", "turns_same_span", "rebuilt, same span"), ("ctx15", "turns_pm15", "rebuilt, 15 extra segments per side"), ("ctx60", "turns_pm60", "rebuilt, 60 extra segments per side")):
        print(f"\nTable 2. {title}"); T = f"rebuilt_{cond}"; W, LT = [], []
        for d in D:
            n = {"A": 0, "B": 0}; k = {"A": 0, "B": 0}
            for t in d[field]:
                if t["speaker"] in n: n[t["speaker"]] += len(t["text"].split()); k[t["speaker"]] += 1
            W.append(n["A"] - n["B"]); LT.append(n["A"] / max(k["A"], 1) - n["B"] / max(k["B"], 1))
        W, LT = np.array(W), np.array(LT)
        ok[cond + "_words"] = record(T, "More words", W >= 0, gold, W, meet); record(T, "Longer turns", LT >= 0, gold, LT, meet)
        p = direct(A4[cond], "professor"); ok[cond + "_prof"] = record(T, "Jev, professor", p >= .5, gold, p, meet)
        conf = np.argsort(-np.abs(p - .5)); e = OUT[T]["Jev, professor"]
        e["brier"] = round(float(np.mean((p - gold) ** 2)), 3); e["accuracy_most_confident_fifth"] = round(100 * float(((p >= .5) == gold)[conf][: len(ids) // 5].mean()), 1)
        p2 = direct(A4[cond], "more_power"); record(T, "Jev, more power", p2 >= .5, gold, p2, meet)
        ok[cond + "_graph"] = record(T, "Typed-statement graph", np.array([xor(typed_arguments(A4[cond][i]), [], rules) == "A" for i in ids]), gold, meet=meet)
        if cond == "fixed":
            prof_of = np.array([d["speakers"][d["professor"]] for d in D])
            OUT["professors"] = {str(q): dict(snippets=int((prof_of == q).sum()), jev_accuracy=round(100 * float(ok["fixed_prof"][prof_of == q].mean()), 1)) for q in sorted(set(prof_of), key=lambda q: -(prof_of == q).sum())}
    OUT["brier_base_rate"] = round(float(np.mean((gold.mean() - gold) ** 2)), 3)

    # ---------------------------------------------------------------- Table 3: the Wu factor graph on the rebuilt same-span text
    print("\nTable 3. Wu factor graph on the rebuilt same-span text, by who wrote and who scored the arguments")
    TR = ROOT / "results" / "wu_graph_terra"
    HAIKU = {i: json.load(open(RUN / "scores" / f"{i}.json"))["aspects"] for i in ids}
    JEV = {"haiku": {d["id"]: d["answers"] for d in jsonl(RUN / "jev_scores.jsonl")}, "terra": {d["id"]: d["answers"] for d in jsonl(TR / "jev_scores.jsonl")}}
    def graph_rows(i, writer, scorer, mode):
        """Reason weight: P(valid) * P(grounded). Rebuttal weight: P(counters its reason) * P(grounded) (Jev) or P(valid) * P(grounded) (Haiku)."""
        args, rels = [], []; J = JEV[writer][i]
        for ai, a in enumerate(ASPECTS):
            base = 2 + 24 * ai
            for si, s in enumerate("AB"):
                for j in range(3):
                    v, g = HAIKU[i][a]["reason"][s][j] if scorer == "haiku" else (J[f"{a}|rv|{s}{j}"], J[f"{a}|rg|{s}{j}"])
                    args.append(dict(variable=base + 3 * si + j, kind="reason", side=s, validity=L(v), grounding=L(g)))
                    if mode != "reasons":
                        v, g = HAIKU[i][a]["rebuttal"][s][j] if scorer == "haiku" else (J[f"{a}|ba|{s}{j}"], J[f"{a}|bg|{s}{j}"])
                        args.append(dict(variable=base + 6 + 3 * si + j, kind="rebuttal", side=s, validity=L(v), grounding=L(g)))
            if mode == "all":
                if scorer == "haiku": sc = [x / 5 for x in HAIKU[i][a]["similar"] + HAIKU[i][a]["contra_A"] + HAIKU[i][a]["contra_B"]]
                else: sc = [J[f"{a}|sim|{p}{q}"] for p in range(3) for q in range(p, 3)] + [J[f"{a}|cA|{pq}"] for pq in ("01", "02", "12")] + [J[f"{a}|cB|{pq}"] for pq in ("01", "02", "12")]
                rels += [dict(variable=base + 12 + k, score=v) for k, v in enumerate(sc)]
        return args, rels
    for writer, scorer, tag in (("terra", "jev", "Terra arguments, Jev scores"), ("haiku", "jev", "Haiku arguments, Jev scores"), ("haiku", "haiku", "Haiku arguments, Haiku scores")):
        for mode, nm in (("reasons", "reasons only"), ("rr", "reasons + rebuttals"), ("all", "all relations")):
            ok[f"{writer}_{scorer}_{mode}"] = record("wu_graph", f"Wu graph, {nm} ({tag})", np.array([xor(*graph_rows(i, writer, scorer, mode), rules) == "A" for i in ids]), gold)
        s = np.array([sum(math.exp(a["validity"] + a["grounding"]) * (1 if a["side"] == "A" else -1) for a in graph_rows(i, writer, scorer, "reasons")[0]) for i in ids])
        record("wu_graph", f"Sum of reason scores, no graph ({tag})", s >= 0, gold, s)
    Zt = {d["id"]: d["prediction"] for d in jsonl(TR / "zero_shot.jsonl")}
    ok["zero_terra"] = record("wu_graph", "Terra zero-shot", np.array([Zt[i] == "A" for i in ids]), gold)
    for m in ("haiku", "sonnet"):
        Z = {}
        for k in range(3): Z.update(json.load(open(RUN / f"zero_{m}" / f"zero_{k}.json")))
        ok["zero_" + m] = record("wu_graph", f"{m.capitalize()} zero-shot", np.array([Z[i]["answer"] == "A" for i in ids]), gold, np.array([float(Z[i]["p_A"]) for i in ids]))

    print("\nPaired comparisons (wins / losses for the first method, exact McNemar p)")
    pairs = [("fixed_prof", "rel_prof", "Jev professor: rebuilt same span vs released"), ("fixed_graph", "rel_graph", "Typed graph: rebuilt same span vs released"),
             ("ctx15_prof", "fixed_prof", "Jev professor: 15 extra vs same span"), ("ctx60_prof", "fixed_prof", "Jev professor: 60 extra vs same span"),
             ("fixed_graph", "fixed_prof", "Typed graph vs Jev professor, same span"),
             ("terra_jev_all", "zero_terra", "Wu graph (Terra, Jev; all) vs Terra zero-shot"), ("terra_jev_all", "terra_jev_reasons", "Wu graph (Terra, Jev): all relations vs reasons only"),
             ("terra_jev_all", "fixed_prof", "Wu graph (Terra, Jev; all) vs Jev professor"), ("zero_terra", "fixed_prof", "Terra zero-shot vs Jev professor"),
             ("haiku_jev_all", "fixed_prof", "Wu graph (Haiku, Jev; all) vs Jev professor"), ("haiku_jev_all", "haiku_jev_reasons", "Wu graph (Haiku, Jev): all relations vs reasons only"),
             ("haiku_haiku_all", "zero_haiku", "Wu graph (Haiku, Haiku; all) vs Haiku zero-shot"), ("haiku_haiku_all", "haiku_haiku_reasons", "Wu graph (Haiku, Haiku): all relations vs reasons only"),
             ("zero_sonnet", "haiku_haiku_all", "Sonnet zero-shot vs Wu graph (Haiku, Haiku; all)"), ("zero_sonnet", "fixed_prof", "Sonnet zero-shot vs Jev professor"), ("zero_sonnet", "zero_terra", "Sonnet zero-shot vs Terra zero-shot")]
    for a, b, name in pairs:
        wn, ls, p = mcnemar(ok[a], ok[b]); OUT.setdefault("paired", {})[name] = dict(wins=wn, losses=ls, mcnemar_p=p); print(f"  {name:58s} +{wn}/-{ls}  p={p:.2g}")
    json.dump(OUT, open(RES / "report_numbers.json", "w"), indent=1); print("\nwrote results/report_numbers.json")

    if "--check" in sys.argv:
        expect = {("released_151", "XOR graph, cached GPT-3.5 scores"): 82, ("released_151", "Jev, is X the professor"): 72, ("released_151", "XOR graph, Jev scores"): 76,
                  ("released_151", "Preference grounded, cached scores"): 79, ("released_151", "Preference grounded, Jev scores"): 71, ("released_151", "Typed-statement graph (Jev)"): 77,
                  ("released_150", "More words"): 69, ("released_150", "Jev, professor"): 72, ("released_150", "Jev, more power"): 72, ("released_150", "Typed-statement graph"): 77,
                  ("rebuilt_fixed", "More words"): 100, ("rebuilt_fixed", "Longer turns"): 102, ("rebuilt_fixed", "Jev, professor"): 107, ("rebuilt_fixed", "Jev, more power"): 106, ("rebuilt_fixed", "Typed-statement graph"): 105,
                  ("rebuilt_ctx15", "More words"): 99, ("rebuilt_ctx15", "Longer turns"): 104, ("rebuilt_ctx15", "Jev, professor"): 127, ("rebuilt_ctx15", "Jev, more power"): 119, ("rebuilt_ctx15", "Typed-statement graph"): 121,
                  ("rebuilt_ctx60", "More words"): 103, ("rebuilt_ctx60", "Longer turns"): 100, ("rebuilt_ctx60", "Jev, professor"): 134, ("rebuilt_ctx60", "Jev, more power"): 132, ("rebuilt_ctx60", "Typed-statement graph"): 136,
                  ("wu_graph", "Wu graph, reasons only (Terra arguments, Jev scores)"): 100, ("wu_graph", "Wu graph, reasons + rebuttals (Terra arguments, Jev scores)"): 108, ("wu_graph", "Wu graph, all relations (Terra arguments, Jev scores)"): 108,
                  ("wu_graph", "Wu graph, reasons only (Haiku arguments, Jev scores)"): 110, ("wu_graph", "Wu graph, reasons + rebuttals (Haiku arguments, Jev scores)"): 105, ("wu_graph", "Wu graph, all relations (Haiku arguments, Jev scores)"): 105,
                  ("wu_graph", "Wu graph, reasons only (Haiku arguments, Haiku scores)"): 103, ("wu_graph", "Wu graph, reasons + rebuttals (Haiku arguments, Haiku scores)"): 101, ("wu_graph", "Wu graph, all relations (Haiku arguments, Haiku scores)"): 102,
                  ("wu_graph", "Terra zero-shot"): 109, ("wu_graph", "Haiku zero-shot"): 102, ("wu_graph", "Sonnet zero-shot"): 114}
        audit_expect = dict(located_exactly_once=151, meetings=45, one_to_one_with_one_professor=128, label_names_professor_under_last_line_reading=128, words_under_other_letter=7596,
                            words_total=13185, snippets_majority_of_words_under_other_letter=73, label_names_letter_with_most_professor_words=69)
        bad = [(k, v, OUT[k[0]][k[1]]["correct"]) for k, v in expect.items() if OUT[k[0]][k[1]]["correct"] != v]
        e = OUT["rebuilt_fixed"]["Jev, professor"]
        if e["vs_always_A"]["meeting_bootstrap_95"] != [6.7, 22.0] or e["brier"] != 0.189 or e["accuracy_most_confident_fifth"] != 93.3: bad.append(("Jev professor interval/Brier/top fifth", "[6.7, 22.0] 0.189 93.3", (e["vs_always_A"]["meeting_bootstrap_95"], e["brier"], e["accuracy_most_confident_fifth"])))
        bad += [(k, v, OUT["data_audit"][k]) for k, v in audit_expect.items() if OUT["data_audit"][k] != v]
        n = len(expect) + 1 + len(audit_expect)
        for k, v, got in bad: print("MISMATCH", k, "report:", v, "recomputed:", got)
        print(f"check: {n - len(bad)} of {n} report values reproduced"); sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
