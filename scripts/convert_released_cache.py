#!/usr/bin/env python3
"""Convert the released argument cache (all_obj.pkl) into plain JSON. Needs numpy.

  python3 scripts/convert_released_cache.py      # reads sources/, writes work/snippets.jsonl and work/rules.txt

The pickle is read with a restricted unpickler that only accepts the four record classes of the release and numpy
scalars, so no code from the pickle is executed. Each of the 151 snippets becomes one JSON line:

  id          row index in meeting.csv
  transcript  the released conversation text
  label       the released `power` value (A or B)
  arguments   48 entries: for each aspect, 3 reasons for A, 3 for B, and 6 rebuttals. Fields: id, variable (index of the
              argument's variable in the factor graph), kind, side, aspect, text, target (the reason a rebuttal answers),
              validity and grounding (cached GPT-3.5 log-probabilities)
  relations   48 entries: per aspect, 6 similarity and 6 contradiction scores, divided by 5

Variable layout (98 variables, as in the release's rule file): 0 and 1 are "A has power" and "B has power"; then for
each aspect in the order style, content, coordination, engagement: 6 reasons, 6 rebuttals, 12 relations.

Adapted from quote_power.data in KrishMay05/nlp_research.
"""
import csv, io, json, pickle, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ASPECTS = ("style", "content", "coordination", "engagement")


class Record:
    pass


class CacheReader(pickle.Unpickler):
    def find_class(self, module, name):
        if module == "obj.conversation" and name in {"Conversation", "Aspect", "Reason", "Rebuttal"}: return Record
        if module in {"numpy.core.multiarray", "numpy._core.multiarray"} and name == "scalar": return getattr(np, "_core", None).multiarray.scalar if hasattr(np, "_core") else np.core.multiarray.scalar   # numpy 2 and numpy 1
        if module == "numpy" and name == "dtype": return np.dtype
        raise pickle.UnpicklingError(f"Unsupported global in cache: {module}.{name}")


def main(src=ROOT / "sources", work=ROOT / "work"):
    src, work = Path(src), Path(work); work.mkdir(parents=True, exist_ok=True)
    convs = CacheReader(io.BytesIO((src / "all_obj.pkl").read_bytes())).load()
    labels = list(csv.DictReader(open(src / "meeting.csv", newline="", encoding="utf-8")))
    assert len(convs) == len(labels) == 151, "expected the released 151 snippets"
    with open(work / "snippets.jsonl", "w") as out:
        for k, (conv, lab) in enumerate(zip(convs, labels)):
            assert conv.text == lab["conversation"] and conv.power == lab["power"], f"cache and CSV disagree at row {k}"
            args, rels = [], []
            for ai, aspect in enumerate(ASPECTS):
                obj = getattr(conv, aspect); base = 2 + 24 * ai
                for kind, offset in (("reason", 0), ("rebuttal", 6)):
                    for si, side in enumerate("AB"):
                        for j, arg in enumerate(getattr(obj, f"{kind}_{side.lower()}")):   # rebuttal_a rebuts reason_a
                            var = base + offset + 3 * si + j
                            args.append(dict(id=f"{k}:{var}", variable=var, kind=kind, side=side, aspect=aspect, text=arg.text,
                                             target=f"{k}:{base + 3 * si + j}" if kind == "rebuttal" else None,
                                             validity=float(arg.valid_potential),
                                             grounding=float(getattr(arg, "grounding_potential" if kind == "reason" else "rebuttal_potential"))))
                for j, score in enumerate(obj.similarity_score + obj.contradict_score_a + obj.contradict_score_b):
                    rels.append(dict(variable=base + 12 + j, score=int(score[0][0].strip()) / 5))
            assert len(args) == 48 and len(rels) == 48
            out.write(json.dumps(dict(id=str(k), transcript=conv.text, label=conv.power, arguments=args, relations=rels), ensure_ascii=False) + "\n")
    (work / "rules.txt").write_text((src / "rules.txt").read_text())
    print("wrote", work / "snippets.jsonl", "and", work / "rules.txt")


if __name__ == "__main__":
    main(*sys.argv[1:3])
