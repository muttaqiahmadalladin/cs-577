#!/usr/bin/env python3
"""Label-preserving perturbations and per-class precision/recall metrics for any snippet set (ICSI or SCOTUS).

Addresses two items from the professor's feedback:
  - TODO 2: alter the dialogue text (punctuation/commas, disfluencies, letter swap, speaker tokens, name masking)
    and measure how many predictions flip and how much accuracy/MCC changes.
  - TODO 3: report precision, recall and F1 for BOTH classes (A and B), balanced accuracy, macro-F1, MCC and
    % predicted A alongside overall accuracy.

Usage:
  python3 scripts/perturb_and_metrics.py --data data/scotus_ot2026/snippets_masked.jsonl --perturb no_commas
  python3 scripts/perturb_and_metrics.py --metrics results/glm_run/zero_shot.jsonl --data data/icsi_rebuilt_snippets.jsonl
"""
import argparse, copy, json, math, random, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISFLUENCY = re.compile(r"\b(?:uh|um|er|ah|mm-hmm|uh-huh)\b[,.]?|\b(\w+)-\s+(?=\1\b)", re.I)


def perturb_text(text, kind, rng):
    if kind == "none": return text
    if kind == "no_commas": return " ".join(text.replace(",", " ").split())
    if kind == "no_punct": return " ".join(re.sub(r"[,.;:?!\"'()-]+", " ", text).split())
    if kind == "extra_commas":
        out = []
        for w in text.split():
            out.append(w + ("," if w.isalpha() and len(w) > 3 and rng.random() < 0.15 else ""))
        return " ".join(out)
    if kind == "no_disfluencies":
        x = DISFLUENCY.sub(" ", text)
        x = re.sub(r"\s+--\s+", " ", x)
        x = re.sub(r"\b(\w+)\s+\1\b", r"\1", x, flags=re.I)
        return " ".join(x.split())
    if kind == "lowercase": return text.lower()
    raise ValueError(f"unknown perturbation: {kind}")


def swap_ab(s):
    return {"A": "B", "B": "A"}.get(s, s)


def perturb_snippet(rec, kind, seed=2026):
    """Return a transformed copy of rec. For letter_swap, gold ('professor') and speaker letters are swapped too."""
    r = copy.deepcopy(rec)
    rng = random.Random(f"{seed}:{rec['id']}:{kind}")
    if kind == "letter_swap":
        r["professor"] = swap_ab(r["professor"])
        if "speakers" in r: r["speakers"] = {swap_ab(k): v for k, v in r["speakers"].items()}
        if "roles" in r: r["roles"] = {swap_ab(k): v for k, v in r["roles"].items()}
        for w in ("turns_same_span", "turns_pm15", "turns_pm60"):
            if w in r:
                for t in r[w]:
                    t["speaker"] = swap_ab(t["speaker"])
                    t["text"] = re.sub(r"\bSpeaker ([AB])\b", lambda m: f"Speaker {swap_ab(m.group(1))}", t["text"])
    else:
        for w in ("turns_same_span", "turns_pm15", "turns_pm60"):
            if w in r:
                for t in r[w]: t["text"] = perturb_text(t["text"], kind, rng)
    r["perturbation"] = kind
    return r


PERTURBATIONS = ("none", "no_commas", "extra_commas", "no_punct", "no_disfluencies", "lowercase", "letter_swap")


def classification_metrics(pairs):
    """pairs: [(gold, pred)] with values in {'A', 'B'}. Reports both classes so choice of 'positive' cannot hide bias."""
    pairs = [(g, p) for g, p in pairs if g in ("A", "B") and p in ("A", "B")]
    n = len(pairs)
    if not n: return {"n": 0}
    def prf(pos):
        tp = sum(g == pos and p == pos for g, p in pairs)
        fp = sum(g != pos and p == pos for g, p in pairs)
        fn = sum(g == pos and p != pos for g, p in pairs)
        pr = tp / (tp + fp) if tp + fp else None
        rc = tp / (tp + fn) if tp + fn else None
        f1 = (2 * pr * rc / (pr + rc)) if (pr and rc) else 0.0
        return {"precision": pr, "recall": rc, "f1": f1, "support": tp + fn}
    a, b = prf("A"), prf("B")
    tp = sum(g == "A" and p == "A" for g, p in pairs); tn = sum(g == "B" and p == "B" for g, p in pairs)
    fp = sum(g == "B" and p == "A" for g, p in pairs); fn = sum(g == "A" and p == "B" for g, p in pairs)
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    bal = ((a["recall"] or 0.0) + (b["recall"] or 0.0)) / 2
    return {
        "n": n, "accuracy": (tp + tn) / n, "balanced_accuracy": bal,
        "macro_f1": (a["f1"] + b["f1"]) / 2, "mcc": (tp * tn - fp * fn) / denom if denom else 0.0,
        "predicted_A_rate": (tp + fp) / n, "gold_A_rate": (tp + fn) / n,
        "class_A": a, "class_B": b, "confusion": {"tp_A": tp, "fp_A": fp, "fn_A": fn, "tn_B": tn},
    }


def heuristic_baselines(rows, window="turns_same_span"):
    """Word-count, turn-count, question-count and always-A baselines on any snippet list."""
    out = {}
    for name, fn in (
        ("always_A", lambda ts: "A"),
        ("more_words", lambda ts: "A" if sum(len(t["text"].split()) for t in ts if t["speaker"] == "A") >=
                                       sum(len(t["text"].split()) for t in ts if t["speaker"] == "B") else "B"),
        ("more_questions", lambda ts: "A" if sum(t["text"].count("?") for t in ts if t["speaker"] == "A") >=
                                           sum(t["text"].count("?") for t in ts if t["speaker"] == "B") else "B"),
        ("shorter_turns", lambda ts: "A" if sum(len(t["text"].split()) for t in ts if t["speaker"] == "A") <=
                                          sum(len(t["text"].split()) for t in ts if t["speaker"] == "B") else "B"),
    ):
        out[name] = classification_metrics([(r["professor"], fn(r[window])) for r in rows])
    return out


def parse_answer(rec):
    if rec.get("prediction") in ("A", "B"): return rec["prediction"]
    a = str(rec.get("answer", "")).strip()
    if a in ("A", "B"): return a
    m = re.search(r"\b([AB])\b", a)
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "scotus_ot2026" / "snippets_masked.jsonl")
    ap.add_argument("--perturb", choices=PERTURBATIONS)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--metrics", type=Path, help="JSONL file of model predictions (with id and answer/prediction)")
    ap.add_argument("--baselines", action="store_true", help="print heuristic baseline metrics on --data")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.data, encoding="utf-8")]
    if a.perturb:
        pert = [perturb_snippet(r, a.perturb) for r in rows]
        body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in pert)
        if a.out: a.out.write_text(body, encoding="utf-8")
        else: print(f"perturbed {len(pert)} rows with {a.perturb}; sample turn: {pert[0]['turns_same_span'][0]['text'][:140]}")
    if a.baselines:
        for split in ("all", "dev", "test"):
            sub = rows if split == "all" else [r for r in rows if r.get("split") == split]
            if sub: print(split, json.dumps({k: round(v["accuracy"], 3) for k, v in heuristic_baselines(sub).items()}))
    if a.metrics:
        gold = {r["id"]: r["professor"] for r in rows}
        preds = [json.loads(l) for l in open(a.metrics, encoding="utf-8")]
        pairs = [(gold[p["id"]], parse_answer(p)) for p in preds if p.get("id") in gold]
        print(json.dumps(classification_metrics(pairs), indent=2))


if __name__ == "__main__":
    main()
