# Experiments

All accuracy numbers are for the task "which of A and B is the professor". Paired tests are exact McNemar tests; intervals for differences come from a bootstrap that resamples whole meetings (seed 2026).

## Inputs

| Name | Text | Labels | Size |
| --- | --- | --- | --- |
| Released | `meeting.csv` from kandicew/social-reasoning | its `power` column | 151 |
| Rebuilt, same span | `turns_same_span` in `data/icsi_rebuilt_snippets.jsonl` | `professor` | 150 |
| Rebuilt, 15 or 60 extra segments per side | `turns_pm15`, `turns_pm60` | `professor` | 150 |

## Runs and where their outputs live

| Run | What was asked | Output |
| --- | --- | --- |
| Jev arm 1 | Released text. "Is speaker X the professor?", "Does X hold more power?", and eight cue questions, each for A and B | `results/jev_arm1.jsonl` |
| Jev arm 2 | Released text. For each of the 7,248 cached arguments: supported by the transcript, valid as evidence, and (rebuttals) does it counter its reason | `results/jev_arm2.jsonl` |
| Jev arm 3 | Released text. The 24 typed statements used by the typed-statement factor graph | `results/jev_arm3.jsonl` |
| Jev arm 4 | Rebuilt text at all three windows. The two direct questions plus the 24 typed statements | `results/jev_arm4.jsonl` |
| Claude arguments | Rebuilt same-span text. Four aspect summaries, three reasons per speaker per aspect, one rebuttal per reason, written by Claude Haiku subagents | `results/wu_graph_claude/arguments/` |
| Claude scores | Validity and grounding for every argument, similarity and contradiction for reason pairs, by separate Haiku subagents | `results/wu_graph_claude/scores/` |
| Jev scores for Claude arguments | Rebuilt same-span text. Validity and grounding for each Claude-written argument, whether each rebuttal counters its reason, similarity and contradiction for reason pairs (168 questions per snippet) | `results/wu_graph_claude/jev_scores.jsonl` |
| Claude zero-shot | "Which of A or B has more power", with a stated probability, by Haiku and by Sonnet subagents | `results/wu_graph_claude/zero_haiku/`, `zero_sonnet/` |

Jev is TypeSafe AI's decision model (`jev-1.14.0` in every response). Every question's wording is in one block at the top of `scripts/jev_collect.py`. The instructions given to the Claude subagents are the three `INSTRUCTIONS_*.md` files in `results/wu_graph_claude/`; none of the subagents had access to labels.

## Methods

- **Direct question.** Predict the speaker with the higher Jev probability for "Is speaker X the professor?".
- **XOR factor graph.** The factor graph of Wu et al.: their rule file, reason weight 20, rebuttal weight 18, solved exactly as an integer program (PuLP with CBC). The implementation is `quote_power.inference.xor` in KrishMay05/nlp_research.
- **Typed-statement factor graph.** The same graph with the generated text replaced by 12 fixed yes/no statements, three per aspect. Jev's probability for a statement about X weights a reason for X; the same statement about the other speaker is its rebuttal. Relation variables are unused.
- **Grounded extension.** Dung's grounded labelling over reasons and rebuttals, as in the proposal, and a preference-based variant in which an attack succeeds only if the attacker scores at least as high as its target (`scripts/exploratory/`).
- **Wu graph with Claude arguments.** The XOR factor graph over the Claude-written arguments and scores, in the three variants of the paper: reasons only, reasons plus rebuttals, all relations.
- **Word-count rules.** "Whoever says more words" and "whoever has longer turns" is the professor.

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/build_dataset.py` | Builds the dataset and the work files (`rows.json`, `fixed_index.json`, `contexts.jsonl`) |
| `scripts/jev_collect.py` | Sends the Jev requests for arms 1 to 4; reads `TYPESAFE_API_KEY` from the environment |
| `scripts/final_analysis.py` | Accuracy, paired tests, bootstrap and calibration for the Jev runs; writes `results/results.json` |
| `scripts/analyze_wu_graph_claude.py` | Runs the XOR graph over the Claude arguments and scores; writes `results/wu_graph_claude/results.json` |
| `scripts/wu_pipeline.py` | Call-by-call version of the Wu pipeline for any OpenAI-compatible API, with Jev or LLM scoring |
| `scripts/check_against_released.py` | Prints a released snippet next to corpus participant IDs, and summary counts |
| `scripts/icsi.py` | MRT parsing helpers used by the analysis scripts |
| `scripts/exploratory/` | Earlier runs on the released snippets |

The analysis scripts expect a working folder that contains the work files from `build_dataset.py`, the `jev_arm*.jsonl` files, and `data/snippets.jsonl` plus `data/rules.txt` produced by `scripts/setup.sh` in KrishMay05/nlp_research (set `KRISH_REPO` to that checkout, and `ICSI_DIR` to a folder with the two ICSI archives unzipped as `mrt/` and `nxt/`).

## Caveats that apply to every number

- The released file has no development split, and the runs on it were exploratory.
- The questions used on the rebuilt snippets were fixed before that data was built, and each run was made once.
- Only Jev and Claude models were run on the rebuilt snippets. GPT-3.5, Gemma and a human study were not.
- The Claude run is not a call-by-call rerun of the paper's pipeline: each snippet's arguments were written in one pass, and scores are stated probabilities with about 15 distinct values, not token probabilities.
- Four professors appear in the 150 snippets, and one of them in 110.
