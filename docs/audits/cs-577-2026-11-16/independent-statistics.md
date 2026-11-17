# Independent statistics and evaluation audit

**Scope:** `muttaqiahmadalladin/cs-577`, commit [`2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa`](https://github.com/muttaqiahmadalladin/cs-577/tree/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa), independently examined on 2026-11-16. No other reviewers' findings were consulted. No model calls, installs, source edits, or full reproduction. This review checks statistical interpretation and saved prediction coverage; it does not independently authenticate the ICSI annotations or hosted-model provenance.

## Overall assessment

The central attribution finding is substantially stronger than the argumentation null result. The saved Jev outputs reproduce the important paired counts, and correction/context gains remain positive when resampling whole meetings. Conversely, the paper often turns an inability to detect a difference into a claim that a method adds no accuracy. Several tested graph settings actually have positive observed differences. Small samples, shared professors, and exploration make broad claims about argumentation or debate premature.

The repository does several things well: pairs methods on the same snippets, releases outputs, discloses exploration, separates 151 released from 150 rebuilt snippets, explicitly calls policy-search split quantiles a distribution of splits rather than a confidence interval, and uses meeting bootstrap intervals for selected baseline contrasts. I found no hidden denominator loss in the principal streams checked.

## Findings

### 1. High: the negative headline exceeds the statistical evidence

**Classification:** validity threat / overstatement, not a calculation bug. **Confidence:** high.

The abstract and contribution say rebuttals, relations and grounded extension do not improve accuracy, including “for any of three argument-writing models” ([report/report.tex:45–50](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L45-L50), [81–83](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L81-L83)). Yet the table records Haiku/Jev reasons-only and grounded accuracy of 73.3%, versus Haiku direct at 68.0%; the full graph is 70.0%. Terra rebuttals improve the reasons-only graph by eight cases, 5.3 points, with 11 paired wins and three losses, exact p=0.057 ([309–348](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L309-L348)).

The full Terra graph/direct comparison is 14 wins versus 15 losses. With only 29 discordances among 150 observations, even an independence-based paired standard error is about 3.6 percentage points; the estimate cannot establish equality within a few points. The GLM graph/direct comparison has 42 discordances and a four-point deficit, likewise leaving material uncertainty. The report's explicit acknowledgment that a few points are undetectable is fair and should govern the headline. Its later wording, “We find no evidence,” is defensible.

**Implication:** the results support “no demonstrated improvement among these evaluated implementations,” not an equivalence claim or a general conclusion that structured argumentation cannot help. **Correction:** define a practically meaningful margin in advance, report paired meeting-bootstrap differences for every primary graph contrast, and use an equivalence/noninferiority design with enough independent meetings to address that margin. Keep positive and negative observed differences visible. Multiple nonsignificant variants do not collectively prove equivalence.

### 2. Medium: exact McNemar p-values are exact for independent snippets, not this sampling structure

**Classification:** validity threat; proven methodological mismatch in the reported inferential unit. **Confidence:** high about the assumption, moderate about its numerical impact on unexamined graph contrasts.

`mcnemar` uses the ordinary conditional binomial test on discordant snippet outcomes ([scripts/analyze.py:38–40](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/analyze.py#L38-L40)). The 150 snippets come from 45 meetings, with 15 from Bro017, and only four professors. Correlated outcomes within meetings violate the independence that makes that binomial reference exact. Pairing correctly handles dependence between methods on one snippet; it does not handle dependence between snippets.

Importantly, this does **not** overturn the positive findings. My read-only check used 100,000 meeting resamples, seed 2026, retaining snippet-weighted accuracy. Jev rebuilt minus always-A is +14.7 points, 95% percentile interval [6.5, 22.1]; context ±15 minus same-span is +13.3 [6.0, 20.6]; ±60 minus same-span is +18.0 [9.9, 25.7]. The first agrees closely with the committed 10,000-resample interval [6.7, 22.0]. Thus the paper's main positive direction survives this sensitivity analysis.

**Correction:** extend the existing cluster bootstrap to all primary paired contrasts, including graphs, judges and ensembles, and distinguish exploratory snippet-level p-values from inference over new meetings. Meeting resampling still conditions on the narrow professor population; it is not a cure for that external-validity problem.

### 3. Medium: the all-150 “only who is shown saying them differs” contrast also changes eight labels

**Classification:** proven reporting/design confound, with reassuring sensitivity evidence. **Confidence:** high.

The paper states that only displayed attribution differs in the released/rebuilt comparison ([report/report.tex:282–286](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L282-L286)). In fact `analyze.py` scores released predictions against `released_label`, rebuilt predictions against `professor` ([132–156](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/analyze.py#L132-L156)). Labels differ for IDs **3, 15, 47, 79, 88, 111, 119, 121**, and letters are reassigned for 22 snippets. The report discloses these facts elsewhere ([173–178](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L173-L178)).

The confound is quantitatively small: released predictions score 72 with released labels and 74 with rebuilt labels; rebuilt predictions score 107. More decisively, the 128 letter-preserved cases improve from 63/128 to 90/128: 42 wins, 15 losses, +21.1 points, meeting-bootstrap interval [9.6, 32.7] across 43 meetings. The 142 unchanged-label cases improve from 69 to 102. These checks support the attribution explanation while removing a stronger causal claim about the all-150 contrast.

**Correction:** add the 128-case controlled sensitivity analysis, identify the all-150 result as the combined reconstruction/label-correction effect, and retain the separate denominators. This is a wording/analysis repair, not evidence that the correction finding collapses.

### 4. Medium: “order matters little” hides substantial prediction instability

**Classification:** validity threat / interpretation overreach. **Confidence:** high for observed instability; low for attributing it causally to order alone.

The judge changes its answer on **33/150 snippets (22%)** when the order of the two argument cases changes, despite only a three-case net accuracy difference. IDs include 0, 3, 5, 7, 14, 15, 17 and 27; the complete list is in the accompanying verification JSON. The report accurately gives 117 agreements, then concludes “order matters little” ([report/report.tex:339–342](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L339-L342)). Accuracy stability and decision stability are different properties.

My meeting-bootstrap intervals for the judge minus GLM direct are −6.0 points [−13.6, +0.7] for A-first and −4.0 [−13.3, +4.6] for B-first. The observed judge variants underperform, but their inferiority is not established. Likewise, one call per order does not isolate ordering from ordinary generation variability; no same-order repeat baseline exists ([scripts/judge_run.py:75–82](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/judge_run.py#L75-L82)).

**Correction:** say aggregate accuracy changes little while 22% of decisions change; replicate both orders with matched generation settings, measure same-order instability, and report uncertainty over meetings and repeated runs. Scope the conclusion to this static self-judging protocol; it does not test every form of iterative debate.

### 5. Medium: meeting-held-out policy selection is useful internal validation, with narrow generalization

**Classification:** disclosed limitation / validity threat, **not proven test leakage**. **Confidence:** high.

The 288-policy code really selects using development-meeting accuracy and evaluates on disjoint test meetings ([scripts/grounded_policy_search.py:73–86](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/grounded_policy_search.py#L73-L86)). Computing a full-data ranking earlier only for an explicitly optimistic summary does not feed the held-out selections. I found no justification for calling this direct label leakage. The “middle 95% of splits” is accurately labeled; 500 overlapping splits are not 500 independent experiments or a confidence interval for new-data performance.

However, the policy family and broader method search are evaluated after an explicitly exploratory sequence ([report/report.tex:365–367](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L365-L367)). These splits validate selection within a fixed family conditional on this corpus, not all preceding design decisions. Moreover, professor frequencies are **110, 23, 15, 2**. Excluding the dominant professor leaves only three identities, not 40 independent professor examples. Meeting separation does not establish unseen-speaker generalization. The reported subgroup success is encouraging but narrower than a broadly feasible conversational-power task.

**Correction:** freeze the pipeline, use an untouched external meeting sample, and add leave-professor/participant-pair-out analyses where feasible. Bootstrap the entire policy-selection procedure at the meeting level for uncertainty; do not treat the fraction of 500 splits won as a significance test.

### 6. Low: secondary confidence and exploratory-combination claims need uncertainty and multiplicity context

**Classification:** disclosed limitation / reporting gap. **Confidence:** high.

“Most confident fifth” means 28 correct of 30; even an iid Wilson interval is roughly 79–98%, before meeting dependence. AUC and Brier improvement are useful descriptive results, but lack uncertainty. These are normalized probabilities `p_A/(p_A+p_B)`, not unmodified per-question probabilities ([scripts/analyze.py:137–158](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/analyze.py#L137-L158)). That transformation should be stated when discussing calibration.

There are numerous contrasts, 24 gradual variants, and exploratory judge/ensemble combinations. The authors generally avoid claiming their near-threshold p-values as significant, appropriately. The ensemble's p=0.078 and the selected confidence slice should remain exploratory; multiplicity adjustment cannot strengthen the graph null claim. **Correction:** nominate a small primary family, report remaining outcomes descriptively, and obtain confidence/calibration intervals on held-out meetings with a frozen confidence-selection rule.

## Reproducible evidence and handback

The accompanying `statistics/verify_statistics.py` reads committed predictions only and writes no source files. Run from the parent repository:

```sh
.venv/bin/python docs/audits/cs-577-2026-11-16/statistics/verify_statistics.py data/audit-sources/cs-577-2026-11-16
```

`statistics/verification.json` captures the result. Coverage checks found 151 unique released Jev IDs, 450 unique rebuilt `(condition, ID)` records, and complete unique 150-ID direct/judge/Jev-score streams for the checked Terra, GLM and Haiku runs. No attrition explanation for the headline results emerged. The one dropped source example and the 128-example attribution denominator are disclosed, not hidden attrition.

**Round-2 priorities:** narrow negative headlines; retain and strengthen attribution/context findings with the controlled subset; distinguish aggregate order effects from decision instability; request clustered uncertainty for graph comparisons and truly untouched evaluation. Residual risks: I did not regenerate graphs, authenticate original annotations, inspect every prompt/provenance record, or audit API-response selection. No finding here depends on assuming undisclosed misconduct or training contamination.
