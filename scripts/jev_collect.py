#!/usr/bin/env python3
"""Collect TypeSafe Jev judgments for the CS 577 power-relations project.

Standard library only. Reads snippets.jsonl (151 ICSI snippets + Wu's cached GPT-3.5 arguments),
writes jev_arm1.jsonl (direct + atomic System 1 judgments) and jev_arm2.jsonl (argument scores).
Resumable: finished snippets are skipped. Every request payload is saved in payloads/.

  export TYPESAFE_API_KEY=...        # never put the key in this file
  python3 jev_collect.py --limit 3   # probe three snippets first
  python3 jev_collect.py             # all 151
"""
import argparse, json, os, re, sys, time, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
URL = os.environ.get("TYPESAFE_URL", "https://api.typesafe.ai/v1/systemone")
MODEL = os.environ.get("JEV_MODEL", "jev-latest")   # the resolved version is recorded per response
OTHER = {"A": "B", "B": "A"}

# ---- all question wording lives here (fixed before any labels were looked at) -------------------
SETTING = ("Excerpt from a university research group meeting. Exactly one of the two speakers, "
           "A and B, is a professor and the other is a student.")
# name -> (question about speaker X, expected sign for 'X is the professor'; used only in analysis)
ATOMIC = {
    "professor":     ("Is speaker {x} the professor?", +1),
    "more_power":    ("Does speaker {x} hold more power in this conversation than speaker {o}?", +1),
    "evaluates":     ("Does speaker {x} evaluate speaker {o}'s work?", +1),
    "directs":       ("Does speaker {x} tell speaker {o} what to do?", +1),
    "asks_status":   ("Does speaker {x} ask about the status of speaker {o}'s work?", +1),
    "picks_topic":   ("Does speaker {x} choose what the conversation is about?", +1),
    "explains_own":  ("Is speaker {x} explaining their own work to speaker {o}?", -1),
    "seeks_assent":  ("Does speaker {x} seek speaker {o}'s agreement?", -1),
    "unsure":        ("Does speaker {x} sound unsure?", -1),
    "backchannels":  ("Are speaker {x}'s turns mostly brief acknowledgements?", -1),
}
# Arm 3: Wu's factor graph rebuilt from typed statements. Three statements per Wu aspect, each asked
# about both speakers; a yes is evidence that speaker {x} has the higher status.
TYPED = {
    "style":        ["Does speaker {x} speak assertively?",
                     "Does speaker {x} state things plainly, without hedging?",
                     "Is speaker {x} blunt with speaker {o}?"],
    "content":      ["Does speaker {x} evaluate speaker {o}'s work?",
                     "Does speaker {x} give speaker {o} advice?",
                     "Does speaker {x} ask speaker {o} to justify something?"],
    "coordination": ["Does speaker {x} steer the conversation?",
                     "Does speaker {x} set the tone of the conversation?",
                     "Does speaker {o} follow speaker {x}'s lead?"],
    "engagement":   ["Does speaker {x} participate more actively than speaker {o}?",
                     "Does speaker {x} introduce new points?",
                     "Does speaker {x} interrupt speaker {o}?"],
}
Q_GROUNDED = "Is this claim supported by what the speakers say in `turns`?\n\nClaim: {text}"
Q_VALID = ("If this claim were true, would it be evidence that speaker {s} holds more power than "
           "speaker {o}?\n\nClaim: {text}")
Q_REB_VALID = ("If this claim were true, would it be evidence against speaker {s} holding more power "
               "than speaker {o}?\n\nClaim: {text}")
Q_ANSWERS = "Does the rebuttal directly counter the reason?\n\nReason: {reason}\n\nRebuttal: {text}"
# -------------------------------------------------------------------------------------------------

def turns(transcript):
    parts = re.split(r"(?m)^\s*([AB]):", transcript)
    return [{"speaker": parts[i], "text": " ".join(parts[i + 1].split())} for i in range(1, len(parts) - 1, 2)]

def state(row):
    return {"setting": SETTING, "turns": turns(row["transcript"])}

def arm1_questions(row):
    q = {}
    for name, (text, _) in ATOMIC.items():
        for x in "AB":
            q[f"{name}_{x}"] = {"type": "noul", "instructions": text.format(x=x, o=OTHER[x])}
    return q

def arm2_questions(row):
    q, by_id = {}, {a["id"]: a for a in row["arguments"]}
    for a in row["arguments"]:
        v, s = a["variable"], a["side"]
        q[f"g{v}"] = {"type": "noul", "instructions": Q_GROUNDED.format(text=a["text"])}
        if a["kind"] == "reason":
            q[f"v{v}"] = {"type": "noul", "instructions": Q_VALID.format(s=s, o=OTHER[s], text=a["text"])}
        else:
            q[f"v{v}"] = {"type": "noul", "instructions": Q_REB_VALID.format(s=s, o=OTHER[s], text=a["text"])}
            q[f"r{v}"] = {"type": "noul", "instructions": Q_ANSWERS.format(reason=by_id[a["target"]]["text"], text=a["text"])}
    return q

def arm3_questions(row):
    q = {}
    for aspect, items in TYPED.items():
        for j, text in enumerate(items):
            for x in "AB":
                q[f"{aspect}{j}_{x}"] = {"type": "noul", "instructions": text.format(x=x, o=OTHER[x])}
    return q

ICSI = {"icsi_mrt.zip": "https://groups.inf.ed.ac.uk/ami/ICSICorpusAnnotations/ICSI_original_transcripts.zip",
        "icsi_core_nxt.zip": "https://groups.inf.ed.ac.uk/ami/ICSICorpusAnnotations/ICSI_core_NXT.zip"}
def fetch_icsi():
    for name, url in ICSI.items():
        dest = HERE / name
        if dest.exists() and dest.stat().st_size > 1_000_000: print(f"{name}: already here"); continue
        print(f"downloading {name} ...", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
            while chunk := r.read(1 << 20): f.write(chunk)
        print(f"{name}: {dest.stat().st_size / 1e6:.1f} MB")

def arm4_questions(_row=None):
    """Direct questions plus the typed statements, for the corrected-speaker and longer-context states."""
    q = {}
    for name in ("professor", "more_power"):
        for x in "AB":
            q[f"{name}_{x}"] = {"type": "noul", "instructions": ATOMIC[name][0].format(x=x, o=OTHER[x])}
    q.update(arm3_questions(None))
    return q

def run_arm4(key, limit):
    recs = [json.loads(l) for l in (HERE / "contexts.jsonl").read_text().splitlines() if l.strip()]
    if limit: recs = recs[: limit * 3]
    out = HERE / "jev_arm4.jsonl"
    seen = {(json.loads(l)["id"], json.loads(l)["cond"]) for l in out.read_text().splitlines() if l.strip()} if out.exists() else set()
    for i, r in enumerate(recs):
        if (r["id"], r["cond"]) in seen: continue
        payload = {"model": MODEL, "state": r["state"], "questions": arm4_questions()}
        (HERE / "payloads" / f"arm4_{r['id']}_{r['cond']}.json").write_text(json.dumps(payload))
        resp = call(payload, key)
        missing = set(payload["questions"]) - set(resp.get("answers", {}))
        if missing: raise SystemExit(f"{r['id']}/{r['cond']}: {len(missing)} questions unanswered")
        with out.open("a") as f:
            f.write(json.dumps({"id": r["id"], "cond": r["cond"], "model": resp.get("model"), "usage": resp.get("usage"),
                                "answers": {k: a["noul"] for k, a in resp["answers"].items()}}) + "\n")
        print(f"arm 4: {i + 1}/{len(recs)} ({r['id']} {r['cond']})", flush=True)

def call(payload, key, tries=6):
    body = json.dumps(payload).encode()
    for attempt in range(tries):
        req = urllib.request.Request(URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json",
            "User-Agent": "cs577-jev-collect/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:800]
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(min(60, 2 ** attempt * 2)); continue
            raise SystemExit(f"HTTP {e.code} from TypeSafe: {detail}")   # a failed call is an error, never an answer
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < tries - 1: time.sleep(min(60, 2 ** attempt * 2)); continue
            raise SystemExit(f"Network error reaching {URL}: {e}")

def done_ids(path):
    return {json.loads(l)["id"] for l in path.read_text().splitlines() if l.strip()} if path.exists() else set()

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--arms", default="1,2,3"); ap.add_argument("--fetch-icsi", action="store_true"); args = ap.parse_args()
    if args.fetch_icsi: return fetch_icsi()
    rows = [json.loads(l) for l in (HERE / "snippets.jsonl").read_text().splitlines() if l.strip()][: args.limit]
    builders = {"1": arm1_questions, "2": arm2_questions, "3": arm3_questions}
    if args.dry_run:
        chars = 0
        for arm in args.arms.split(","):
            for r in rows:
                chars += len(json.dumps({"state": state(r), "questions": builders[arm](r)}))
        print(f"{len(rows)} snippets, arms {args.arms}: ~{chars // 4:,} input tokens, ~${chars / 4 / 1e6 * 0.042:.2f} at $0.042/M")
        print(json.dumps({"model": MODEL, "state": state(rows[0]), "questions": dict(list(arm1_questions(rows[0]).items())[:2])}, indent=1)[:1500])
        return
    key = os.environ.get("TYPESAFE_API_KEY") or sys.exit("Set TYPESAFE_API_KEY first.")
    (HERE / "payloads").mkdir(exist_ok=True)
    for arm in args.arms.split(","):
        if arm == "4": run_arm4(key, args.limit); continue
        out = HERE / f"jev_arm{arm}.jsonl"; seen = done_ids(out)
        for i, r in enumerate(rows):
            if r["id"] in seen: continue
            payload = {"model": MODEL, "state": state(r), "questions": builders[arm](r)}
            (HERE / "payloads" / f"arm{arm}_{r['id']}.json").write_text(json.dumps(payload))
            resp = call(payload, key)
            missing = set(payload["questions"]) - set(resp.get("answers", {}))
            if missing: raise SystemExit(f"Snippet {r['id']}: {len(missing)} questions unanswered, e.g. {sorted(missing)[:3]}")
            rec = {"id": r["id"], "model": resp.get("model"), "usage": resp.get("usage"),
                   "answers": {k: a["noul"] for k, a in resp["answers"].items()}}
            with out.open("a") as f: f.write(json.dumps(rec) + "\n")
            print(f"arm {arm}: {i + 1}/{len(rows)} (snippet {r['id']}, model {rec['model']})", flush=True)
    print("Done.")

if __name__ == "__main__":
    main()
