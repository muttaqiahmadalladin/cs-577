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
| Terra arguments | Rebuilt same-span text. The original pipeline call by call with GPT-6.1 Terra through the Codex command line: one independent request per aspect summary, per list of three reasons and per rebuttal (36 per snippet), tools disabled, no labels | `results/wu_graph_terra/arguments.jsonl` |
| Terra zero-shot | Rebuilt same-span text. "Who has more power", one request per snippet | `results/wu_graph_terra/zero_shot.jsonl` |
| Jev scores for Terra arguments | Validity and grounding for each argument, whether each rebuttal counters its reason, similarity and contradiction for reason pairs (168 questions per snippet) | `results/wu_graph_terra/jev_scores.jsonl` |
| Claude arguments | Rebuilt same-span text. Four aspect summaries, three reasons per speaker per aspect, one rebuttal per reason, written by Claude Haiku subagents | `results/wu_graph_claude/arguments/` |
| Claude scores | Validity and grounding for every argument, similarity and contradiction for reason pairs, by separate Haiku subagents | `results/wu_graph_claude/scores/` |
| Jev scores for Claude arguments | Rebuilt same-span text. Validity and grounding for each Claude-written argument, whether each rebuttal counters its reason, similarity and contradiction for reason pairs (168 questions per snippet) | `results/wu_graph_claude/jev_scores.jsonl` |
| Claude zero-shot | "Which of A or B has more power", with a stated probability, by Haiku and by Sonnet subagents | `results/wu_graph_claude/zero_haiku/`, `zero_sonnet/` |

Jev is TypeSafe AI's decision model (`jev-1.14.0` in every response). Every question's wording is in one block at the top of `scripts/jev_collect.py`. The instructions given to the Claude subagents are the three `INSTRUCTIONS_*.md` files in `results/wu_graph_claude/`; none of the subagents had access to labels.

## Methods

- **Direct question.** Predict the speaker with the higher Jev probability for "Is speaker X the professor?".
- **XOR factor graph.** The factor graph of Wu et al.: their rule file, reason weight 20, rebuttal weight 18, solved exactly as an integer program (PuLP with CBC). The implementation is `quote_power.inference.xor` in KrishMay05/nlp_research.
- **Typed-statement factor graph.** The same graph with the generated text replaced by 12 fixed yes/no statements, three per aspect. Jev's probability for a statement about X weights a reason for X; the same statement about the other speaker is its rebuttal. Relation variables are unused.
- **Grounded extension.** Dung's grounded labelling over reasons and rebuttals. See the section below. On the rebuilt snippets it is `scripts/grounded_extension.py`; the earlier runs on the released snippets are in `scripts/exploratory/`.
- **Wu graph on the rebuilt snippets.** The XOR factor graph over generated arguments, in the three variants of the paper: reasons only, reasons plus rebuttals, all relations. Three combinations are reported: Terra arguments with Jev scores, Haiku arguments with Jev scores, and Haiku arguments with Haiku scores. A reason's weight uses P(valid) x P(grounded). A rebuttal's weight uses P(counters its reason) x P(grounded) under Jev, and P(valid) x P(grounded) under Haiku.
- **Word-count rules.** "Whoever says more words" and "whoever has longer turns" is the professor.

## Grounded extension: method

**Arguments.** Each snippet has 48 arguments: for each of the four aspects, three reasons that A is the professor, three reasons that B is, and one rebuttal for every reason. A reason for X supports the claim "X is the professor".

**Strengths.** A reason has strength P(valid) x P(grounded). A rebuttal has strength P(counters its reason) x P(grounded). The probabilities come from the Haiku scores or from the Jev scores.

**Attack relations.** Two are evaluated.

| Relation | Rebuttal against its reason | Reason for A against reason for B (and the reverse) |
| --- | --- | --- |
| Proposed | Always attacks | Always attack each other |
| Preference | Attacks only if its strength is at least the reason's | Attacks only if strictly stronger |

The preference relation is preference-based argumentation in the sense of Amgoud and Cayrol: an attack from a weaker argument on a stronger one does not succeed.

**Labelling.** The grounded labelling is the least fixed point of: an argument is IN when every attacker is OUT (so an unattacked argument is IN), OUT when at least one attacker is IN, and UNDECIDED otherwise. It is computed by iterating those two rules from the empty labelling until nothing changes.

**Decision.** Predict the speaker with more IN reasons. Ties go to the speaker with the larger sum of reason strengths, then to A. Both tie rules come from the proposal.

**Why the proposed relation is degenerate.** No argument attacks a rebuttal, so every rebuttal is IN and every reason is OUT. Even if weak rebuttals are removed, a reason for A and a reason for B that attack each other form a two-cycle, which the grounded labelling leaves UNDECIDED. Either way no reason is IN, and the decision is made entirely by the tie-break, that is, by the sum of reason strengths. The preference relation breaks both problems because at most one direction of each attack succeeds.

**Results on the 150 rebuilt snippets (same span).**

| Arguments | Scores | Relation | Accuracy | Snippets decided by IN count | Reasons IN |
| --- | --- | --- | ---: | ---: | ---: |
| Terra | Jev | Proposed | 66.7% | 0 | 0 of 3,600 |
| Terra | Jev | Preference | 70.0% | 150 | 1,504 of 3,600 |
| Haiku | Jev | Proposed | 73.3% | 0 | 0 of 3,600 |
| Haiku | Jev | Preference | 73.3% | 150 | 1,517 of 3,600 |
| Haiku | Haiku | Proposed | 68.7% | 0 | 0 of 3,600 |
| Haiku | Haiku | Preference | 64.7% | 141 | 849 of 3,600 |

With Haiku arguments and Jev scores the preference relation is level with the direct Jev question (13 wins to 10 losses, exact McNemar p = 0.68). Full numbers are in `results/grounded_results.json`.

## Grounded extension: policy search

`scripts/grounded_policy_search.py` asks whether any score-aware attack policy does better. It evaluates 288 policies built from the Jev scores of the Haiku arguments:

| Choice | Options |
| --- | --- |
| Reason strength | P(valid) x P(grounded), P(grounded), P(valid) |
| Rebuttal strength | P(counters) x P(grounded), P(counters), P(grounded) |
| When a rebuttal attacks | preference (at least as strong as its reason), or its strength clears 0.3, 0.5 or 0.7 |
| Cross-side attacks | none; stronger reason defeats any opposing reason; the same within an aspect only; only pairs Jev judges similar |
| Decision | count of IN reasons, or summed strength of IN reasons |

To avoid choosing a policy on the snippets it is scored on, meetings are split at random into a development half and a test half; the best development policy is scored on the test half, next to the direct Jev question on the same half. Over 500 splits:

| | Mean test accuracy |
| --- | ---: |
| Selected grounded policy | 69.7% |
| Jev direct | 71.5% |

The selected policy is ahead of the direct question in 133 of 500 splits (mean difference -1.8 points, middle 95% of splits -11.2 to +3.8). On all 150 snippets the policies range from 82 to 111 correct (median 99) against 107 for the direct question; the 111 is the optimistic, same-data maximum. Output: `results/wu_graph_claude/grounded_policy_search.json`.

## Scripts

| Script | Purpose | Needs |
| --- | --- | --- |
| `scripts/reproduce.py` | Runs everything below that needs no API key, in order | numpy, PuLP |
| `scripts/get_sources.py` | Downloads the five external inputs and verifies their SHA-256 | standard library |
| `scripts/build_dataset.py` | Builds the dataset and the work files (`rows.json`, `fixed_index.json`, `contexts.jsonl`) | standard library |
| `scripts/convert_released_cache.py` | Converts the released argument cache to `work/snippets.jsonl` | numpy |
| `scripts/factor_graph.py` | The XOR factor graph as an exact integer program | PuLP |
| `scripts/analyze.py` | Recomputes every table, paired test, interval and calibration number in the report; `--check` compares with the report | numpy, PuLP |
| `scripts/grounded_extension.py` | Dung's grounded extension over the Claude arguments, with the proposed and preference relations | standard library |
| `scripts/grounded_policy_search.py` | Search over 288 grounded policies with development and test splits by meeting | standard library |
| `scripts/data_differences.py` | Writes `data/released_vs_rebuilt.csv` and the report's appendix table: every released snippet against the rebuilt set | standard library |
| `scripts/jev_collect.py` | Sends the Jev requests for arms 1 to 4 | `TYPESAFE_API_KEY` |
| `scripts/wu_codex_pipeline.py` | The script that produced the Terra run: the original pipeline call by call through the Codex command line, then Jev scoring | Codex CLI signed in, `TYPESAFE_API_KEY` |
| `scripts/wu_pipeline.py` | Call-by-call version of the original pipeline for any OpenAI-compatible API, with Jev or LLM scoring | API keys |
| `scripts/check_against_released.py` | Prints a released snippet next to corpus participant IDs, and summary counts | standard library |
| `scripts/exploratory/` | Earlier runs on the released snippets. They read files from KrishMay05/nlp_research (`KRISH_REPO`) and are kept as a record, not as part of the reproduction | |

Step-by-step instructions and expected outputs are in [REPRODUCE.md](REPRODUCE.md).

## Caveats that apply to every number

- The released file has no development split, and the runs on it were exploratory.
- The questions used on the rebuilt snippets were fixed before that data was built, and each run was made once.
- Only Jev, GPT-6.1 Terra and Claude models were run on the rebuilt snippets. GPT-3.5, Gemma and a human study were not.
- The Terra run is call by call but its scores come from Jev, since the Codex command line does not expose token probabilities. Codex's own evaluation of that run (`results/wu_graph_terra/codex_results.txt`) reports 101 correct for the reasons-only graph where `analyze.py` gets 100; the other variants agree.
- The Haiku run is not call by call: each snippet's arguments were written in one pass, and the Haiku scores are stated probabilities with about 15 distinct values.
- Four professors appear in the 150 snippets, and one of them in 110.
