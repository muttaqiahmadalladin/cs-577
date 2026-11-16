# Next steps after the independent CS-577 audit

Based on the [consolidated audit](AUDIT.md) and completed peer discussion, 2026-11-16. This is a proposed execution plan; the external repository and existing experiment code have not been edited. Steps marked “new collection” require future model outputs or human annotations.

## 1. Repair the current report using existing evidence

**Priority: first; no new model calls.** Owner: report authors.

- Replace the alternative majority-speaker explanation: 69/128 counts which letter contains more professor words. State that a two-person majority mapping fails in 86/128 cases. Preserve the explicitly conditional 57.6% result.
- Add the 128-case unchanged-letter/gold contrast: 63 versus 90 correct, 42 paired wins/15 losses, +21.1 percentage points with meeting-bootstrap interval [9.6, 32.7]. Describe the all-150 contrast as reconstruction including eight recoded gold letters.
- Use “no demonstrated reliable gain among these implementations” consistently; retain favorable and unfavorable point estimates and the existing low-power caveat.
- State that the judge changed 33/150 decisions across orders. Its small net accuracy difference does not demonstrate decision stability or isolate order causation.
- Use “professor versus non-professor” as the actual label target. Explain the inherited power proxy and differing model prompt framings.

**Acceptance:** every headline has an explicit task, population, comparison and uncertainty; no general argumentation-equivalence claim; no claim about what original-paper human judges saw. Full stored-output reproduction still passes after any prose-only changes. Reconcile stale README/reproduction instructions with the current twelve-step runner.

## 2. Make evaluation identity and graph behavior explicit

**Priority: next; offline work.** Owner: implementation/evaluation maintainer.

Publish a separate evaluation manifest: source commit, corpus/data hash, generator/scorer versions, precise reason/rebuttal formulas, score normalization, rounding, solver version and deterministic tie policy. Preserve the collection manifest as historical provenance. Archive executed script/template hashes and export resolved model metadata, including the missing GLM scorer field. If historical version information cannot be recovered, label it unknown rather than filling it from assumptions.

Write per-snippet predictions and conditional objectives. Explain Terra reasons-only ID 142 and retain both historical and current evaluator provenance. Add meeting-bootstrap paired intervals for primary graph/direct and judge/direct contrasts; predeclare the primary family and treat the rest as exploratory. A report-value manifest should identify each asserted value, its producing command, and externally sourced numbers.

Expose plain reason-sum and strongest-surviving-reason baselines. Separate similarity from contradiction ablations. For the faithful graph, explicitly test and document similarity invariance. For any redesigned graph, require synthetic cases proving the intended relation can alter a prediction; develop the redesign separately.

**Acceptance:** rerunning one manifest reproduces each prediction; formula changes cannot silently retain an aggregate number while changing decisions. Primary full-graph results remain distinguishable from the one tie-sensitive ablation. New relation-scoring spend follows a demonstrated active mechanism.

## 3. Freeze a clean-data quote-filter experiment

**Priority: next research iteration; design first, then new collection.** Owners: experiment lead plus independent evidence annotators.

The most relevant continuation of our earlier work is to test whether the strict quote filter's failure persists when speaker attribution is correct. This targets the new finding rather than merely trying a larger judge on corrupted inputs.

1. Validate an ID/participant/label crosswalk to the rebuilt corpus. Select one clean same-span argument bank and its matching score bank, with verified provenance, before comparing filter variants. The target's stored clean arguments are candidates for exploratory reuse. Old released-text arguments and quote annotations are incompatible with clean transcripts.
2. Have two independent human annotators check a stratified sample of clean-data arguments, with model/gold predictions hidden. Judge quote presence, speaker, support for the particular claim, and whether a rebuttal answers its target. Include “uncertain,” adjudicate disagreements, and measure filter false rejections as well as false acceptances. Preserve the prior assistant-proxy audit as such.
3. Use corrected data already inspected in this audit for development. Choose one filter rule and an uncertainty policy using evidence annotations rather than final power-label accuracy. Keep alternative filters exploratory. Avoid treating a late split of the old 151 snippets as an untouched confirmatory sample.
4. Collect an independently selected test set from additional meetings and speakers. Lock eligibility, professor/non-professor labels, model versions, prompts, thresholds and the primary contrast before looking at test outcomes. Check that expanded windows do not leak overlapping text across partitions. Report meeting and participant membership explicitly.

**Primary contrast:** selected quote-filtered inference minus identical unfiltered inference, using the same corrected transcripts, argument texts, scores, solver and tie rules. Changing the writer/scorer and filter simultaneously would make the filter effect ambiguous.

**Required baselines:** direct prediction under the same role prompt; faithful unfiltered graph; reason sum; strongest-surviving reason; selected filtered graph. Report accuracy, balanced accuracy, per-class recall, argument retention, decision route, paired meeting-level uncertainty and compute cost. Treat role classification and independently labeled behavioral power as separate targets.

**Decision rule:** choose a smallest practically meaningful improvement and a precision/power target before collection. Declare success only if the prespecified analysis supports that target. If uncertainty includes useful benefit and harm, call the result inconclusive. If the filter rejects valid evidence, repair/calibrate the evidence checker on development annotations before enlarging the inference study.

**Acceptance:** data and score provenance are aligned, human evidence validation is real, the only change in the primary pair is filtering, and confirmatory data are genuinely untouched.

## 4. Run focused diagnostic controls rather than another broad method sweep

**Priority: after the design lock; new collection.** Owner: experiment lead.

| Question | Minimal control | Interpretation boundary |
| --- | --- | --- |
| Does letter identity affect results? | Swap A/B consistently with identical prompts and focal people | Relabel predictions back before comparison |
| Is judge instability specifically due to order? | Repeated A-first and repeated B-first calls under matched settings | Compare cross-order flips with same-order variability |
| Why does context help? | Focal-speaker-only versus all-speaker context; status/name masking; length-matched relevant versus unrelated context | Masking can remove legitimate task evidence; define intended use first |
| Does a stronger judge fix filtering? | Fixed clean argument bank × checker capacity, with the same selection rule | Select capacity by evidence validation and requirements, not test accuracy |
| Do interactions add anything? | A graph with demonstrably active relation factors versus matched simple baselines | Any redesigned topology is a new method |

Report these diagnostics as exploratory unless individually preregistered. Favor the smallest set that resolves the failure mechanism before another large factorial collection.

## Recommended immediate sequence

1. Incorporate the report repairs and 128-case sensitivity.
2. Freeze the evaluation manifest, deterministic ties and simple-baseline diagnostics.
3. Establish clean-data argument/score alignment and an independent human evidence audit.
4. Lock one filter comparison and collect fresh speaker-disjoint confirmation data.
5. Run only the diagnostic controls needed to explain the observed result.

The completed audit supplies the source snapshot, independent reviews, discussion record and verification scripts for steps 1–2. No external messages, remote edits, paid model runs, or commits were performed during this audit.
