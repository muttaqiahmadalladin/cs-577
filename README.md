# CS 577 project: conversational power in ICSI meeting excerpts

Muttaqi Ahmad Alladin\*, Krish Patel\*, Jiwon Kim\* (Purdue University)

\* These authors contributed equally.

Report: [report/report.pdf](report/report.pdf)

We revisit the multi-agent social reasoning method of Wu et al. (NAACL 2025), which predicts which of two speakers in a short ICSI meeting excerpt is the professor. We evaluate their factor graph, Dung's grounded extension, a System One decision model (Jev), and Claude models, on the released snippets and on a snippet set rebuilt from the ICSI corpus.

The labels identify institutional professor status, used here as a proxy for conversational power; they are not independent judgments of behavior or authority.

## Results

Released snippets (151, always answering A scores 55.0%): the XOR factor graph reproduces the published 54.3%, and no method we tried scores higher than the base rate. Details are in the report.

Tracing each released snippet back to the ICSI corpus shows that its displayed speaker letters and its label disagree: under the reading of the letters that makes the labels correct, 57.6% of the words appear under the other speaker's letter. The evidence and its limits are in the report's Data section and in [docs/DATA.md](docs/DATA.md). We therefore rebuilt the snippets with speakers taken from the corpus.

On the 128 cases whose letters and gold labels remain unchanged, direct Jev improves from 63 to 90 correct: 42 wins and 15 losses, a gain of 21.1 percentage points (100,000 whole-meeting bootstrap resamples, 95% interval +9.6 to +32.7). The all-150 comparison also includes letter reassignment and eight changed labels.

ICSI-rebuilt snippets (150, always answering A scores 56.7%):

| Method | Same span | 15 extra segments per side | 60 extra per side |
| --- | ---: | ---: | ---: |
| Jev: "is X the professor" | 71.3% | 84.7% | 89.3% |
| Typed-statement factor graph (Jev) | 70.0% | 80.7% | 90.7% |

Argument-based methods on the same span, by who wrote and who scored the arguments:

| Arguments | Scores | Model asked directly | Wu graph, reasons only | + rebuttals | all relations | Grounded extension (preference) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| GPT-6.1 Terra, call by call | Jev | 72.7% | 66.7% | 72.0% | 72.0% | 70.0% |
| Claude Haiku, one pass | Jev | 68.0% | 73.3% | 70.0% | 70.0% | 73.3% |
| Claude Haiku, one pass | Haiku | 68.0% | 68.7% | 67.3% | 68.0% | 64.7% |

Claude Sonnet asked directly scores 76.0%. The evaluated argument pipelines show no demonstrated reliable improvement over direct questioning. Positive point estimates remain: Haiku/Jev reasons-only and preference-grounded each exceed direct Haiku by 5.3 points. These comparisons do not establish equivalence or a general limit on argumentation. The inherited cross-speaker similarity factors cannot affect the graph's decision; within-speaker contradictions can.

## Documentation

- [docs/REPRODUCE.md](docs/REPRODUCE.md): how to regenerate the data and recompute the supported results, step by step.
- [docs/DATA.md](docs/DATA.md): the dataset, its sources, how it is built, and its schema.
- [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md): every run, method and script, with caveats.

## Quick start

```bash
pip install -r requirements.txt
python3 scripts/reproduce.py
```

This runs twelve offline steps: it downloads the public sources and checks their SHA-256, rebuilds the dataset byte for byte, and recomputes the historical analyses from committed model outputs (`check: 60 of 60 report values reproduced`). Those sixty assertions cover selected values, not every claim or historical result in the report. It calls no model and needs no API key. The [independent audit](docs/audits/cs-577-2026-11-16/AUDIT.md) documents the verified replay and its limits.

The historical tables retain their original arithmetic, including Terra reasons-only at 100/150. The post-audit evaluation preserves that computation and reports a separately named direct-product rounding sensitivity (101/150); the difference is floating-point quantization, not a tied historical objective. See [docs/REPRODUCE.md](docs/REPRODUCE.md). The released-data quote-filter result remains historical; no clean-data quote-filter result is claimed here.

## Repository layout

| Path | Contents |
| --- | --- |
| `report/` | LaTeX source and PDF |
| `data/` | `icsi_rebuilt_snippets.jsonl`, and `released_vs_rebuilt.csv` (every released snippet against the rebuilt set) |
| `results/` | Every model answer and the computed numbers (`report_numbers.json`) |
| `scripts/` | Dataset builder, collection and analysis code |
| `docs/` | Data and experiment documentation |

## Licences

Code: MIT. The dataset is derived from the ICSI Meeting Corpus (CC BY 4.0). The released snippets of Wu et al. are downloaded at build time and not redistributed. Jev is a proprietary model from TypeSafe AI.
