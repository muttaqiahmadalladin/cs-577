# Experiments

Accuracy is evaluated against institutional professor/non-professor labels, a proxy for power rather than independent behavioral judgments. Jev is asked about professor status; the direct LLM prompts ask about power, so these prompts are not fully harmonized. Paired tests are exact McNemar tests; their independence assumption does not account for snippets sharing a meeting. Whole-meeting bootstrap intervals (seed 2026) address meeting clustering conditional on these four professors, not generalization to new professors.

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

Jev is TypeSafe AI's decision model. The direct-arm outputs and the Terra/Haiku argument score files record `jev-1.14.0`; all 150 exported GLM score rows omit the resolved scorer version, so it is unknown from those rows. Every direct-arm question's wording is in one block at the top of `scripts/jev_collect.py`. The instructions given to the Claude subagents are the three `INSTRUCTIONS_*.md` files in `results/wu_graph_claude/`; none of the subagents had access to labels.

## Methods

- **Direct question.** Predict the speaker with the higher Jev probability for "Is speaker X the professor?".
- **XOR factor graph.** The factor graph of Wu et al.: their rule file, reason weight 20, rebuttal weight 18, solved exactly as an integer program (PuLP with CBC) in `scripts/factor_graph.py`, adapted from `quote_power.inference.xor` in KrishMay05/nlp_research.
- **Typed-statement factor graph.** The same graph with the generated text replaced by 12 fixed yes/no statements, three per aspect. Jev's probability for a statement about X weights a reason for X; the same statement about the other speaker is its rebuttal. Relation variables are unused.
- **Grounded extension.** Dung's grounded labelling over reasons and rebuttals. See the section below. On the rebuilt snippets it is `scripts/grounded_extension.py`; the earlier runs on the released snippets are in `scripts/exploratory/`.
- **Wu graph on the rebuilt snippets.** The XOR factor graph over generated arguments, in the three variants of the paper: reasons only, reasons plus rebuttals, all relations. Four combinations are reported: Terra, GLM or Haiku arguments with Jev scores, and Haiku arguments with Haiku scores. A reason's weight uses P(valid) x P(grounded). A rebuttal's weight uses P(counters its reason) x P(grounded) under Jev, and P(valid) x P(grounded) under Haiku. The literal computation is `round(exp(log(max(v,1e-6)) + log(max(g,1e-6))), 2)`, then multiplication by 20 or 18; this is not interchangeable with `round(v*g, 2)` at floating-point half-cent boundaries. Released-arm Jev rescoring instead uses rebuttal validity x countering; it is a different scoring condition.
- **Word-count rules.** "Whoever says more words" and "whoever has longer turns" is the professor.

The inherited cross-speaker similarity factors are redundant: speaker XOR and OROUT imply `reason_A + reason_B <= 1`, so `reason_A + reason_B + similarity <= 2` is automatically satisfied even in the LP relaxation. Each nonnegative similarity variable contributes the same constant to either speaker's objective. A similarity ablation cannot test whether useful similarity reasoning helps. Within-speaker contradictions remain active: they change the GLM result from 106 correct with rebuttals to 104 with all relations. Reasons-only inference reduces to comparing sums of quantized reason strengths, subject to ties.

The evaluated implementations show no demonstrated reliable improvement over direct questioning. They do not establish equivalence: Haiku/Jev reasons-only and preference-grounded each score 73.3%, versus 68.0% for direct Haiku, and Terra rebuttals add eight correct cases. These point estimates and the small sample limit the negative conclusion.

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

**Preference relation reduction.** In all 450 Jev-scored Terra/Haiku/GLM cases, grounded prediction equals choosing the side of the strongest reason whose rebuttal does not defeat it. A survivor exists in every stored case. This preserves the reported grounded results but limits what they establish about richer argument interaction; see the [independent implementation check](audits/cs-577-2026-11-16/implementation/verification.json).

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

Development and test meetings are disjoint within each split. The 500 splits overlap and reuse an already explored dataset; they are internal validation of this policy family, not 500 independent experiments or fresh confirmation of the earlier choices.

## Scripts

| Script | Purpose | Needs |
| --- | --- | --- |
| `scripts/reproduce.py` | Runs everything below that needs no API key, in order | numpy, PuLP |
| `scripts/get_sources.py` | Downloads the five external inputs and verifies their SHA-256 | standard library |
| `scripts/build_dataset.py` | Builds the dataset and the work files (`rows.json`, `fixed_index.json`, `contexts.jsonl`) | standard library |
| `scripts/convert_released_cache.py` | Converts the released argument cache to `work/snippets.jsonl` | numpy |
| `scripts/factor_graph.py` | The XOR factor graph as an exact integer program | PuLP |
| `scripts/analyze.py` | Recomputes the original main analyses; `--check` asserts 60 selected values | numpy, PuLP |
| `scripts/grounded_extension.py` | Dung's grounded extension over the Claude arguments, with the proposed and preference relations | standard library |
| `scripts/grounded_policy_search.py` | Search over 288 grounded policies with development and test splits by meeting | standard library |
| `scripts/data_differences.py` | Writes `data/released_vs_rebuilt.csv` and the report's appendix table: every released snippet against the rebuilt set | standard library |
| `scripts/jev_collect.py` | Sends the Jev requests for arms 1 to 4 | `TYPESAFE_API_KEY` |
| `scripts/wu_codex_pipeline.py` | The script that produced the Terra run: the original pipeline call by call through the Codex command line, then Jev scoring | Codex CLI signed in, `TYPESAFE_API_KEY` |
| `scripts/wu_pipeline.py` | Call-by-call version of the original pipeline for any OpenAI-compatible API, with Jev or LLM scoring | API keys |
| `scripts/check_against_released.py` | Prints a released snippet next to corpus participant IDs, and summary counts | standard library |
| `scripts/post_audit_evaluation.py` | Deterministic post-audit evaluation, simple baselines, paired meeting bootstrap intervals and provenance (`results/post_audit/`) | numpy |
| `scripts/clean_quote_study.py` | Clean-bank alignment, stratified human worksheets, bounded quote-checker collection and paired filter evaluation | numpy |
| `scripts/dome_dataset.py` | Pinned importer and participant-disjoint builder for DOME + AMI human dominance labels (`results/external_dome/`) | standard library |
| `scripts/begin_dataset.py` | Pinned importer and calibration evaluator for Google's BEGIN human dialogue-grounding benchmark (`results/external_begin/`) | standard library |
| `scripts/exploratory/` | Earlier runs on the released snippets. They read files from KrishMay05/nlp_research (`KRISH_REPO`) and are kept as a record, not as part of the reproduction | |

Step-by-step instructions and expected outputs are in [REPRODUCE.md](REPRODUCE.md), [EVALUATION.md](research-followup/EVALUATION.md), [VALIDATED-DATASET.md](research-followup/VALIDATED-DATASET.md) and [CLEAN-STUDY.md](research-followup/CLEAN-STUDY.md).

## Caveats that apply to every number

- The released file has no development split, and the runs on it were exploratory.
- The questions used on the rebuilt snippets were fixed before that data was built, and each run was made once.
- Jev, GPT-6.1 Terra, GLM-5.3 and Claude models were run on the rebuilt snippets. GPT-3.5, Gemma, the quote filter and a human study were not rerun there. The released-data quote-filter result remains a historical result on the malformed representation.
- The Terra run is call by call but its scores come from Jev, since the Codex command line does not expose token probabilities. Codex's earlier evaluation (`results/wu_graph_terra/codex_results.txt`) reports 101 correct for reasons-only where `analyze.py` gets 100. For ID 142, the literal historical computation gives objectives A=112.6 and B=113.0, selecting B; direct-product rounding gives A=B=112.8 and selects A under an A tie policy. Thus quantization sensitivity, not a historical objective tie, explains how these counts can differ; the earlier evaluator's exact arithmetic is undocumented. The historical tables retain 100. The three primary Jev-scored full graphs remain 108/105/104 correct.
- Terra's collection manifest describes rebuttal validity x grounding x countering, while the primary evaluation uses countering x grounding. The alternative formula changes predictions on IDs 74 and 110 while preserving 108 correct. The archived collection-script hash differs from the committed script, and at audit time the loader required a historical template path. Stored-answer replay and repairs to future collection cannot reconstruct the missing historical artifacts.
- The Haiku run is not call by call: each snippet's arguments were written in one pass, and the Haiku scores are stated probabilities with about 15 distinct values.
- Four professors appear in 110, 23, 15 and 2 snippets. Added context also adds third-party speech and possible role cues, so these results do not isolate a context mechanism or establish new-speaker performance.

The separate `scripts/post_audit_evaluation.py` analysis writes to `results/post_audit/`, preserving the literal historical quantization and recording conditional objectives, deterministic ties to A and prediction-level provenance. The `reasons_product_round` sensitivity explicitly uses direct-product rounding. It does not replace the historical tables. Its outputs and rerun command are described in [REPRODUCE.md](REPRODUCE.md).

## Robustness checks

Computed by the "Robustness" block of `scripts/analyze.py` and stored under `robustness` in `results/report_numbers.json`.

- One professor accounts for 110 of the 150 rebuilt snippets. On the 40 snippets with the other three professors, Jev scores 77.5%, 85.0% and 85.0% at the three context lengths, Terra 77.5% and Sonnet 70.0%.
- The first of the two speakers to talk is the professor in 83 of 150 snippets, the same as the majority label.
- At the original span Jev is correct in 85.9% of snippets where the professor is A and 52.3% where the professor is B (balanced accuracy 69.1%, AUC 0.79). With 60 extra segments per side the two are 89.4% and 89.2%. Sonnet: 71.8% and 81.5%.

## Running another model (GLM)

`scripts/run_glm.sh` reruns the argument experiments with a Z.ai GLM model: `probe` (2 snippets), `run` (all 150), `score`.
It calls `wu_pipeline.py` with `--out glm_run`, `LLM_LOGPROBS=0` and `reasoning_effort=low` (GLM-5.3 always reasons and
does not return token probabilities, so the printed answer is used), then `score_run.py`, which prints the Table 3 rows
for that model and writes `results/glm_run/`. `score_run.py --run <folder> --name <model>` works for any
`wu_pipeline.py` run. Keys are read from `ZAI_API_KEY` and `TYPESAFE_API_KEY` in the environment only.

### GLM-5.3 results (run 2026-11-12)

Stored in `results/glm_run/` and rescored by steps 9 and 10 of `reproduce.py`. Asked directly: 73.3% (original span),
74.0% (15 extra segments), 82.0% (60 extra). Wu graph with Jev scores: 71.3% reasons only, 70.7% with rebuttals, 69.3%
all relations. Grounded extension: 71.3% proposed relation (all decisions by the tie-break), 67.3% preference relation.
Policy search: selected policy 67.1% against 71.5% for the direct Jev question, ahead in 41 of 500 splits.
Notes: the direct answer is the letter GLM prints (no token probabilities); one rebuttal (snippet 122, coordination, B)
came back empty and was scored as it was.

## Gradual argumentation (QBAF), 2026-11-13

`scripts/qbaf.py` builds a quantitative bipolar argumentation framework per snippet from the stored arguments and Jev
scores, in the style of ArgLLM (Freedman et al., AAAI 2025), and evaluates the claim with DF-QuAD and Quadratic Energy
semantics, flat or grouped by aspect, with a prior of 0.5 or the direct Jev answer. All 8 variants times 3 argument sets
are reported in `results/qbaf_results.json`; none is selected on the test set. Range: 68.7% to 74.0%; no paired comparison
with the direct Jev question (71.3%) is significant. This does not establish equivalence. Reference without arguments: a majority vote of the GLM, Terra,
Sonnet and Jev direct answers scores 77.3% (15 wins to 6 losses against Jev alone, p=0.078).

## Debate with a judge (GLM-5.3), 2026-11-13

`scripts/judge_run.py` (`bash scripts/run_glm.sh judge`): GLM-5.3 reads the conversation and its own 12 reasons per
side with their rebuttals, then answers A or B; each snippet is judged in both orders. Answers are in
`results/glm_run/judge.jsonl`. A's case first 67.3%, B's case first 69.3%, against 73.3% asked directly; same answer in
both orders for 117 of 150 (86 correct), meaning predictions change on 33/150 snippets (22%); the judge answers A in 215 of 300 judgments. The three-correct-answer aggregate difference masks that decision instability. With one call per order, this cannot distinguish a causal order effect from generation variability; same-order repeated calls are needed. This static self-judging protocol does not cover iterative debate generally.
