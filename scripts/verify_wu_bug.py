#!/usr/bin/env python3
"""Independent check of speaker attribution in the Wu et al. (NAACL 2025) meeting test set.

Put these three files next to this script, then run:  python3 verify_wu_bug.py
  meeting.csv            https://github.com/kandicew/social-reasoning/blob/main/data/meeting.csv  (Download raw file)
  icsi_mrt.zip           https://groups.inf.ed.ac.uk/ami/ICSICorpusAnnotations/ICSI_original_transcripts.zip
  icsi_core_nxt.zip      https://groups.inf.ed.ac.uk/ami/ICSICorpusAnnotations/ICSI_core_NXT.zip

  python3 verify_wu_bug.py --show 0      # print snippet 0 next to the raw corpus
Standard library only.
"""
import argparse, collections, csv, re, zipfile
from pathlib import Path
HERE = Path(__file__).resolve().parent

def clean(t): return " ".join(re.sub(r"<[^>]+>", "", t).split())

def load_corpus():
    """meeting -> list of (start_time, speaker_id, text, line_number_in_mrt_file), in file order."""
    M = {}
    with zipfile.ZipFile(HERE / "icsi_mrt.zip") as z:
        for name in z.namelist():
            if not re.search(r"transcripts/B\w+\.mrt$", name): continue
            x = z.read(name).decode("latin-1"); segs = []
            for m in re.finditer(r'<Segment\s+StartTime="([\d.]+)"\s+EndTime="[\d.]+"([^>]*)>(.*?)</Segment>', x, re.S):
                p = re.search(r'Participant="(\w+)"', m.group(2)); txt = clean(m.group(3))
                if p and txt: segs.append((m.group(1), p.group(1), txt, x.count("\n", 0, m.start()) + 1))
            M[Path(name).stem] = segs
    return M

def load_roles():
    with zipfile.ZipFile(HERE / "icsi_core_nxt.zip") as z:
        x = z.read("ICSI/speakers.xml").decode("latin-1")
    return dict(re.findall(r'<speaker[^>]*tag="(\w+)">\s*<education[^>]*>([^<]*)<', x))

def wu_lines(conv):
    """Wu's snippet as (displayed label, text, turn index), one entry per non-empty line."""
    out, turn = [], -1
    for ln in conv.split("\n"):
        m = re.match(r"\s*([AB]):\s?(.*)", ln)
        if m: lab, txt, turn = m.group(1), m.group(2), turn + 1
        else: txt = ln
        if clean(txt): out.append((lab, clean(txt), turn))
    return out

def locate(lines, M):
    texts = [t for _, t, _ in lines]
    return [(name, i) for name, segs in M.items() for i in range(len(segs) - len(texts) + 1)
            if segs[i][2] == texts[0] and [s[2] for s in segs[i:i + len(texts)]] == texts]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--show", type=int); args = ap.parse_args()
    M, role = load_corpus(), load_roles()
    rows = list(csv.DictReader(open(HERE / "meeting.csv", newline="", encoding="utf-8")))
    matched = wrong = total = rule_ok = rule_n = h_wu = h_true = h_n = 0
    for k, row in enumerate(rows):
        L = wu_lines(row["conversation"]); hits = locate(L, M)
        if len(hits) != 1: print(f"snippet {k}: {len(hits)} matches in the corpus"); continue
        matched += 1; name, i = hits[0]; segs = M[name][i:i + len(L)]
        if args.show == k:
            print(f"\nSnippet {k}: meeting {name}, starts at {segs[0][0]} s, line {segs[0][3]} of {name}.mrt, Wu's label: {row['power']}\n")
            print(f"{'Wu shows':9s} {'real speaker':13s} {'role':10s} text"); print("-" * 100)
            for (lab, t, _), s in zip(L, segs): print(f"{lab:9s} {s[1]:13s} {role.get(s[1], '?'):10s} {t[:66]}")
            print()
        # which real person does each displayed letter stand for? (speaker of the last line of each turn)
        last = {}
        for (lab, _, turn), s in zip(L, segs): last[turn] = (lab, s[1])
        who = collections.defaultdict(set)
        for lab, sp in last.values(): who[lab].add(sp)
        real = {s[1] for s in segs}; profs = [s for s in real if role.get(s) == "Professor"]
        if not (len(who["A"]) == 1 and len(who["B"]) == 1 and who["A"] != who["B"] and len(profs) == 1): continue
        a, b = next(iter(who["A"])), next(iter(who["B"])); rule_n += 1
        rule_ok += ("A" if a == profs[0] else "B") == row["power"]
        shown = collections.Counter(); true = collections.Counter()
        for (lab, t, _), s in zip(L, segs):
            n = len(t.split()); total += n; wrong += n * (s[1] != (a if lab == "A" else b))
            shown[lab] += n; true["A" if s[1] == a else "B" if s[1] == b else "other"] += n
        h_n += 1
        h_wu += ("A" if shown["A"] >= shown["B"] else "B") == row["power"]
        h_true += ("A" if true["A"] >= true["B"] else "B") == row["power"]
    print(f"1. Snippets found exactly once in the ICSI corpus: {matched} / {len(rows)}")
    print(f"2. Snippets where each letter maps to one real person and one is a professor: {rule_n}")
    print(f"3. Of those, Wu's label equals the letter of the professor: {rule_ok} / {rule_n}")
    print(f"4. Words displayed under the other person's letter: {wrong} / {total} = {100 * wrong / total:.1f}%")
    print(f"5. 'Whoever says more words is the professor', using Wu's displayed letters: {h_wu} / {h_n} = {100 * h_wu / h_n:.1f}%")
    print(f"6. Same rule using the real speakers:                                     {h_true} / {h_n} = {100 * h_true / h_n:.1f}%")

if __name__ == "__main__":
    main()
