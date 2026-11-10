#!/usr/bin/env python3
"""Build the ICSI-rebuilt snippet set from its two public sources. Standard library only.

Sources (put them in --sources, or pass --download to fetch them):
  meeting.csv         kandicew/social-reasoning at commit fed11b6: the 151 released snippets and labels
  icsi_mrt.zip        ICSI original MRT transcripts (segment text, participant ID, timing)
  icsi_core_nxt.zip   ICSI core NXT annotations (speakers.xml: education level per participant)

Steps:
  1. Parse every MRT transcript into segments (start time, participant, text with markup removed).
  2. Locate each released snippet: its non-empty lines must equal a run of consecutive segment texts
     in exactly one meeting. All 151 are found exactly once.
  3. Take speakers from the corpus participant IDs of those segments. The professor is the single
     participant whose education field is "Professor". Snippets without exactly one professor and
     at least two speakers are dropped (one snippet).
  4. Assign letters. Where the released file's letters map one-to-one onto the two participants
     (each letter read as the speaker of the last line of its turns), keep that mapping so labels stay
     comparable. Otherwise the first of the two speakers to talk is A. Further participants are C, D, ...
  5. Merge consecutive segments by the same participant into turns, for three windows: the snippet's
     own segments, and 15 or 60 extra corpus segments on each side.

Outputs:
  <out>/icsi_rebuilt_snippets.jsonl   the dataset (see docs/DATA.md for the schema)
  <work>/rows.json, fixed_index.json, contexts.jsonl   intermediate files used by the analysis scripts

  python3 scripts/build_dataset.py --download            # fetch sources, build
  python3 scripts/build_dataset.py --check               # rebuild and compare with the committed dataset
"""
import argparse, collections, csv, json, re, sys, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URLS = {
    "meeting.csv": "https://raw.githubusercontent.com/kandicew/social-reasoning/fed11b69765b4a398ce4a985adedfb65ec3098ab/data/meeting.csv",
    "icsi_mrt.zip": "https://groups.inf.ed.ac.uk/ami/ICSICorpusAnnotations/ICSI_original_transcripts.zip",
    "icsi_core_nxt.zip": "https://groups.inf.ed.ac.uk/ami/ICSICorpusAnnotations/ICSI_core_NXT.zip",
}
SETTING2 = "Excerpt from a university research group meeting. Exactly one of the two speakers, A and B, is a professor and the other is a student."
SETTING3 = SETTING2 + " Other people in the meeting are labeled C, D, and so on."
WINDOWS = (("same_span", "fixed", 0), ("pm15", "ctx15", 15), ("pm60", "ctx60", 60))


def clean(t):
    """Remove MRT markup such as <VocalSound/> and <Comment/> and collapse whitespace."""
    return " ".join(re.sub(r"<[^>]+>", "", t).split())


def load_corpus(src):
    """meeting -> [(start_time, participant, text)] in file order, skipping segments with no words."""
    M = {}
    with zipfile.ZipFile(src / "icsi_mrt.zip") as z:
        for name in sorted(z.namelist()):
            if not re.search(r"transcripts/B\w+\.mrt$", name): continue
            x = z.read(name).decode("latin-1"); segs = []
            for m in re.finditer(r'<Segment\s+StartTime="([\d.]+)"\s+EndTime="[\d.]+"([^>]*)>(.*?)</Segment>', x, re.S):
                p = re.search(r'Participant="(\w+)"', m.group(2)); txt = clean(m.group(3))
                if p and txt: segs.append((float(m.group(1)), p.group(1), txt))
            M[Path(name).stem] = segs
    return M


def load_education(src):
    with zipfile.ZipFile(src / "icsi_core_nxt.zip") as z:
        x = z.read("ICSI/speakers.xml").decode("latin-1")
    return dict(re.findall(r'<speaker[^>]*tag="(\w+)">\s*<education[^>]*>([^<]*)<', x))


def released_turns(conv):
    """[[letter, [line index, ...]], ...] for the released text; lines are its non-empty lines."""
    turns, lines = [], []
    for ln in conv.split("\n"):
        m = re.match(r"\s*([AB]):\s?(.*)", ln); txt = m.group(2) if m else ln
        if m: turns.append([m.group(1), []])
        if clean(txt): turns[-1][1].append(len(lines)); lines.append(clean(txt))
    return turns, lines


def locate(lines, M):
    return [(name, i) for name, segs in M.items() for i in range(len(segs) - len(lines) + 1)
            if segs[i][2] == lines[0] and [s[2] for s in segs[i:i + len(lines)]] == lines]


def window(M, o, k):
    S = M[o["meeting"]]; lo = max(0, o["start"] - k); hi = min(len(S), o["start"] + o["n"] + k); let = dict(o["letters"]); T = []
    for _, sp, tx in S[lo:hi]:
        if sp not in let: let[sp] = [c for c in "CDEFGHIJKLMN" if c not in let.values()][0]
        if T and T[-1]["speaker"] == let[sp]: T[-1]["text"] += " " + tx
        else: T.append({"speaker": let[sp], "text": tx})
    return T


def build(src):
    M, edu = load_corpus(src), load_education(src)
    released = list(csv.DictReader(open(src / "meeting.csv", newline="", encoding="utf-8")))
    rows, fixed = [], []
    for k, row in enumerate(released):
        turns, lines = released_turns(row["conversation"]); hits = locate(lines, M)
        if len(hits) != 1: sys.exit(f"snippet {k}: found {len(hits)} times in the corpus")
        name, i = hits[0]; spk = [s[1] for s in M[name][i:i + len(lines)]]
        assign = collections.defaultdict(set)
        for letter, idx in turns:
            if idx: assign[letter].add(spk[idx[-1]])
        a = next(iter(assign["A"]), None); b = next(iter(assign["B"]), None)
        one_to_one = len(assign["A"]) == 1 and len(assign["B"]) == 1 and a != b
        real = list(dict.fromkeys(spk)); profs = [s for s in real if edu.get(s) == "Professor"]
        rows.append(dict(id=str(k), meeting=name, start=i, n=len(lines), mapA=a, mapB=b, consistent=one_to_one, profs=profs, real=sorted(real)))
        if len(profs) != 1 or len(real) < 2: continue
        prof = profs[0]
        if one_to_one: let = {a: "A", b: "B"}
        else:
            other = [s for s in real if s != prof][0]; first = [s for s in real if s in (prof, other)][0]
            let = {first: "A", (other if first == prof else prof): "B"}
        for s in real:
            if s not in let: let[s] = "CDEFGH"[len(let) - 2]
        fixed.append(dict(id=str(k), meeting=name, start=i, n=len(lines), letters=let, label=let[prof], wu_label=row["power"], wu_consistent=one_to_one))
    data, contexts = [], []
    for o in fixed:
        rec = dict(id=o["id"], meeting=o["meeting"], start_time=M[o["meeting"]][o["start"]][0], n_segments=o["n"],
                   speakers={v: k for k, v in o["letters"].items()}, professor=o["label"], released_label=o["wu_label"],
                   letters_from_released=o["wu_consistent"])
        for field, cond, k in WINDOWS:
            T = window(M, o, k); rec["turns_" + field] = T
            contexts.append(dict(id=o["id"], cond=cond, state=dict(setting=SETTING3 if any(t["speaker"] not in "AB" for t in T) else SETTING2, turns=T)))
        data.append(rec)
    return rows, fixed, data, contexts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", default=str(ROOT / "sources")); ap.add_argument("--out", default=str(ROOT / "data"))
    ap.add_argument("--work", default=str(ROOT / "work")); ap.add_argument("--download", action="store_true"); ap.add_argument("--check", action="store_true")
    args = ap.parse_args(); src, out, work = Path(args.sources), Path(args.out), Path(args.work)
    if args.download:
        src.mkdir(parents=True, exist_ok=True)
        for name, url in URLS.items():
            if (src / name).exists(): continue
            print("downloading", name, flush=True)
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=300) as r: (src / name).write_bytes(r.read())
    rows, fixed, data, contexts = build(src)
    text = "".join(json.dumps(d) + "\n" for d in data)
    print(f"released snippets located: {len(rows)}; rebuilt set: {len(data)}; professor is A in {sum(d['professor'] == 'A' for d in data)}; "
          f"labels equal to released: {sum(d['professor'] == d['released_label'] for d in data)}; letters kept from released: {sum(d['letters_from_released'] for d in data)}")
    if args.check:
        same = (out / "icsi_rebuilt_snippets.jsonl").read_text() == text
        print("committed dataset reproduced exactly" if same else "MISMATCH with committed dataset"); sys.exit(0 if same else 1)
    out.mkdir(parents=True, exist_ok=True); work.mkdir(parents=True, exist_ok=True)
    (out / "icsi_rebuilt_snippets.jsonl").write_text(text)
    json.dump(rows, open(work / "rows.json", "w")); json.dump(fixed, open(work / "fixed_index.json", "w"))
    (work / "contexts.jsonl").write_text("".join(json.dumps(c) + "\n" for c in contexts))
    print("wrote", out / "icsi_rebuilt_snippets.jsonl", "and work files in", work)


if __name__ == "__main__":
    main()
