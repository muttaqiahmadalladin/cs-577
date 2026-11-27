# CS 577 project: conversational power in ICSI meeting excerpts

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24327838.svg)](https://doi.org/10.5281/zenodo.24327838)

Muttaqi Ahmad Alladin\*, Krish Patel\*, Jiwon Kim\* (Purdue University)

\* These authors contributed equally.

Report: [report/report.pdf](report/report.pdf)

We revisit the multi-agent social reasoning method of Wu et al. (NAACL 2025), which predicts which of two speakers in a short ICSI meeting excerpt is the professor. We evaluate their factor graph, Dung's grounded extension, a System One decision model (Jev), and Claude models, on the released snippets and on a snippet set rebuilt from the ICSI corpus.

## Results

Released snippets (151, always answering A scores 55.0%): the XOR factor graph reproduces the published 54.3%, and no method we tried scores higher than the base rate. Details are in the report.

Tracing each released snippet back to the ICSI corpus shows that its displayed speaker letters and its label disagree: under the reading of the letters that makes the labels correct, 57.6% of the words appear under the other speaker's letter. The evidence and its limits are in the report's Data section and in [docs/DATA.md](docs/DATA.md). We therefore rebuilt the snippets with speakers taken from the corpus.

ICSI-rebuilt snippets (150, always answering A scores 56.7%):

| Method | Same span | 15 extra segments per side | 60 extra per side |
| --- | ---: | ---: | ---: |
| Jev: "is X the professor" | 71.3% | 84.7% | 89.3% |
| Typed-statement factor graph (Jev) | 70.0% | 80.7% | 90.7% |

Argument-based methods on the same span, by who wrote and who scored the arguments:

| Arguments | Scores | Model asked directly | Wu graph, reasons only | + rebuttals | all relations | Grounded extension (preference) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| GPT-6.1 Terra, call by call | Jev | 72.7% | 66.7% | 72.0% | 72.0% | 70.0% |
| GLM-5.3, call by call | Jev | 73.3% | 71.3% | 70.7% | 69.3% | 67.3% |
| Claude Haiku, one pass | Jev | 68.0% | 73.3% | 70.0% | 70.0% | 73.3% |
| Claude Haiku, one pass | Haiku | 68.0% | 68.7% | 67.3% | 68.0% | 64.7% |

Claude Sonnet asked directly scores 76.0%. In no row does the full graph differ significantly from asking the model directly (largest gap: GLM-5.3, 69.3% against 73.3%, p = 0.44). Gradual argumentation (68.7% to 74.0% over 24 variants) and a debate judged by GLM-5.3 (67.3% and 69.3%) give the same picture. A majority vote of four direct answers scores 77.3% (p = 0.078 against Jev alone).

The released cached GPT-3.5 arguments were generated on the mismatched text of `meeting.csv`, and our solver run on them reproduces the published 54.3% factor-graph result exactly (82 of 151), so that result was computed on this text. We cannot tell what text the human judges saw. These observations have not yet been confirmed with the authors of Wu et al.

## Post-Cutoff SCOTUS OT2026 Dataset & Perturbation Suite

To test whether zero-shot power prediction on ICSI relies on pretraining exposure or fragile punctuation/label cues, we construct a fresh post-training-cutoff dataset of **333 non-overlapping role-masked dyadic excerpts** from all 13 October--November 2026 U.S. Supreme Court oral argument transcripts (`2026-10-05` to `2026-11-10`) and evaluate three open/API models across 30 experimental arms ($6{,}993$ snippet judgments; see [docs/SCOTUS_DATA.md](docs/SCOTUS_DATA.md) and Section 4.1 of [report/report.pdf](report/report.pdf)):

| Dataset / Condition | Gemma-4-26B | Llama-3.3-70B | GPT-4o-mini |
| --- | ---: | ---: | ---: |
| **ICSI-150 Rebuilt** (`clean`) — Acc / MCC | 64.0% / +.290 | 64.0% / +.273 | 62.0% / +.256 |
| **ICSI-150** (`no_commas`) — Acc (Flip%) | 66.7% (6.7%) | 66.7% (2.7%) | 62.0% (5.3%) |
| **ICSI-150** (`extra_commas`) — Acc (Flip%) | 66.7% (6.7%) | 64.7% (3.3%) | 60.0% (3.3%) |
| **ICSI-150** (`no_disfluencies`) — Acc (Flip%) | 66.7% (4.0%) | 67.3% (3.3%) | 61.3% (6.0%) |
| **ICSI-150** (`letter_swap`) — Acc (Flip%) | 71.3% (11.3%) | 66.7% (9.3%) | 64.7% (14.7%) |
| **SCOTUS-333 OT2026** (`masked` post-cutoff) — Acc / MCC | **66.7%** / **+.336** | 50.2% / +.004 | 45.9% / -.081 |
| **SCOTUS-263** (`masked test` split) — Acc / Macro-$F_1$ | **65.4%** / **65.2%** | 49.4% / 48.6% | 44.9% / 44.8% |
| **SCOTUS-333** (`raw` unmasked titles) — Acc (Flip%) | **72.1%** (16.8%) | 50.8% (36.6%) | 49.2% (21.3%) |
| **SCOTUS-333** (`masked no_commas`) — Acc (Flip%) | 65.8% (13.5%) | 50.5% (32.7%) | 47.7% (21.0%) |
| **SCOTUS-333** (`masked extra_commas`) — Acc (Flip%) | 68.5% (12.0%) | 46.8% (35.7%) | 46.5% (24.0%) |
| **SCOTUS-333** (`masked letter_swap`) — Acc (Flip%) | 66.4% (24.9%) | 50.8% (41.4%) | 49.5% (40.2%) |

## Documentation

- [docs/REPRODUCE.md](docs/REPRODUCE.md): how to regenerate the data and every number, step by step.
- [docs/DATA.md](docs/DATA.md): the ICSI dataset, its sources, how it is built, and its schema.
- [docs/SCOTUS_DATA.md](docs/SCOTUS_DATA.md): the post-cutoff SCOTUS OT2026 dataset, role/identity masking rules, leak verification, perturbations, and two-class precision/recall/MCC evaluator.
- [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md): every run, method and script, with caveats.

## Environment Setup & Quick Start (`uv` / `setup.sh`)

For the grading container (`nvidia/13.1.2-cudnn-devel-ubuntu24.04` with `uv` installed) or local macOS/Linux:

```bash
# 1. Create and populate the virtual environment (.venv) using uv
bash setup.sh
source .venv/bin/activate

# 2. Reproduce the ICSI dataset and all 60 core report values from committed outputs (no API key needed)
python3 scripts/reproduce.py

# 3. Rebuild/verify the post-cutoff SCOTUS OT2026 dataset and check byte-for-byte identity + zero identity leaks
python3 scripts/build_scotus_dataset.py --check

# 4. Recompute all 30-arm Nous evaluation, perturbation, and two-class Precision/Recall/F1/MCC tables from cached predictions
python3 scripts/run_scotus_and_perturbations.py --score-only

# 5. Run the unit test suite
python3 -m unittest discover -s tests -v
```

To re-query the Nous API live across all 30 arms ($6{,}993$ snippet evaluations, $\sim\$0.88$ total API cost):

```bash
NOUS_API_KEY="sk-..." python3 scripts/run_scotus_and_perturbations.py
```

## Repository layout

| Path | Contents |
| --- | --- |
| `setup.sh` | One-command `uv` virtual environment setup script |
| `report/` | ACL `[preprint]` LaTeX source (`report.tex`) and compiled PDF (`report.pdf`) |
| `data/` | `icsi_rebuilt_snippets.jsonl`, `released_vs_rebuilt.csv`, and `scotus_ot2026/` (`snippets_masked.jsonl`, `snippets_raw.jsonl`, `manifest.json`) |
| `results/` | Every model answer (`results/*.jsonl`, `results/nous_eval/predictions/`) and computed summaries (`report_numbers.json`, `results/nous_eval/summary.json`) |
| `scripts/` | Dataset builders (`build_icsi_dataset.py`, `build_scotus_dataset.py`), perturbation/metrics utility (`perturb_and_metrics.py`), evaluation runners, and `reproduce.py` |
| `tests/` | Unit tests for dataset integrity, leak verification, perturbations, and metric reproduction |
| `docs/` | Data and experiment documentation |

## Licences

Code: MIT. The ICSI dataset is derived from the ICSI Meeting Corpus (CC BY 4.0). The SCOTUS OT2026 dataset is derived from public-domain U.S. Supreme Court oral argument transcripts (`17 U.S.C. § 105`). The released snippets of Wu et al. are downloaded at build time and not redistributed. Jev is a proprietary model from TypeSafe AI.

