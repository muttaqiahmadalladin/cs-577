#!/usr/bin/env bash
# Run every experiment of the report with a Z.ai GLM model in place of GPT-6.1 Terra.
#
#   export ZAI_API_KEY=...        # Developer API key from z.ai/manage-apikey (not a Coding Plan key)
#   export TYPESAFE_API_KEY=...   # Jev, used to score the arguments exactly as for the other models
#   bash scripts/run_glm.sh probe # 2 snippets end to end, a few cents: do this first
#   bash scripts/run_glm.sh run   # all 150 snippets; safe to rerun, finished snippets are skipped
#   bash scripts/run_glm.sh score # print the table and write results/glm_run/
#
# What "run" does:
#   1. GLM writes the arguments with Wu's templates, one request per summary, reason list and rebuttal (36 per snippet)
#   2. GLM is asked directly who has more power, at the original span and with 15 and 60 extra segments
#   3. Jev scores every argument and relation (one call per snippet)
# and "score" then solves the Wu factor graph (three variants) and the grounded extension (both relations).
#
# Optional: GLM_OWN_SCORES=1 also has GLM score its own arguments as in the paper (144 more requests per snippet,
# several times the cost). GLM does not return token probabilities, so those scores are 0.99 or 0.01.
#
# GLM-5.3 always reasons before answering and rejects thinking.type=disabled, so the requests set reasoning_effort=low
# and leave room for the reasoning tokens. Override with GLM_MODEL, GLM_EFFORT, GLM_WORKERS if needed.
#
# Through OpenRouter instead of Z.ai (same model, one key for many providers):
#   export ZAI_API_KEY=<OpenRouter key>  GLM_BASE_URL=https://openrouter.ai/api/v1  GLM_MODEL=z-ai/glm-5.3
#   export GLM_EXTRA_JSON='{"reasoning": {"effort": "low"}}'
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ZAI_API_KEY:?Set ZAI_API_KEY first (export ZAI_API_KEY=...). Do not write the key into any file.}"
export LLM_API_KEY="$ZAI_API_KEY"
export LLM_BASE_URL="${GLM_BASE_URL:-https://api.z.ai/api/paas/v4}"
export LLM_MODEL="${GLM_MODEL:-glm-5.3}"
export LLM_LOGPROBS=0 LLM_MAX_TOKENS=4096
if [ -n "${GLM_EXTRA_JSON:-}" ]; then export LLM_EXTRA_JSON="$GLM_EXTRA_JSON"; else export LLM_EXTRA_JSON="{\"reasoning_effort\": \"${GLM_EFFORT:-low}\"}"; fi
export LLM_WORKERS="${GLM_WORKERS:-4}"
RUN=glm_run
STAGES=gen,zero,jev; [ "${GLM_OWN_SCORES:-0}" = 1 ] && STAGES=$STAGES,llm

if [ ! -f work/contexts.jsonl ] || [ ! -f work/rules.txt ]; then
  echo "Building the dataset first (downloads the public sources)"
  python3 scripts/get_sources.py && python3 scripts/build_dataset.py && python3 scripts/convert_released_cache.py
fi

case "${1:-}" in
  probe)
    : "${TYPESAFE_API_KEY:?Set TYPESAFE_API_KEY first.}"
    python3 scripts/wu_pipeline.py --out ${RUN}_probe --limit 2 --stages gen,zero,jev
    python3 - <<'PY'
import json
g = json.load(open("work/glm_run_probe/gen/0.json")); z = json.load(open("work/glm_run_probe/zero/0.json"))
print("\nProbe looks like this. Check that the reasons are real sentences about the conversation and the answer names A or B.")
print("  reasons for A (style):", g["aspects"]["style"]["reasons"]["A"])
print("  first rebuttal       :", g["aspects"]["style"]["rebuttals"]["A"][0])
print("  direct answer        :", repr(z["answer"]), "-> p_A", z["p_A"])
PY
    ;;
  run)
    : "${TYPESAFE_API_KEY:?Set TYPESAFE_API_KEY first.}"
    python3 scripts/wu_pipeline.py --out $RUN --stages $STAGES
    python3 scripts/wu_pipeline.py --out $RUN --cond ctx15 --stages zero
    python3 scripts/wu_pipeline.py --out $RUN --cond ctx60 --stages zero
    echo "Done. If any snippet FAILED above, run the same command again. Then: bash scripts/run_glm.sh score"
    ;;
  score)
    python3 scripts/score_run.py --run $RUN --name "$LLM_MODEL"
    ;;
  *) echo "usage: bash scripts/run_glm.sh probe|run|score"; exit 2 ;;
esac
