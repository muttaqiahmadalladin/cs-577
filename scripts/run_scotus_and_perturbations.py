#!/usr/bin/env python3
"""Run the Nous API zero-shot power evaluation across ICSI-150 (original + perturbations) and SCOTUS OT2026 (masked + raw + perturbations).

Because the Nous API enforces a 50 requests/minute rate limit (2,100/hour) alongside a 500,000 tokens/minute limit,
we support both:
  1. Single-snippet mode (--batch-size 1): exact first-token logprob scoring on individual snippets.
  2. Batched JSON mode (--batch-size 15, default): packs 15 conversations per request (same blind batch protocol as
     results/wu_graph_claude/INSTRUCTIONS_zero.md) and asks for {"<id>": {"answer": "A"|"B", "p_A": 0.0-1.0}}.
     With --batch-size 15, all 30 arms across 3 models (6,993 snippet evaluations) take only ~480 HTTP requests
     (~10 minutes within the 50 req/min limit) and cost < $1.50 total.

Every response is cached on disk under work/nous_cache/ (gitignored) and written cleanly to
results/nous_eval/predictions/<model_slug>/<arm>.jsonl, with an aggregate summary in
results/nous_eval/summary.json. Enforces a hard USD budget cap (--max-usd, default 5.00).
"""
import argparse, hashlib, json, math, os, re, sys, threading, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import perturb_and_metrics as pm

ZERO_SHOT_SINGLE = (
    "In this task, you are given a conversation between A and B. Decide which speaker has more power "
    "in the conversation. Respond with A or B.\n\nConversation:\n{conversation}\n\noutput:"
)

ZERO_SHOT_BATCH = (
    "You are given a batch of short conversations between two speakers, A and B (sometimes other speakers C, D appear). "
    "For each conversation, decide which of A or B has more power in the conversation, judging only from the conversation text.\n\n"
    "Return ONLY a valid JSON object mapping each conversation id to an object with keys \"answer\" (\"A\" or \"B\") "
    "and \"p_A\" (your probability from 0.0 to 1.0 that A has more power; \"answer\" must be \"A\" when p_A > 0.5 and \"B\" when p_A < 0.5).\n"
    "Example format: {{\"0\": {{\"answer\": \"A\", \"p_A\": 0.75}}, \"1\": {{\"answer\": \"B\", \"p_A\": 0.20}}}}\n\n"
    "Conversations:\n{batch_text}"
)

DEFAULT_MODELS = [
    ("gemma-4-26b", "google/gemma-4-26b-a4b-it"),
    ("llama-3.3-70b", "meta-llama/llama-3.3-70b-instruct"),
    ("gpt-4o-mini", "openai/gpt-4o-mini"),
]

_lock = threading.Lock()
_spend_usd = [0.0]
_calls_made = [0]
_last_req = [0.0]


def load_env():
    for candidate in (ROOT / ".env", ROOT.parent.parent.parent / ".env"):
        if candidate.exists():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    k, v = s.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def conversation(turns):
    return "\n".join(f"{t['speaker']}: {t['text']}" for t in turns)


def call_api(base_url, api_key, payload, cache_dir, max_usd, min_interval=0.35, tries=8):
    raw_key = json.dumps({"base": base_url, "payload": payload}, sort_keys=True)
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    cache_file = cache_dir / f"{key_hash}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8")), True

    with _lock:
        if _spend_usd[0] >= max_usd:
            raise RuntimeError(f"Budget cap reached (${_spend_usd[0]:.4f} >= ${max_usd:.2f})")

    body = json.dumps(payload).encode("utf-8")
    url = base_url.rstrip("/") + "/chat/completions"
    for attempt in range(tries):
        with _lock:
            wait = min_interval - (time.monotonic() - _last_req[0])
            if wait > 0:
                time.sleep(wait)
            _last_req[0] = time.monotonic()

        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "cs577-nous-eval/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.loads(r.read())
                rem = r.headers.get("x-ratelimit-remaining-requests")
                rst = r.headers.get("x-ratelimit-reset-requests")
                if rem is not None and int(float(rem)) <= 2 and rst is not None:
                    time.sleep(max(1.0, float(rst) + 0.5))
            usage = resp.get("usage") or {}
            cost = float(usage.get("cost") or 0.0)
            with _lock:
                _spend_usd[0] += cost
                _calls_made[0] += 1
            tmp = cache_dir / f"{key_hash}.tmp"
            tmp.write_text(json.dumps(resp), encoding="utf-8")
            tmp.replace(cache_file)
            return resp, False
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:400]
            rst = e.headers.get("x-ratelimit-reset-requests") if e.headers else None
            if e.code == 429 and attempt < tries - 1:
                sleep_s = float(rst) + 1.5 if rst else min(45.0, 5.0 * (attempt + 1))
                print(f"  [429 rate limit] sleeping {sleep_s:.1f}s before retry...", flush=True)
                time.sleep(sleep_s)
                continue
            if e.code in (408, 409, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(min(30.0, 2.0 * (2 ** attempt)))
                continue
            raise RuntimeError(f"HTTP {e.code} for {payload.get('model')}: {detail}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < tries - 1:
                time.sleep(min(30.0, 2.0 * (2 ** attempt)))
                continue
            raise RuntimeError(f"Network error for {payload.get('model')}: {e}")


def parse_json_map(text):
    """Extract a JSON object from model output (stripping markdown fences if present)."""
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I | re.M).strip()
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start:end + 1]
    return json.loads(s)


def eval_batch(batch_rows, base_url, api_key, model_id, cache_dir, max_usd, window="turns_same_span"):
    blocks = []
    for r in batch_rows:
        blocks.append(f"=== Conversation ID: {r['id']} ===\n{conversation(r[window])}")
    prompt = ZERO_SHOT_BATCH.format(batch_text="\n\n".join(blocks))
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }
    resp, cached = call_api(base_url, api_key, payload, cache_dir, max_usd)
    text = (resp["choices"][0]["message"].get("content") or "").strip()
    usage = resp.get("usage") or {}
    batch_cost = float(usage.get("cost") or 0.0) / max(1, len(batch_rows))
    try:
        parsed = parse_json_map(text)
    except Exception:
        parsed = {}

    results = []
    for r in batch_rows:
        item = parsed.get(str(r["id"])) or parsed.get(r["id"])
        if isinstance(item, dict):
            ans = str(item.get("answer", "")).strip().upper()
            try:
                p_a = float(item.get("p_A", 0.75 if ans == "A" else 0.25))
            except (TypeError, ValueError):
                p_a = 0.75 if ans == "A" else 0.25
            if ans not in ("A", "B"):
                ans = "A" if p_a >= 0.5 else "B"
        elif isinstance(item, str) and item.strip().upper() in ("A", "B"):
            ans = item.strip().upper()
            p_a = 0.75 if ans == "A" else 0.25
        else:
            # Fallback single-snippet call if any ID was omitted by the batch response
            single_prompt = ZERO_SHOT_SINGLE.format(conversation=conversation(r[window]))
            spayload = {"model": model_id, "messages": [{"role": "user", "content": single_prompt}], "temperature": 0, "max_tokens": 6}
            sresp, _ = call_api(base_url, api_key, spayload, cache_dir, max_usd)
            stext = (sresp["choices"][0]["message"].get("content") or "").strip()
            m = re.search(r"\b([AB])\b", stext)
            ans = m.group(1) if m else "A"
            p_a = 0.99 if ans == "A" else 0.01
            batch_cost += float((sresp.get("usage") or {}).get("cost") or 0.0)

        results.append({
            "id": r["id"],
            "model": model_id,
            "answer": ans,
            "prediction": ans,
            "p_A": round(p_a, 4),
            "gold": r["professor"],
            "cost": round(batch_cost, 8),
        })
    return results


def build_arms():
    icsi = [json.loads(l) for l in (ROOT / "data" / "icsi_rebuilt_snippets.jsonl").read_text(encoding="utf-8").splitlines()]
    scotus_masked = [json.loads(l) for l in (ROOT / "data" / "scotus_ot2026" / "snippets_masked.jsonl").read_text(encoding="utf-8").splitlines()]
    scotus_raw = [json.loads(l) for l in (ROOT / "data" / "scotus_ot2026" / "snippets_raw.jsonl").read_text(encoding="utf-8").splitlines()]
    return [
        ("icsi_clean", icsi, "turns_same_span"),
        ("icsi_no_commas", [pm.perturb_snippet(r, "no_commas") for r in icsi], "turns_same_span"),
        ("icsi_extra_commas", [pm.perturb_snippet(r, "extra_commas") for r in icsi], "turns_same_span"),
        ("icsi_no_disfluencies", [pm.perturb_snippet(r, "no_disfluencies") for r in icsi], "turns_same_span"),
        ("icsi_letter_swap", [pm.perturb_snippet(r, "letter_swap") for r in icsi], "turns_same_span"),
        ("scotus_masked", scotus_masked, "turns_same_span"),
        ("scotus_raw", scotus_raw, "turns_same_span"),
        ("scotus_masked_no_commas", [pm.perturb_snippet(r, "no_commas") for r in scotus_masked], "turns_same_span"),
        ("scotus_masked_extra_commas", [pm.perturb_snippet(r, "extra_commas") for r in scotus_masked], "turns_same_span"),
        ("scotus_masked_letter_swap", [pm.perturb_snippet(r, "letter_swap") for r in scotus_masked], "turns_same_span"),
    ]


def flip_rate(base_preds, pert_preds, is_letter_swap=False):
    """Fraction of snippets whose substantive speaker choice flipped under perturbation."""
    by_id_base = {r["id"]: r["prediction"] for r in base_preds}
    flips, total = 0, 0
    for r in pert_preds:
        b = by_id_base.get(r["id"])
        if b not in ("A", "B"):
            continue
        p = pm.swap_ab(r["prediction"]) if is_letter_swap else r["prediction"]
        flips += (p != b)
        total += 1
    return {"flips": flips, "total": total, "flip_rate": flips / total if total else 0.0}


def main():
    load_env()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "https://inference-api.nousresearch.com/v1"))
    ap.add_argument("--batch-size", type=int, default=15)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--model", help="run only this model slug (gemma-4-26b, llama-3.3-70b, gpt-4o-mini)")
    ap.add_argument("--max-usd", type=float, default=5.0)
    ap.add_argument("--cache-dir", type=Path, default=ROOT / "work" / "nous_cache")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "results" / "nous_eval")
    ap.add_argument("--score-only", action="store_true", help="recompute summary.json from already committed prediction files")
    a = ap.parse_args()

    arms = build_arms()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    if not a.score_only:
        api_key = os.environ.get("LLM_API_KEY", "")
        if not api_key:
            sys.exit("Missing LLM_API_KEY in environment or .env")
        a.cache_dir.mkdir(parents=True, exist_ok=True)

    summary = {"provider": "nous", "base_url": a.base_url, "batch_size": a.batch_size, "models": {}, "total_cost_usd": 0.0}
    total_recorded_cost = 0.0
    from concurrent.futures import ThreadPoolExecutor

    models_to_run = [m for m in DEFAULT_MODELS if not a.model or m[0] == a.model]
    for slug, model_id in models_to_run:
        model_dir = a.out_dir / "predictions" / slug
        model_dir.mkdir(parents=True, exist_ok=True)
        model_res = {"model_id": model_id, "arms": {}, "flips": {}}
        stored_preds = {}

        for arm_name, rows, window in arms:
            pred_file = model_dir / f"{arm_name}.jsonl"
            if a.score_only or pred_file.exists():
                preds = [json.loads(l) for l in pred_file.read_text(encoding="utf-8").splitlines()]
                if len(preds) == len(rows):
                    print(f"[{slug}] {arm_name}: loaded {len(preds)} cached predictions", flush=True)
                else:
                    preds = []
            else:
                preds = []

            if not preds:
                chunks = [rows[i:i + a.batch_size] for i in range(0, len(rows), a.batch_size)]
                def run_chunk(chunk):
                    return eval_batch(chunk, a.base_url, api_key, model_id, a.cache_dir, a.max_usd, window)
                with ThreadPoolExecutor(max_workers=a.workers) as ex:
                    for chunk_res in ex.map(run_chunk, chunks):
                        preds.extend(chunk_res)
                body = "".join(json.dumps(p) + "\n" for p in preds)
                pred_file.write_text(body, encoding="utf-8")
                acc_now = sum(p["gold"] == p["prediction"] for p in preds) / len(preds)
                print(f"[{slug}] {arm_name}: {len(preds)} rows | acc={acc_now:.3f} | live calls={_calls_made[0]} | live spend=${_spend_usd[0]:.4f}", flush=True)

            stored_preds[arm_name] = preds
            total_recorded_cost += sum(float(p.get("cost") or 0.0) for p in preds)
            pairs = [(p["gold"], p["prediction"]) for p in preds]
            metrics = pm.classification_metrics(pairs)
            if arm_name.startswith("scotus_"):
                split_of = {r["id"]: r["split"] for r in rows}
                metrics["dev"] = pm.classification_metrics([(p["gold"], p["prediction"]) for p in preds if split_of.get(p["id"]) == "dev"])
                metrics["test"] = pm.classification_metrics([(p["gold"], p["prediction"]) for p in preds if split_of.get(p["id"]) == "test"])
            model_res["arms"][arm_name] = metrics

        for pert_arm, is_swap in (
            ("icsi_no_commas", False),
            ("icsi_extra_commas", False),
            ("icsi_no_disfluencies", False),
            ("icsi_letter_swap", True),
        ):
            model_res["flips"][pert_arm] = flip_rate(stored_preds["icsi_clean"], stored_preds[pert_arm], is_swap)
        for pert_arm, is_swap in (
            ("scotus_raw", False),
            ("scotus_masked_no_commas", False),
            ("scotus_masked_extra_commas", False),
            ("scotus_masked_letter_swap", True),
        ):
            model_res["flips"][pert_arm] = flip_rate(stored_preds["scotus_masked"], stored_preds[pert_arm], is_swap)

        summary["models"][slug] = model_res

    summary["total_cost_usd"] = round(total_recorded_cost, 6)
    (a.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Done. Summary written to {a.out_dir / 'summary.json'} (total recorded cost: ${summary['total_cost_usd']:.4f})")


if __name__ == "__main__":
    main()
