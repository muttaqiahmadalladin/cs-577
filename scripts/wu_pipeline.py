#!/usr/bin/env python3
"""Run the Wu et al. (NAACL 2025) argument pipeline on the rebuilt snippets.

Stages (all resumable; rerun the same command after an interruption):
  gen     an LLM writes aspect summaries, 3 reasons per speaker and one rebuttal per reason,
          using Wu's own prompt templates (downloaded from their repository at a pinned commit)
  zero    the same LLM answers "who has more power" from the conversation alone
  jev     TypeSafe Jev scores every argument and every relation (one call per snippet)
  llm     optional: the LLM scores arguments with yes/no token probabilities, as in the paper

Environment:
  LLM_API_KEY       key for any OpenAI-compatible chat API
  LLM_BASE_URL      default https://api.openai.com/v1   (Purdue: https://genai.rcac.purdue.edu/api)
  LLM_MODEL         default gpt-3.5-turbo               (Purdue: gemma4:26b-a4b)
  LLM_WORKERS       parallel snippets, default 6        (Purdue: 1)
  LLM_MIN_INTERVAL  seconds between calls, default 0    (Purdue: 3.2)
  LLM_LOGPROBS      1 (default) asks for token probabilities; 0 for models that do not return them or that
                    always reason before answering (the printed answer is used instead)
  LLM_MAX_TOKENS    output cap when LLM_LOGPROBS=0 (default: none)
  LLM_EXTRA_JSON    JSON object merged into every chat request, for example '{"reasoning_effort": "low"}'
  TYPESAFE_API_KEY  for the jev stage

  python3 wu_pipeline.py --stages gen,zero,jev            # main run
  python3 wu_pipeline.py --stages gen,zero,jev,llm        # also Wu's own scoring (144 more calls per snippet)
  python3 wu_pipeline.py --limit 2 --stages gen,zero,jev  # probe two snippets first
  python3 wu_pipeline.py --out glm_run --stages gen,zero,jev   # keep a second model's run in its own folder (see run_glm.sh)
Standard library only.
"""
import argparse, ast, json, math, os, re, sys, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "work"   # contexts.jsonl from build_dataset.py; all outputs go to work/wu_run/
OUT = HERE / "wu_run"
WU_RAW = "https://raw.githubusercontent.com/kandicew/social-reasoning/fed11b69765b4a398ce4a985adedfb65ec3098ab/"
TEMPLATES = ["summary_template", "reason_template", "rebuttal_template", "validation_template", "grounding_template",
             "validation_rebuttal_template", "grounding_rebuttal_template", "same_likert", "contradict_likert"]
ASPECTS = ["style", "content", "coordination", "engagement"]
OTHER = {"A": "B", "B": "A"}
LLM_BASE = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-3.5-turbo")
WORKERS = int(os.environ.get("LLM_WORKERS", "6"))
MIN_INTERVAL = float(os.environ.get("LLM_MIN_INTERVAL", "0"))
USE_LOGPROBS = os.environ.get("LLM_LOGPROBS", "1") != "0"
MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "0"))
EXTRA = json.loads(os.environ.get("LLM_EXTRA_JSON", "{}"))
JEV_URL = os.environ.get("TYPESAFE_URL", "https://api.typesafe.ai/v1/systemone")
JEV_MODEL = os.environ.get("JEV_MODEL", "jev-latest")

ZERO_SHOT = ("In this task, you are given a conversation between A and B. Decide which speaker has more power "
             "in the conversation. Respond with A or B.\n\nConversation:\n{conversation}\n\noutput:")
# Jev question wording (same as the earlier run on the released arguments)
Q_GROUNDED = "Is this claim supported by what the speakers say in `turns`?\n\nClaim: {text}"
Q_VALID = "If this claim were true, would it be evidence that speaker {s} holds more power than speaker {o}?\n\nClaim: {text}"
Q_REB_VALID = "If this claim were true, would it be evidence against speaker {s} holding more power than speaker {o}?\n\nClaim: {text}"
Q_ANSWERS = "Does the rebuttal directly counter the reason?\n\nReason: {reason}\n\nRebuttal: {text}"
Q_SIMILAR = "Do these two claims describe the same behavior with the same reasoning?\n\nClaim 1: {a}\n\nClaim 2: {b}"
Q_CONTRA = "Do these two claims contradict each other?\n\nClaim 1: {a}\n\nClaim 2: {b}"

_lock = threading.Lock(); _last = [0.0]


def http_json(url, payload, key, tries=7):
    body = json.dumps(payload).encode()
    for attempt in range(tries):
        if MIN_INTERVAL and "typesafe" not in url:
            with _lock:
                wait = MIN_INTERVAL - (time.monotonic() - _last[0])
                if wait > 0: time.sleep(wait)
                _last[0] = time.monotonic()
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "cs577-wu-pipeline/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:600]
            if e.code in (400, 408, 409, 429, 500, 502, 503, 504) and attempt < tries - 1 and not (e.code == 400 and "model" in detail.lower()):
                time.sleep(min(90, 2 ** attempt * 2)); continue
            raise RuntimeError(f"HTTP {e.code} from {url}: {detail}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < tries - 1: time.sleep(min(90, 2 ** attempt * 2)); continue
            raise RuntimeError(f"Network error reaching {url}: {e}")


def chat(prompt, logprobs=False):
    payload = {"model": LLM_MODEL, "messages": [{"role": "user", "content": prompt}]}
    if logprobs and USE_LOGPROBS: payload.update(logprobs=True, top_logprobs=5, max_tokens=4, temperature=0)
    elif MAX_TOKENS: payload["max_tokens"] = MAX_TOKENS
    payload.update(EXTRA)
    for attempt in range(3):   # a reasoning model can spend its whole budget thinking and return no answer; retry, never fill in
        resp = http_json(LLM_BASE + "/chat/completions", payload, os.environ["LLM_API_KEY"])
        choice = resp["choices"][0]; text = (choice["message"].get("content") or "").strip()
        if text: break
    else: raise RuntimeError(f"empty answer from {LLM_MODEL} three times (finish_reason {choice.get('finish_reason')}); raise LLM_MAX_TOKENS")
    if not logprobs: return text
    lp = (choice.get("logprobs") or {}).get("content") or []
    top = {t["token"].strip().lower(): math.exp(t["logprob"]) for t in (lp[0]["top_logprobs"] if lp else [])}
    return text, top


def prob(top, text, yes, no):
    """P(yes) from first-token probabilities; falls back to the printed answer if the API gives none."""
    y = sum(p for t, p in top.items() if t == yes); n = sum(p for t, p in top.items() if t == no)
    if y + n > 0: return y / (y + n)
    m = re.search(rf"\b({re.escape(yes)}|{re.escape(no)})\b", text.strip().lower())   # first standalone yes/no (or A/B) in the printed answer
    return 0.5 if not m else 0.99 if m.group(1) == yes else 0.01


def load_templates():
    cache = OUT / "templates.json"
    if cache.exists(): return json.loads(cache.read_text())
    def get(path):
        with urllib.request.urlopen(urllib.request.Request(WU_RAW + path, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
            return r.read().decode()
    T = {n: get(f"template/{n}.txt") for n in TEMPLATES}
    m = re.search(r"definition\s*=\s*(\{.*?\})\s*\n\s*\n", get("code/prompts.py"), re.S)
    T["definition"] = ast.literal_eval(m.group(1))
    cache.write_text(json.dumps(T)); return T


def conversation(turns):
    return "\n".join(f"{t['speaker']}: {t['text']}" for t in turns) + "\n"


def parse_reasons(text):
    out = []
    for ln in text.splitlines():
        s = ln.strip().lstrip("-").strip().strip('"').strip("\u201c\u201d").strip()
        s = re.sub(r"^\d+[.)]\s*", "", s).strip('"').strip()
        if len(s) > 8: out.append(s)
    return out[:3]


def clean_one(text):
    s = text.strip().splitlines()[0] if text.strip() else ""
    return s.lstrip("-").strip().strip('"').strip("\u201c\u201d").strip() or text.strip()


def gen_snippet(rec, T):
    conv = conversation(rec["state"]["turns"]); out = {"id": rec["id"], "model": LLM_MODEL, "aspects": {}}
    for a in ASPECTS:
        summ = chat(T["summary_template"].format(aspect=a, aspect_definition=T["definition"][a], conversation=conv))
        if not summ.startswith(a + " of A:"): summ = a + " of A:\n" + summ
        block = {"summary": summ, "reasons": {}, "rebuttals": {}}
        for s in "AB":
            for attempt in range(3):
                rs = parse_reasons(chat(T["reason_template"].format(high=s, low=OTHER[s], summary=summ)))
                if len(rs) == 3: break
            if len(rs) != 3: raise RuntimeError(f"snippet {rec['id']} {a} {s}: got {len(rs)} reasons after 3 tries")
            block["reasons"][s] = rs
            # the rebuttal argues for the other speaker, against this reason
            block["rebuttals"][s] = [clean_one(chat(T["rebuttal_template"].format(high=s, low=OTHER[s], conversation=conv, reason=r))) for r in rs]
        out["aspects"][a] = block
    return out


def zero_snippet(rec):
    text, top = chat(ZERO_SHOT.format(conversation=conversation(rec["state"]["turns"])), logprobs=True)
    m = re.search(r"\b([AB])\b", text)   # case-sensitive, so the article "a" is not read as an answer
    p_a = prob(top, text, "a", "b") if top else 0.5 if not m else 0.99 if m.group(1) == "A" else 0.01
    return {"id": rec["id"], "model": LLM_MODEL, "answer": text, "p_A": p_a}


def llm_score_snippet(rec, gen, T):
    conv = conversation(rec["state"]["turns"]); out = {"id": rec["id"], "model": LLM_MODEL, "aspects": {}}
    yn = lambda p: prob(*reversed(chat(p, logprobs=True)), "yes", "no")
    def likert(p):
        text, top = chat(p, logprobs=True)
        m = re.search(r"[1-5]", text); return int(m.group()) if m else 3
    for a in ASPECTS:
        g = gen["aspects"][a]; b = {"reason": {}, "rebuttal": {}}
        for s in "AB":
            b["reason"][s] = [[yn(T["validation_template"].format(high=s, low=OTHER[s], reason=r)),
                               yn(T["grounding_template"].format(high=s, low=OTHER[s], conversation=conv, reason=r))] for r in g["reasons"][s]]
            # as intended in the paper: the rebuttal is judged against its reason, and grounded on its own text
            b["rebuttal"][s] = [[yn(T["validation_rebuttal_template"].format(high=OTHER[s], low=s, reason=r, rebuttal=x)),
                                 yn(T["grounding_rebuttal_template"].format(conversation=conv, reason=x))] for r, x in zip(g["reasons"][s], g["rebuttals"][s])]
        ra, rb = g["reasons"]["A"], g["reasons"]["B"]
        b["similar"] = [likert(T["same_likert"].format(description_a=ra[i], description_b=rb[j])) / 5 for i in range(3) for j in range(i, 3)]
        b["contra_A"] = [likert(T["contradict_likert"].format(description_a=ra[i], description_b=ra[j])) / 5 for i, j in ((0, 1), (0, 2), (1, 2))]
        b["contra_B"] = [likert(T["contradict_likert"].format(description_a=rb[i], description_b=rb[j])) / 5 for i, j in ((0, 1), (0, 2), (1, 2))]
        out["aspects"][a] = b
    return out


def jev_questions(gen):
    q = {}
    for a in ASPECTS:
        g = gen["aspects"][a]
        for s in "AB":
            for j, r in enumerate(g["reasons"][s]):
                x = g["rebuttals"][s][j]
                q[f"{a}|rv|{s}{j}"] = {"type": "noul", "instructions": Q_VALID.format(s=s, o=OTHER[s], text=r)}
                q[f"{a}|rg|{s}{j}"] = {"type": "noul", "instructions": Q_GROUNDED.format(text=r)}
                q[f"{a}|bv|{s}{j}"] = {"type": "noul", "instructions": Q_REB_VALID.format(s=s, o=OTHER[s], text=x)}
                q[f"{a}|bg|{s}{j}"] = {"type": "noul", "instructions": Q_GROUNDED.format(text=x)}
                q[f"{a}|ba|{s}{j}"] = {"type": "noul", "instructions": Q_ANSWERS.format(reason=r, text=x)}
        ra, rb = g["reasons"]["A"], g["reasons"]["B"]
        for i in range(3):
            for j in range(i, 3): q[f"{a}|sim|{i}{j}"] = {"type": "noul", "instructions": Q_SIMILAR.format(a=ra[i], b=rb[j])}
        for i, j in ((0, 1), (0, 2), (1, 2)):
            q[f"{a}|cA|{i}{j}"] = {"type": "noul", "instructions": Q_CONTRA.format(a=ra[i], b=ra[j])}
            q[f"{a}|cB|{i}{j}"] = {"type": "noul", "instructions": Q_CONTRA.format(a=rb[i], b=rb[j])}
    return q


def jev_snippet(rec, gen):
    payload = {"model": JEV_MODEL, "state": rec["state"], "questions": jev_questions(gen)}
    resp = http_json(JEV_URL, payload, os.environ["TYPESAFE_API_KEY"])
    missing = set(payload["questions"]) - set(resp.get("answers", {}))
    if missing: raise RuntimeError(f"snippet {rec['id']}: {len(missing)} Jev questions unanswered")
    return {"id": rec["id"], "model": resp.get("model"), "answers": {k: v["noul"] for k, v in resp["answers"].items()}}


def run_stage(name, recs, fn, workers):
    d = OUT / name; d.mkdir(parents=True, exist_ok=True)
    todo = [r for r in recs if not (d / f"{r['id']}.json").exists()]
    print(f"[{name}] {len(recs) - len(todo)} done, {len(todo)} to do", flush=True)
    done = [0]; errors = []
    def work(r):
        try:
            res = fn(r)
            tmp = d / f"{r['id']}.tmp"; tmp.write_text(json.dumps(res)); tmp.replace(d / f"{r['id']}.json")
        except Exception as e:  # a failed snippet is reported, never silently filled in
            errors.append((r["id"], str(e)[:300]))
        with _lock:
            done[0] += 1
            if done[0] % 5 == 0 or done[0] == len(todo): print(f"[{name}] {done[0]}/{len(todo)}", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as ex: list(ex.map(work, todo))
    for i, e in errors[:8]: print(f"[{name}] snippet {i} FAILED: {e}")
    if errors: print(f"[{name}] {len(errors)} snippets failed; rerun the same command to retry them")
    return not errors


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stages", default="gen,zero,jev"); ap.add_argument("--limit", type=int)
    ap.add_argument("--cond", default="fixed"); ap.add_argument("--out", default="wu_run", help="output folder under work/"); ap.add_argument("--reuse-claude-arguments", action="store_true"); args = ap.parse_args(); stages = args.stages.split(",")
    recs = [json.loads(l) for l in (HERE / "contexts.jsonl").read_text().splitlines() if l.strip()]
    recs = [r for r in recs if r["cond"] == args.cond][: args.limit]
    global OUT
    OUT = HERE / (args.out if args.cond == "fixed" else f"{args.out}_{args.cond}")
    OUT.mkdir(exist_ok=True)
    if {"gen", "zero", "llm"} & set(stages) and not os.environ.get("LLM_API_KEY"): sys.exit("Set LLM_API_KEY first.")
    if "jev" in stages and not os.environ.get("TYPESAFE_API_KEY"): sys.exit("Set TYPESAFE_API_KEY first.")
    if args.reuse_claude_arguments and args.cond == "fixed":   # skip the gen stage by reusing the committed Claude arguments
        (OUT / "gen").mkdir(exist_ok=True)
        for f in (ROOT / "results" / "wu_graph_claude" / "arguments").glob("*.json"):
            if not (OUT / "gen" / f.name).exists(): (OUT / "gen" / f.name).write_text(f.read_text())
    T = load_templates() if {"gen", "llm"} & set(stages) else {}
    print(f"{len(recs)} snippets, LLM {LLM_MODEL} at {LLM_BASE}, {WORKERS} workers", flush=True)
    gen = lambda r: json.loads((OUT / "gen" / f"{r['id']}.json").read_text())
    have = lambda rs: [r for r in rs if (OUT / "gen" / f"{r['id']}.json").exists()]
    if "gen" in stages: run_stage("gen", recs, lambda r: gen_snippet(r, T), WORKERS)
    if "zero" in stages: run_stage("zero", recs, zero_snippet, WORKERS)
    if "jev" in stages: run_stage("jev", have(recs), lambda r: jev_snippet(r, gen(r)), 4)
    if "llm" in stages: run_stage("llm", have(recs), lambda r: llm_score_snippet(r, gen(r), T), WORKERS)
    print("Finished. Results are in", OUT.name)


if __name__ == "__main__":
    main()
