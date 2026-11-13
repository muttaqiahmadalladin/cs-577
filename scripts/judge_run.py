#!/usr/bin/env python3
"""Debate with a judge: the model reads the conversation and the stored arguments for both sides, then decides.

For each rebuilt snippet the judge prompt holds the conversation, the 12 reasons that A has more power and the 12 that
B does (from results/<run>/arguments.jsonl), each followed by its rebuttal, and asks which speaker has more power.
Every snippet is judged twice, once with A's case first and once with B's case first, to measure order effects.
This is the debate protocol of Khan et al. (ICML 2024) with the judge seeing the full text, so there is no
information gap between debaters and judge.

Uses the same environment variables as wu_pipeline.py (see run_glm.sh, which sets them: `bash scripts/run_glm.sh judge`).
Resumable; answers go to work/<run>/judge/ and, when complete, to results/<run>/judge.jsonl.

  python3 scripts/judge_run.py --run glm_run            # collect (needs LLM_API_KEY) and score
  python3 scripts/judge_run.py --run glm_run --score    # score the stored results/<run>/judge.jsonl only
"""
import argparse, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ASPECTS = ["style", "content", "coordination", "engagement"]
PROMPT = ("In this task, you are given a conversation between A and B, followed by arguments about which speaker has more power "
          "in the conversation. Each argument is followed by a rebuttal written by the other side. Some arguments and rebuttals "
          "may be wrong. Weigh them against the conversation itself and decide which speaker has more power. "
          "Respond with A or B.\n\nConversation:\n{conversation}\n\n{first}\n\n{second}\n\noutput:")


def case(args, side):
    lines = [f"Arguments that {side} has more power:"]
    n = 0
    for a in ASPECTS:
        for reason, rebuttal in zip(args["aspects"][a]["reasons"][side], args["aspects"][a]["rebuttals"][side]):
            n += 1; lines.append(f"{n}. {reason.strip()}\n   Rebuttal: {rebuttal.strip().lstrip('-').strip() or '(none given)'}")
    return "\n".join(lines)


def score(run, name):
    sys.path.insert(0, str(Path(__file__).parent)); from analyze import jsonl, mcnemar
    D = jsonl(ROOT / "data" / "icsi_rebuilt_snippets.jsonl"); gold = {d["id"]: d["professor"] for d in D}
    J = {r["id"]: r for r in jsonl(ROOT / "results" / run / "judge.jsonl")}; ids = [i for i in gold if i in J]
    Z = {z["id"]: ("A" if z["p_A"] >= 0.5 else "B") for z in jsonl(ROOT / "results" / run / "zero_shot.jsonl")}
    a4 = {d["id"]: d["answers"] for d in jsonl(ROOT / "results" / "jev_arm4.jsonl") if d["cond"] == "fixed"}
    g = np.array([gold[i] == "A" for i in ids]); direct = np.array([Z[i] == gold[i] for i in ids])
    jev = np.array([(a4[i]["professor_A"] >= a4[i]["professor_B"]) == (gold[i] == "A") for i in ids])
    pa, pb = np.array([J[i]["A_first"] for i in ids]), np.array([J[i]["B_first"] for i in ids])
    out = {}; print(f"{name}: {len(ids)} of {len(gold)} snippets judged; {name} asked directly {int(direct.sum())}, Jev direct {int(jev.sum())}")
    def row(label, ok):
        w, l, p = mcnemar(ok, direct); jw, jl, jp = mcnemar(ok, jev)
        out[label] = dict(correct=int(ok.sum()), n=len(ids), accuracy=round(100 * float(ok.mean()), 1), vs_model_direct=dict(wins=w, losses=l, mcnemar_p=p), vs_jev_direct=dict(wins=jw, losses=jl, mcnemar_p=jp))
        print(f"  {label:44s} {int(ok.sum()):3d}/{len(ids)} = {100 * ok.mean():5.1f}%   vs {name} direct +{w}/-{l} p={p:.2g}   vs Jev direct +{jw}/-{jl} p={jp:.2g}")
    row("Judge, A's case first", (pa == "A") == g); row("Judge, B's case first", (pb == "A") == g)
    agree = pa == pb
    # when the two orders disagree, the arguments did not settle it: fall back to the model's own direct answer
    row("Judge, both orders (disagreements to direct)", np.where(agree, (pa == "A") == g, direct))
    out["order"] = dict(same_answer_both_orders=int(agree.sum()), answered_first_side=int((pa == "A").sum() + (pb == "B").sum()), of=2 * len(ids),
                        correct_when_orders_agree=int((((pa == "A") == g) & agree).sum()))
    print(f"  same answer in both orders: {int(agree.sum())}/{len(ids)} (correct in {out['order']['correct_when_orders_agree']} of those); "
          f"chose the side presented first in {out['order']['answered_first_side']} of {2 * len(ids)} judgments")
    json.dump(out, open(ROOT / "results" / run / "judge_results.json", "w"), indent=1)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--run", default="glm_run"); ap.add_argument("--name"); ap.add_argument("--limit", type=int)
    ap.add_argument("--score", action="store_true"); a = ap.parse_args()
    stored = ROOT / "results" / a.run / "judge.jsonl"
    if a.score: return score(a.run, a.name or a.run)
    sys.path.insert(0, str(Path(__file__).parent)); import wu_pipeline as W
    ctx = {r["id"]: r for r in map(json.loads, open(ROOT / "work" / "contexts.jsonl")) if r["cond"] == "fixed"}
    args = {r["id"]: r for r in map(json.loads, open(ROOT / "results" / a.run / "arguments.jsonl"))}
    out = ROOT / "work" / a.run / "judge"; out.mkdir(parents=True, exist_ok=True)
    ids = [i for i in ctx if i in args][: a.limit]; todo = [i for i in ids if not (out / f"{i}.json").exists()]
    print(f"[judge] {len(ids) - len(todo)} done, {len(todo)} to do, model {W.LLM_MODEL}", flush=True)

    def one(i):
        conv = W.conversation(ctx[i]["state"]["turns"]); ca, cb = case(args[i], "A"), case(args[i], "B"); rec = {"id": i, "model": W.LLM_MODEL}
        for key, first, second in (("A_first", ca, cb), ("B_first", cb, ca)):
            for attempt in range(3):   # ask again if the answer names neither speaker; never fill one in
                text = W.chat(PROMPT.format(conversation=conv, first=first, second=second)); m = re.search(r"\b([AB])\b", text)
                if m: break
            else: raise RuntimeError(f"snippet {i}: no A or B in the answer after 3 tries: {text[:80]!r}")
            rec[key] = m.group(1); rec[key + "_answer"] = text
        (out / f"{i}.json").write_text(json.dumps(rec)); return i

    failed = 0
    with ThreadPoolExecutor(W.WORKERS if hasattr(W, "WORKERS") else 4) as ex:
        futs = {i: ex.submit(one, i) for i in todo}
        for k, (i, f) in enumerate(futs.items(), 1):
            try: f.result()
            except Exception as e: failed += 1; print(f"[judge] snippet {i} FAILED: {e}", flush=True)
            if k % 10 == 0 or k == len(futs): print(f"[judge] {k}/{len(futs)}", flush=True)
    if failed: sys.exit(f"[judge] {failed} snippets failed; run the same command again to retry them")
    with open(stored, "w") as f:
        for i in ids: f.write((out / f"{i}.json").read_text() + "\n")
    print(f"wrote results/{a.run}/judge.jsonl"); score(a.run, a.name or W.LLM_MODEL)


if __name__ == "__main__":
    main()
