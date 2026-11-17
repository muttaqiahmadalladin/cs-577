# Post-audit deterministic evaluation

This separately named evaluation is retrospective and exploratory, not preregistered. It reads the frozen saved model answers and makes no hosted-model calls. Historical inputs, results, `factor_graph.py`, and the original sixty assertions remain unchanged.

Run from the repository root, with numpy installed:

```sh
python scripts/post_audit_evaluation.py
python scripts/post_audit_evaluation.py --check
python -m unittest discover -s tests -p 'test_post_audit_evaluation.py' -v
```

`--check` regenerates all four artifacts in memory and compares bytes without writing. Environment versions and evaluation-code hashes are part of the manifest; changes to these deliberately require reviewing/regenerating the manifest. No wall-clock timestamp enters the outputs. The source commit records the latest commit touching the immutable model-answer inputs, rather than whichever follow-up commit contains the evaluator.

## Optimization and validation

Reasons use `20*round(exp(log(max(validity,1e-6))+log(max(grounding,1e-6))),2)`; Jev rebuttals use the same operation with weight18 and countering/grounding. This is the literal historical computation, including floating-point half-cent effects. Haiku's own rebuttals use validity/grounding; its ordinal relation values are divided by5. The unquantized reason-sum baseline uses raw validity*grounding products, without the floor or rounding. The strongest-survivor baseline keeps reasons strictly stronger than their paired rebuttal, selects the side of the strongest survivor, and resolves equal strengths with the reason sum then A. It agrees with preference-grounded decisions on all450 Jev-scored cases (150 each Terra, Haiku, GLM); this empirical agreement does not prove equivalence for arbitrary tied strength patterns.

The optimizer parses and validates the pinned rule topology, including the repeated style-A contradiction pair. It enumerates all eight masks for each aspect and combines exact local maxima with a two-state dynamic program enforcing at least one reason for the selected speaker. Rebuttal and relation constants are included in both exported conditional objectives. Speaker ties within1e-9 objective units choose A. Within-side mask ties choose the lexicographically smallest exact optimum. Similarity constraints are redundant under speaker XOR/OROUT and add only a common constant. Contradictions remain active.

Every JSONL stream must have unique IDs exactly matching all150 rebuilt examples. Argument files, Haiku batch files, self-score files, and all three Jev direct conditions receive the same coverage checks. Duplicate JSON object keys, missing/non-string IDs, schema drift, nonfinite values, and probabilities outside[0,1] fail validation. Each Jev graph bank must have the exact168-answer schema. Haiku self scores are converted under their distinct documented schema. These checks verify saved-file alignment, not the semantic validity or original API provenance of the scores.

The optional `active_variables` argument to `conditional_objectives` supports the clean quote study: an omitted reason or rebuttal is OFF, a missing XOR endpoint drops its XOR, and any retained unpaired rebuttal is free to be ON. A side with no available reason is infeasible; when all reasons are removed, the fallback is A, matching the historical wrapper.

## Correction to the first implementation audit

The archived independent review I3 and its `implementation/checks.py` used `round(v*g,2)`, which is not identical to the implementation's `round(exp(log(v)+log(g)),2)`. Thus I3's claim that historical ID142 is necessarily an unresolved objective tie is superseded by the literal arithmetic check:

| Terra ID142, gold A | Objective A | Objective B | Prediction | Correct/150 |
|---|---:|---:|---|---:|
| Literal historical exp/log quantization |112.6|113.0|B|100|
| Separately labeled product-round sensitivity |112.8|112.8|A under declared tie rule|101|

Two half-cent roundings explain the difference: content B1, `.57*.5`, has literal weight5.8 versus product-round5.6; engagement A0, `.55*.9`, has literal weight9.8 versus product-round10.0. The product-round method has564 hundredths per side and is tie sensitive. The literal implemented method has no speaker tie here. This explains a route to100 versus101, but does not establish which evaluator produced the historical text artifact. Both calculations are exported, without rewriting the original reviews or historical result tables.

Twelve CBC regression comparisons cover Terra0/142, Haiku0, and GLM0 in all three main modes. An additional executed read-only check compared every primary full-graph prediction: exact enumeration agrees with historical CBC on450/450, including all150 for each bank. All primary graph conditional objectives are untied under the declared tolerance.

## Results and paired uncertainty

Primary Jev-scored full graphs preserve108/150 Terra,105/150 Haiku,104/150 GLM. Reasons/rebuttals/full counts are100/108/108 for Terra,110/105/105 for Haiku, and107/106/104 for GLM. Haiku self-scored counts are103/101/102. The exact unquantized sum gives100/110/107 for Terra/Haiku/GLM; strongest survivor gives105/110/101.

The following intervals resample45 whole meetings with replacement10,000 times, seed2026. Each draw retains paired methods and all snippets within a chosen meeting; accuracy remains snippet weighted, with a variable denominator. These are percentile intervals for the observed meeting population and condition on its narrow professor pool. They do not establish unseen-speaker generalization or equivalence, and no multiple-comparison-adjusted confirmatory claim is made.

| Comparison, first minus second | Difference, pp |95% meeting interval, pp|
|---|---:|---:|
|Terra full graph minus Terra direct|−0.67|[−7.95,6.52]|
|Haiku full graph minus Haiku direct|2.00|[−5.65,9.60]|
|GLM full graph minus GLM direct|−4.00|[−10.90,2.99]|
|Terra rebuttals minus reasons|5.33|[1.22,10.94]|
|GLM judge A-first minus GLM direct|−6.00|[−13.77,0.75]|
|GLM judge B-first minus GLM direct|−4.00|[−13.10,4.68]|
|Four-model vote minus Jev direct|6.00|[0.00,11.32]|
|Four-model vote minus Sonnet direct|1.33|[−6.02,8.24]|

All69 paired contrasts, exact wins/losses and unrounded-to-display interval values are in `summary.json`, including all main graph/direct, reason/rebuttal/relation ablations, judges, ensembles, and triple-formula sensitivities. The positive Terra rebuttal interval is an exploratory finding and must remain visible alongside uncertain primary graph/direct comparisons. An interval including zero is not evidence of equivalence; no equivalence margin was specified.

Direct counts are109 Terra,102 Haiku,114 Sonnet,110 GLM,107 Jev; context Jev gives127/134. Judge counts are101 A-first,104 B-first,113 when order disagreements fall back to GLM direct. Predictions change on33/150 across judge orders; one call per order does not isolate ordering from generation variability. The four-model majority (GLM/Terra/Sonnet/Jev, ties to Jev) gives116/150.

Similarity-only predictions match reasons+rebuttals in all three Jev banks; contradiction-only matches full graph. Full relations change no Terra/Haiku decisions versus rebuttals and change GLM IDs40/109, reducing its correct count by2. Equal accuracy is not used as a substitute for prediction agreement.

The historical Terra collection manifest says rebuttal validity*grounding*countering; the evaluated primary formula is countering*grounding. The new manifest preserves that disagreement explicitly. A separately labeled triple-product sensitivity applies literal exp(sum of three floored logs), weight18 and two-decimal rounding: Terra108 (changed74/110), Haiku108 (changed4/27/74/93/98), GLM107 (changed35/60/109). These remain exploratory perturbations.

## Artifacts and limits

- `results/post_audit/predictions.jsonl`: all150 aligned IDs, labels, meeting IDs, method predictions, both conditional objectives, chosen masks and baseline strengths.
- `results/post_audit/summary.json`: every count,69 paired intervals, objective ties, judge changes, and the literal/product-round correction.
- `results/post_audit/manifest.json`: immutable input SHA-256 values, input source commit, exact formulas, tolerance/rounding policy, runtime versions, recorded model fields, prediction hash and historical manifest disagreement. GLM Jev-score model versions are unknown because all150 rows omit the field; omitted Haiku batch/self-score version fields remain unknown too.
- `results/post_audit/report_value_provenance.json`: producing commands and output pointers for new methods, all sixty original assertions, historical supplements, and three explicitly external original rows: proposed grounded69/151, quote-filter64/151, Gemma66/151. This runner does not recompute those external rows or the historical logistic-regression range.

Missing original executed collection/evaluation artifacts, missing recorded model versions, absence of independent human quote judgments, the role-as-power proxy, retrospective exploration, and the narrow professor population remain limitations. No new annotations, fresh held-out result or hosted-model replication is claimed.
