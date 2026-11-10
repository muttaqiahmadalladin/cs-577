# CS 577 project: conversational power in ICSI meeting excerpts

Muttaqi Ahmad Alladin, Krish Patel, Jiwon Kim (Purdue University)

Report: [report/report.pdf](report/report.pdf)

We revisit the multi-agent social reasoning method of Wu et al. (NAACL 2025), which predicts which of two speakers in a short ICSI meeting excerpt is the professor. We evaluate their factor graph, Dung's grounded extension, a System One decision model (Jev), and Claude models, on the released snippets and on a snippet set rebuilt from the ICSI corpus.

## Results

Released snippets (151, always answering A scores 55.0%): the XOR factor graph reproduces the published 54.3%, and no method we tried scores higher than the base rate. Details are in the report.

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

Claude Sonnet asked directly scores 76.0%. In every row the full graph is within about two points of asking a model directly.

## Documentation

- [docs/REPRODUCE.md](docs/REPRODUCE.md): how to regenerate the data and every number, step by step.
- [docs/DATA.md](docs/DATA.md): the dataset, its sources, how it is built, and its schema.
- [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md): every run, method and script, with caveats.

## Quick start

```bash
pip install -r requirements.txt
python3 scripts/reproduce.py
```

This downloads the public sources and checks their SHA-256, rebuilds the dataset and confirms it matches the committed file byte for byte, and recomputes every number in the report from the committed model outputs (`check: 38 of 38 report values reproduced`). It calls no model and needs no API key.

## Repository layout

| Path | Contents |
| --- | --- |
| `report/` | LaTeX source and PDF |
| `data/` | `icsi_rebuilt_snippets.jsonl` |
| `results/` | Every model answer and the computed numbers (`report_numbers.json`) |
| `scripts/` | Dataset builder, collection and analysis code |
| `docs/` | Data and experiment documentation |

## Licences

Code: MIT. The dataset is derived from the ICSI Meeting Corpus (CC BY 4.0). The released snippets of Wu et al. are downloaded at build time and not redistributed. Jev is a proprietary model from TypeSafe AI.
