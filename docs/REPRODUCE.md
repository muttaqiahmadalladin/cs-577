# Reproducing this project

There are three levels. Levels 1 and 2 rebuild data and replay stored answers without an API key. Level 3 re-collects model outputs and cannot be bit-for-bit reproducible, because it depends on hosted models. Numerical replay does not recover undocumented historical collection settings.

## Requirements

- Python 3.10 or newer (developed on 3.13).
- Level 1: the standard library only.
- Level 2: `pip install -r requirements.txt` (numpy, and PuLP with its bundled CBC solver).
- About 30 MB of downloads.

## One command

```bash
pip install -r requirements.txt
python3 scripts/reproduce.py
```

It runs the twelve steps below in order and stops at the first failure. On a laptop it takes a few minutes, most of it in the integer programs.

| Step | Command | What it proves | Expected last line |
| --- | --- | --- | --- |
| 1 | `get_sources.py` | The five external inputs are the same bytes we used | five lines starting with `ok` |
| 2 | `build_dataset.py --check` | The committed dataset is regenerated exactly from the sources | `committed dataset reproduced exactly` |
| 3 | `build_dataset.py` | Writes `work/rows.json`, `work/fixed_index.json`, `work/contexts.jsonl` | `wrote ... icsi_rebuilt_snippets.jsonl and work files ...` |
| 4 | `convert_released_cache.py` | Converts the released argument cache to `work/snippets.jsonl` | `wrote ... snippets.jsonl and ... rules.txt` |
| 5 | `analyze.py --check` | The main analyses are recomputed from `results/`; 60 selected values are asserted | `check: 60 of 60 report values reproduced` |
| 6 | `grounded_extension.py` | The Terra/Haiku grounded extension results | six result lines |
| 7 | `grounded_policy_search.py` | The 288-policy search with held-out selection | `chosen in ... splits` lines |
| 8 | `data_differences.py` | The per-snippet differences in `data/released_vs_rebuilt.csv` and the report's appendix table | `151 released snippets; 150 in the rebuilt set; ...` |
| 9 | `score_run.py --run glm_run --name glm-5.3` | The stored GLM direct, graph and grounded rows | `wrote results/glm_run/` |
| 10 | `grounded_policy_search.py --run glm_run` | The policy search over GLM arguments | `chosen in ... splits` lines |
| 11 | `qbaf.py` | The gradual-semantics variants and direct-answer vote | majority-vote result line |
| 12 | `judge_run.py --run glm_run --name glm-5.3 --score` | The stored GLM judge answers and order agreement | order-agreement result line |

Commands in this table run from `scripts/` inside the runner. For manual invocation from the repository root, prefix each with `python3 scripts/`.

## Level 1: the data, from public sources

```bash
python3 scripts/get_sources.py
python3 scripts/build_dataset.py --check
```

`get_sources.py` downloads into `sources/` and checks each file against a recorded SHA-256:

| File | SHA-256 |
| --- | --- |
| `meeting.csv` | `d405654d402c0e7bca37f0732b6005aff70297aeadf7c6e0fa83c1d4e371b286` |
| `all_obj.pkl` | `e4be3c7c6a3543a77ad07eddde44bfa42f6e58fa6a4bf47df53ea9e894f1e318` |
| `rules.txt` | `5a88f4a5298fcd1fc8d30736bdcb2fba30cb47cc0bafcb7f68c9d12aea3addde` |
| `icsi_mrt.zip` | `9db98ebdd61a085b4f45f24f46e9c9f6c6f26c3c9cd41643a3b9e74362c85de7` |
| `icsi_core_nxt.zip` | `cf4860245b9ca9c9ed11a66e5a74cfea2a99a686a52f7580aa0a6bc2225895a9` |

The first three come from `kandicew/social-reasoning` at commit `fed11b69765b4a398ce4a985adedfb65ec3098ab`; the two archives come from the University of Edinburgh's ICSI corpus mirror. If a checksum fails, an upstream file has changed.

`build_dataset.py` is described step by step in [DATA.md](DATA.md). It is a pure function of `meeting.csv` and the two archives: no randomness, no model, no network.

## Level 2: numerical replay from the committed model outputs

```bash
python3 scripts/convert_released_cache.py
python3 scripts/analyze.py --check
python3 scripts/grounded_extension.py
python3 scripts/grounded_policy_search.py
python3 scripts/data_differences.py
python3 scripts/score_run.py --run glm_run --name glm-5.3
python3 scripts/grounded_policy_search.py --run glm_run
python3 scripts/qbaf.py
python3 scripts/judge_run.py --run glm_run --name glm-5.3 --score
```

`analyze.py` reads the model answers in `results/` and recomputes the original main tables, paired tests, bootstrap interval, Brier scores and per-professor accuracy, then writes `results/report_numbers.json`. With `--check` it asserts 60 selected values. The remaining runner steps recompute supplemental analyses, but do not assert every corresponding LaTeX value. The [audit replay](audits/cs-577-2026-11-16/reproduction-verification.json) passed all twelve steps and left all 369 tracked files byte-identical to the pinned checkout.

Fixed seeds: the original meeting-level bootstrap uses seed 2026 with 10,000 resamples, and the policy search uses seed 2026 with 500 splits. The historical weight calculation is `multiplier * round(exp(log(max(v,1e-6)) + log(max(g,1e-6))), 2)`, with multiplier 20 for reasons or 18 for rebuttals. At floating-point half-cent boundaries, `round(exp(sum(logs)), 2)` and `round(v*g, 2)` are not interchangeable.

For Terra reasons-only ID 142, the literal historical computation gives A=112.6 and B=113.0, so B wins and the result is 100/150. The direct-product rounding sensitivity gives A=B=112.8 and 101/150 when ties go to A. The first audit's tie-only explanation used the latter approximation; it does not describe the historical implemented weights. The earlier saved evaluator's exact arithmetic is undocumented. The original tables retain 100, and the primary Jev-scored full graphs remain 108/105/104 correct.

Three rows of the report's Table 1 are not recomputed here because they are results of [KrishMay05/nlp_research](https://github.com/KrishMay05/nlp_research): the grounded extension as proposed (69 of 151), the quote filter (64 of 151) and Gemma 4 zero-shot (66 of 151). That repository documents how to rerun them.

The earlier logistic-regression range also lacks an input-to-output reproduction here. The released-data quote-filter result remains historical; the old arguments and annotations refer to that representation and are not a clean-data rerun.

### Audit checks and separate post-audit evaluation

The committed audit checks can be rerun without hosted models:

```bash
python3 docs/audits/cs-577-2026-11-16/statistics/verify_statistics.py .
python3 docs/audits/cs-577-2026-11-16/implementation/checks.py .
```

The statistics check uses 100,000 whole-meeting bootstrap resamples (seed 2026). It verifies the unchanged-letter/gold attribution comparison: 63 to 90 correct on 128 snippets, 42 wins and 15 losses, gain 21.1 points and 95% interval +9.6 to +32.7. These intervals are conditional on the sampled meetings and four professors. See the [audit](audits/cs-577-2026-11-16/AUDIT.md) for the majority-mapping correction and graph restrictions.

`scripts/post_audit_evaluation.py` is a separate evaluation of the saved answers, preserving the literal historical quantization and adding deterministic ties to A, conditional objectives, paired meeting intervals and prediction-level provenance in `results/post_audit/`. The separately named `reasons_product_round` sensitivity uses direct-product rounding. Run it from the repository root:

```bash
python3 scripts/post_audit_evaluation.py
python3 scripts/post_audit_evaluation.py --check
python3 scripts/dome_dataset.py fetch && python3 scripts/dome_dataset.py build
python3 scripts/begin_dataset.py fetch-build
python3 -m unittest discover -s tests -v
```

Its values are separate from the historical tables and sixty assertions. Its manifest records the evaluation formulas and input hashes; unknown historical model versions remain unknown. No new hosted-model or clean-data quote-filter result follows from replaying stored outputs. See [EVALUATION.md](research-followup/EVALUATION.md), [VALIDATED-DATASET.md](research-followup/VALIDATED-DATASET.md) and [CLEAN-STUDY.md](research-followup/CLEAN-STUDY.md) for details.

## Level 3: re-collecting the model outputs

These steps call hosted models. Results can differ from ours if a model version changes; the outputs we used are committed so that levels 1 and 2 never depend on this.

### Jev (TypeSafe AI)

```bash
export TYPESAFE_API_KEY=...            # keep the key out of files and out of chat logs
python3 scripts/jev_collect.py --dry-run
python3 scripts/jev_collect.py --arms 1,2,3,4
```

- The direct-arm responses record model `jev-1.14.0`. Set `JEV_MODEL` to request a version; the default is `jev-latest`. The exported GLM argument-score rows omit the resolved scorer version; the audit cannot recover it from those rows.
- The historical four-arm run used about 3 million input tokens; current costs and version availability must be checked before collection.
- Each request body is saved under `work/payloads/`.
- The script overwrites nothing: it skips snippets already present in `results/jev_arm*.jsonl`. Move those files aside to collect from scratch.

### Jev scores for the Claude-written arguments

```bash
python3 scripts/wu_pipeline.py --stages jev --reuse-claude-arguments
```

This sends one request per snippet (168 questions) and writes `work/wu_run/jev/<id>.json`. Our run is committed as `results/wu_graph_claude/jev_scores.jsonl`.

### Claude arguments, scores and zero-shot answers

These were produced by Claude subagents (Haiku for arguments and scores, Haiku and Sonnet for zero-shot), each given one instruction file and one batch of label-free conversations:

| Output | Instruction file | Batches |
| --- | --- | --- |
| `results/wu_graph_claude/arguments/` | `INSTRUCTIONS_gen.md` | 10 batches of 15 snippets |
| `results/wu_graph_claude/scores/` | `INSTRUCTIONS_score.md` | 10 batches of 15, by different agents than the writers |
| `results/wu_graph_claude/zero_haiku/`, `zero_sonnet/` | `INSTRUCTIONS_zero.md` | 3 batches of 50 |

Snippets were shuffled with seed 577 before batching. Each output was checked for shape (three reasons and three rebuttals per speaker per aspect, probabilities in range). This run is not deterministic and is not a call-by-call rerun of the original pipeline.

### The Terra run (the original pipeline, call by call, through the Codex command line)

`scripts/wu_codex_pipeline.py` is the committed Terra collection script. It needs the Codex CLI signed in with a ChatGPT account and `TYPESAFE_API_KEY`. The historical invocation placed it next to `contexts.jsonl` (from `work/`):

```bash
export TYPESAFE_API_KEY=...
python3 wu_codex_pipeline.py --limit 2      # probe
python3 wu_codex_pipeline.py                # stages gen, zero, jev
```

Each prompt is sent as its own `codex exec` session, ephemeral, read-only and with tools disabled, in an empty directory. The saved settings report model `gpt-6.1-terra` with no reasoning effort, 5,546 requests, and `jev-1.14.0` for scoring. The settings and hashes are in `results/wu_graph_terra/manifest.json`, `transport_settings.json` and `provenance.json`.

At audit time the template loader required a historical `work/speaker-audit/upstream` tree rather than downloading the templates. The archived executed-script hash differs from the committed script, and the original `evaluation.json` referenced by `codex_results.txt` is absent. Repairs for future collection do not recover those missing historical artifacts. The manifest also gives a triple-product rebuttal formula, while the primary evaluation uses countering x grounding; the alternative changes IDs 74 and 110 while preserving 108 correct. Treat any new collection and evaluation as a separately manifested run, and preserve the executed scripts. Hosted models will not reproduce identical text.

### The same pipeline against any OpenAI-compatible API

```bash
export LLM_API_KEY=...                  # any OpenAI-compatible chat API
export LLM_BASE_URL=... LLM_MODEL=...
python3 scripts/wu_pipeline.py --stages gen,zero,jev,llm
```

`wu_pipeline.py` downloads the prompt templates from the pinned commit of the original repository and makes one call per summary, per reasons list and per rebuttal, as the paper describes. See the header of the script for all options.

## What is in each folder after a full run

| Folder | Committed | Contents |
| --- | --- | --- |
| `sources/` | no | The five downloaded inputs |
| `work/` | no | Intermediate files: converted cache, dataset index, Jev request states, saved payloads |
| `data/` | yes | `icsi_rebuilt_snippets.jsonl` |
| `results/` | yes | Model answers and computed numbers |
