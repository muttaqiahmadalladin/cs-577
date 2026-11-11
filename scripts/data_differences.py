#!/usr/bin/env python3
"""List, snippet by snippet, how the released file differs from the rebuilt set. Standard library only.

  python3 scripts/data_differences.py     # needs sources/ and work/ (get_sources.py, build_dataset.py)

Writes
  data/released_vs_rebuilt.csv      one row per released snippet (151 rows)
  report/appendix_table.tex         the same rows as a LaTeX longtable, included by the report's appendix

Columns
  id                 row index in the released meeting.csv
  meeting, start     ICSI meeting ID and start time (s) of the snippet's first corpus segment
  segments, words    corpus segments and words in the snippet
  speakers           number of distinct corpus participants in the snippet
  misplaced          words displayed under the other participant's letter, when each released letter is read as the
                     speaker of the last line of its turns; empty when the letters do not map one-to-one
  released           the released label
  rebuilt            the professor's letter in the rebuilt set; empty when the snippet is not in the rebuilt set
  letters            "kept" when the rebuilt letters follow the released letters, "reassigned" when the first of the
                     two speakers to talk was made A
  note               why a snippet was reassigned or dropped
"""
import csv, json
from pathlib import Path
from build_dataset import load_corpus, load_education, released_turns

ROOT = Path(__file__).resolve().parent.parent


def main():
    src = ROOT / "sources"; M = load_corpus(src); edu = load_education(src)
    rows = json.load(open(ROOT / "work" / "rows.json")); fixed = {o["id"]: o for o in json.load(open(ROOT / "work" / "fixed_index.json"))}
    released = list(csv.DictReader(open(src / "meeting.csv", newline="", encoding="utf-8"))); out = []
    for x, rel in zip(rows, released):
        turns, lines = released_turns(rel["conversation"]); segs = M[x["meeting"]][x["start"]:x["start"] + x["n"]]; spk = [s[1] for s in segs]
        words = sum(len(l.split()) for l in lines); mis = ""
        if x["consistent"] and len(x["profs"]) == 1:
            who = {"A": x["mapA"], "B": x["mapB"]}
            mis = sum(len(lines[k].split()) for letter, idx in turns for k in idx if spk[k] != who[letter])
        f = fixed.get(x["id"]); note = ""
        if len(x["real"]) == 1: note = "one participant only; dropped"
        elif len(x["profs"]) != 1: note = "no single professor; dropped"
        elif len(x["real"]) > 2 and not x["consistent"]: note = "third participant; a letter covers two participants"
        elif len(x["real"]) > 2: note = "third participant"
        elif not x["consistent"]: note = "a letter covers two participants"
        out.append(dict(id=x["id"], meeting=x["meeting"], start=f"{segs[0][0]:.1f}", segments=x["n"], words=words, speakers=len(x["real"]), misplaced=mis,
                        released=rel["power"], rebuilt=f["label"] if f else "", letters=("kept" if f["wu_consistent"] else "reassigned") if f else "", note=note))
    with open(ROOT / "data" / "released_vs_rebuilt.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    with open(ROOT / "report" / "appendix_table.tex", "w") as fh:
        for r in out:
            pct = f"{100 * r['misplaced'] / r['words']:.0f}" if r["misplaced"] != "" else "--"
            changed = r["rebuilt"] and r["rebuilt"] != r["released"]
            fh.write(" & ".join([r["id"], r["meeting"], r["start"], str(r["segments"]), str(r["words"]), str(r["misplaced"]) if r["misplaced"] != "" else "--", pct,
                                 r["released"], (r["rebuilt"] + ("$^\\dagger$" if changed else "")) or "--", r["letters"] or "--", r["note"]]) + " \\\\\n")
    kept = [r for r in out if r["rebuilt"]]; m = [r for r in out if r["misplaced"] != ""]
    print(f"{len(out)} released snippets; {len(kept)} in the rebuilt set; letters kept in {sum(r['letters'] == 'kept' for r in kept)}, reassigned in {sum(r['letters'] == 'reassigned' for r in kept)}; "
          f"label differs in {sum(r['rebuilt'] != r['released'] for r in kept)}; misplaced words {sum(r['misplaced'] for r in m)} of {sum(r['words'] for r in m)} over {len(m)} snippets; "
          f"snippets with any misplaced word: {sum(r['misplaced'] > 0 for r in m)}; with none: {sum(r['misplaced'] == 0 for r in m)}")


if __name__ == "__main__":
    main()
