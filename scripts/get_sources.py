#!/usr/bin/env python3
"""Download every external input into sources/ and verify it by SHA-256. Standard library only.

  python3 scripts/get_sources.py

| File                | Origin                                                                    |
| meeting.csv         | kandicew/social-reasoning @ fed11b6, data/meeting.csv  (151 released snippets and labels)
| all_obj.pkl         | kandicew/social-reasoning @ fed11b6, data/all_obj.pkl  (cached GPT-3.5 arguments and scores)
| rules.txt           | kandicew/social-reasoning @ fed11b6, rules/rules.txt   (factor graph rules)
| icsi_mrt.zip        | ICSI Meeting Corpus, original MRT transcripts (University of Edinburgh mirror)
| icsi_core_nxt.zip   | ICSI Meeting Corpus, core NXT annotations (speakers.xml)

Nothing in sources/ is committed to this repository. A checksum mismatch stops the run: it means an upstream
file changed and every downstream number should be treated as unverified until the difference is understood.
"""
import hashlib, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WU = "https://raw.githubusercontent.com/kandicew/social-reasoning/fed11b69765b4a398ce4a985adedfb65ec3098ab/"
ICSI = "https://groups.inf.ed.ac.uk/ami/ICSICorpusAnnotations/"
SOURCES = {
    "meeting.csv": (WU + "data/meeting.csv", "d405654d402c0e7bca37f0732b6005aff70297aeadf7c6e0fa83c1d4e371b286"),
    "all_obj.pkl": (WU + "data/all_obj.pkl", "e4be3c7c6a3543a77ad07eddde44bfa42f6e58fa6a4bf47df53ea9e894f1e318"),
    "rules.txt": (WU + "rules/rules.txt", "5a88f4a5298fcd1fc8d30736bdcb2fba30cb47cc0bafcb7f68c9d12aea3addde"),
    "icsi_mrt.zip": (ICSI + "ICSI_original_transcripts.zip", "9db98ebdd61a085b4f45f24f46e9c9f6c6f26c3c9cd41643a3b9e74362c85de7"),
    "icsi_core_nxt.zip": (ICSI + "ICSI_core_NXT.zip", "cf4860245b9ca9c9ed11a66e5a74cfea2a99a686a52f7580aa0a6bc2225895a9"),
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()


def main(dest=ROOT / "sources"):
    dest = Path(dest); dest.mkdir(parents=True, exist_ok=True); ok = True
    for name, (url, digest) in SOURCES.items():
        path = dest / name
        if not path.exists():
            print(f"downloading {name}", flush=True)
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=600) as r:
                path.write_bytes(r.read())
        got = sha256(path); match = got == digest; ok &= match
        print(f"{'ok      ' if match else 'MISMATCH'} {name}  {got}")
    if not ok: sys.exit("At least one source does not match its recorded checksum.")
    return dest


if __name__ == "__main__":
    main(*sys.argv[1:2])
