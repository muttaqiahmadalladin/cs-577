# CS 577 project: a speaker-attribution confound in a conversational power benchmark

Krish Patel, Jiwon Kim, Muttaqi Ahmad Alladin (Purdue University)

Report: [report/report.pdf](report/report.pdf)

## Summary

Wu et al. (NAACL 2025) predict which of two speakers in a six-turn ICSI meeting snippet is the professor.
On their 151 released snippets nothing we tried beats always answering A (55.0%).
Matching every snippet back to the ICSI corpus shows that the released text and labels disagree about who is speaking:
under the letter-to-person mapping that makes the labels correct, 57.6% of words are displayed under the other speaker's letter.

With the same words attributed to the people who said them (150 usable snippets, 56.7% majority baseline):

| Input | Jev: "is X the professor" | Typed-statement factor graph |
| --- | ---: | ---: |
| Released text and labels | 48.0% | 51.3% |
| Corrected attribution, same words | 71.3% | 70.0% |
| Corrected, 15 extra segments per side | 84.7% | 80.7% |
| Corrected, 60 extra segments per side | 89.3% | 90.7% |

Corrected same-span Jev against the majority label: 34 wins, 12 losses, exact McNemar p = 0.0016.
All of this is exploratory work on a small test set with four professors; see the Limitations section of the report.

## Check the audit yourself

`scripts/verify_wu_bug.py` uses only the Python standard library and three public files
(Wu's `meeting.csv` and the two ICSI annotation archives; links are in the script header).

```bash
python3 scripts/verify_wu_bug.py            # the six audit numbers
python3 scripts/verify_wu_bug.py --show 0   # snippet 0 next to the raw corpus
```

## Contents

| Path | What it is |
| --- | --- |
| `report/` | LaTeX source and PDF |
| `data/corrected_snippets.jsonl` | The 150 corrected snippets: corpus offsets, real speaker IDs, labels, and turns at three context lengths |
| `results/jev_arm1.jsonl` | Jev direct and cue questions on the released snippets |
| `results/jev_arm2.jsonl` | Jev scores for Wu's 7,248 cached arguments |
| `results/jev_arm3.jsonl` | Typed statements on the released snippets |
| `results/jev_arm4.jsonl` | Direct questions and typed statements on the corrected snippets (same span, 15, 60) |
| `results/results.json` | Every number in the report's corrected-data section |
| `scripts/build_corrected.py` | Locates the snippets in ICSI and rebuilds them with true speakers |
| `scripts/jev_collect.py` | All Jev question wording and the collection code (`TYPESAFE_API_KEY` from the environment) |
| `scripts/final_analysis.py` | Accuracy, paired tests, meeting-level bootstrap, calibration |
| `scripts/exploratory/` | Earlier runs on the released snippets (grounded-extension variants, rescoring) |

## Reproducing the analysis

1. Clone [KrishMay05/nlp_research](https://github.com/KrishMay05/nlp_research) and run its `scripts/setup.sh`; this converts Wu's pinned release into `snippets.jsonl` and `rules.txt`. Set `KRISH_REPO` to that checkout.
2. Unzip the ICSI archives into `$ICSI_DIR/mrt` and `$ICSI_DIR/nxt`.
3. Put those two files in a working folder under `data/`, then run `build_corrected.py`, then `final_analysis.py` with the `results/jev_arm*.jsonl` files alongside.

## Data and licences

The ICSI Meeting Corpus and its annotations are distributed under CC BY 4.0 (Janin et al., 2003); the corrected snippets here are derived from it.
The released snippets and cached arguments belong to [kandicew/social-reasoning](https://github.com/kandicew/social-reasoning) and are not redistributed here.
Jev is a proprietary model from TypeSafe AI (`jev-1.14.0`).
