# Reproducing this project

There are three levels. Levels 1 and 2 are fully deterministic and need no API key. Level 3 re-collects model outputs and cannot be bit-for-bit reproducible, because it depends on hosted models.

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

It runs the eight steps below in order and stops at the first failure. On a laptop it takes a few minutes, most of it in the integer programs of step 5.

| Step | Command | What it proves | Expected last line |
| --- | --- | --- | --- |
| 1 | `get_sources.py` | The five external inputs are the same bytes we used | five lines starting with `ok` |
| 2 | `build_dataset.py --check` | The committed dataset is regenerated exactly from the sources | `committed dataset reproduced exactly` |
| 3 | `build_dataset.py` | Writes `work/rows.json`, `work/fixed_index.json`, `work/contexts.jsonl` | `wrote ... icsi_rebuilt_snippets.jsonl and work files ...` |
| 4 | `convert_released_cache.py` | Converts the released argument cache to `work/snippets.jsonl` | `wrote ... snippets.jsonl and ... rules.txt` |
| 5 | `analyze.py --check` | Every table entry and paired test in the report is recomputed from `results/` | `check: 46 of 46 report values reproduced` |
| 6 | `grounded_extension.py` | The grounded extension results | four result lines |
| 7 | `grounded_policy_search.py` | The 288-policy search with held-out selection | `chosen in ... splits` lines |
| 8 | `data_differences.py` | The per-snippet differences in `data/released_vs_rebuilt.csv` and the report's appendix table | `151 released snippets; 150 in the rebuilt set; ...` |

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

## Level 2: every number, from the committed model outputs

```bash
python3 scripts/convert_released_cache.py
python3 scripts/analyze.py --check
python3 scripts/grounded_extension.py
python3 scripts/grounded_policy_search.py
```

`analyze.py` reads the model answers in `results/` and recomputes the report's tables, paired tests, bootstrap interval, Brier scores and per-professor accuracy, then writes `results/report_numbers.json`. With `--check` it compares 46 values with the ones printed in the report.

Fixed seeds: the meeting-level bootstrap uses seed 2026 with 10,000 resamples, and the policy search uses seed 2026 with 500 splits. The integer programs are solved exactly, so the graph predictions do not depend on solver randomness.

Three rows of the report's Table 1 are not recomputed here because they are results of [KrishMay05/nlp_research](https://github.com/KrishMay05/nlp_research): the grounded extension as proposed (69 of 151), the quote filter (64 of 151) and Gemma 4 zero-shot (66 of 151). That repository documents how to rerun them.

## Level 3: re-collecting the model outputs

These steps call hosted models. Results can differ from ours if a model version changes; the outputs we used are committed so that levels 1 and 2 never depend on this.

### Jev (TypeSafe AI)

```bash
export TYPESAFE_API_KEY=...            # keep the key out of files and out of chat logs
python3 scripts/jev_collect.py --dry-run
python3 scripts/jev_collect.py --arms 1,2,3,4
```

- Every response we used reports model `jev-1.14.0`. Set `JEV_MODEL` to pin a version; the default is `jev-latest`.
- All four arms together are about 3 million input tokens, well under one US dollar at the launch price.
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

`scripts/wu_codex_pipeline.py` produced `results/wu_graph_terra/`. It needs the Codex CLI signed in with a ChatGPT account and `TYPESAFE_API_KEY`. Put it in a folder next to `contexts.jsonl` (from `work/`) and run:

```bash
export TYPESAFE_API_KEY=...
python3 wu_codex_pipeline.py --limit 2      # probe
python3 wu_codex_pipeline.py                # stages gen, zero, jev
```

Each prompt is sent as its own `codex exec` session, ephemeral, read-only and with tools disabled, in an empty directory, using the prompt templates downloaded from the pinned commit of the original repository. Our run used model `gpt-6.1-terra` with no reasoning effort, 5,546 requests, and `jev-1.14.0` for scoring. The settings and hashes of that run are in `results/wu_graph_terra/manifest.json`, `transport_settings.json` and `provenance.json`. Hosted models are not deterministic, so a rerun will not give identical text.

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
