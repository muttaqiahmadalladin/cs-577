# Independent implementation audit, round 1

Reviewed commit `2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa` of `muttaqiahmadalladin/cs-577` on 2026-11-16. This review was conducted independently of the other auditors. Scope: executable graph semantics, scoring alignment, saved-run provenance, and the distinction between numerical recomputation and experimental replication. No hosted model was called and no source, dataset, or result file was changed. The parent reviewer owns the complete reproduction run.

**Overall judgment:** the saved results support useful findings about a defective released input and about prediction on a corpus-rebuilt dataset. The graph comparisons support “no demonstrated benefit in these implementations.” They do not establish equivalence to direct prediction, or a general failure of structured argumentation. Several apparently empirical graph results follow directly from the graph's construction. One numerical discrepancy has a concrete tie-breaking explanation; it does not affect the headline Terra full-graph accuracy.

## Evidence and reproducible checks

The accompanying [implementation/checks.py](implementation/checks.py) reads the pinned checkout and exhaustively enumerates each aspect's eight reason subsets under each fixed speaker choice. This computes conditional graph optima without running the full reproduction. Run from the main repository:

```sh
.venv/bin/python docs/audits/cs-577-2026-11-16/implementation/checks.py
```

It checks all 450 Jev-scored argument sets, speaker-level objective ties, two scoring perturbations, and a simpler equivalent grounded decision. The independently fetched upstream rules had SHA-256 `5a88f4a5298fcd1fc8d30736bdcb2fba30cb47cc0bafcb7f68c9d12aea3addde`, matching the repository's pin. I separately called the repository's `xor` implementation on Terra ID 142 to confirm CBC's choice.

## Findings

### I1. Similarity factors are structurally redundant; parts of the “graph” reduce to simple rules

**Classification:** proven implementation property and scientific interpretation threat. **Severity: high for mechanism claims; no demonstrated accuracy corruption. Confidence: high.**

Sources: [factor_graph.py:33–50](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/factor_graph.py#L33), [pinned upstream rules](https://github.com/kandicew/social-reasoning/blob/fed11b69765b4a398ce4a985adedfb65ec3098ab/rules/rules.txt), [report.tex:325–334](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L325).

Speaker XOR imposes `power_A + power_B = 1`; OROUT implies every A reason is at most `power_A`, and every B reason at most `power_B`. Thus an A reason and B reason sum to at most one. Each cross-side similarity factor imposes only `reason_A + reason_B + similarity <= 2`. With similarity at most one, that constraint is automatically satisfied. Its nonnegative-weight variable can always be one, contributing the same constant to either speaker's objective. This redundancy holds even in the LP relaxation. A similarity ablation cannot improve this implementation because similarity cannot influence its prediction.

The reasons-only graph similarly selects the larger sum of quantized reason strengths, apart from objective ties. This is consistent with the report's plain-sum ablation. Consequently, relation factors' weak performance cannot by itself show that useful relations were inferred and then failed to help: an entire class of those relations never enters the decision.

**Correction / experiment:** document the algebraic redundancy; report similarity and within-side contradiction separately; require a synthetic test in which changing a relation actually changes a prediction before collecting new relation scores. A redesigned graph would be a new method, requiring development data. **Counterargument:** faithful reuse of the released rules is appropriate for replication. Agreed: this is an inherited architectural restriction, not evidence that this repository incorrectly copied the rules.

### I2. Preference-grounded prediction is a strongest-surviving-reason classifier on these scores

**Classification:** proven empirical equivalence with a structural explanation; interpretation threat. **Severity: medium. Confidence: high for the stored cases.**

Sources: [grounded_extension.py:68–81](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/grounded_extension.py#L68), [report.tex:468–476](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L468).

Every rebuttal is unattacked. Remove reasons whose rebuttal strength is at least their own. Among remaining reasons, stronger reasons attack every weaker opposing reason. With a unique strongest survivor, that reason is IN, every surviving opposing reason is OUT, and its side wins. The verifier found a survivor in every case and exact prediction agreement between this simple rule and grounded labelling for **150/150 Terra, 150/150 Haiku, and 150/150 GLM** cases. This preserves the reported 105, 110, and 101 correct respectively.

The disclosed proposed relation's degeneration is also mathematically correct: unattacked rebuttals make every reason OUT, leaving only the strength-sum fallback. The labelling routine itself implements the stated least-fixed-point rules; I found no contrary example in the small sanity checks.

**Correction / experiment:** add the strongest-survivor baseline and describe the induced topology. To test argument interaction more broadly, attacks must express specific incompatibility rather than every opposite-side reason attacking every other one. **Counterargument:** a simple rule can be a valid grounded semantics implementation. Yes; this finding limits what the experiment establishes about richer argumentation, not the correctness of these reported labels.

### I3. An unresolved objective tie explains the 100/101 Terra discrepancy

**Classification:** proven tie-policy defect; disclosed artifact discrepancy now localized. **Severity: medium for reproducibility, low for the main conclusion. Confidence: high.**

Sources: [factor_graph.py:52–53](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/factor_graph.py#L52), [codex_results.txt](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/results/wu_graph_terra/codex_results.txt), [analyze.py:232](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/analyze.py#L232).

For Terra reasons-only **ID 142**, each side sums to **564 hundredths**, giving equal objective values after multiplication by 20. Gold is A; the repository's CBC call returns B. The final `>=` expression compares the chosen binary solution; it does not resolve ties between alternative optimal solutions. Choosing A yields 101 correct, choosing B 100. This fully explains the saved text versus current table discrepancy, although it does not prove which tie policy the earlier evaluator used.

The independent conditional optimization found **no speaker-level ties in the full Terra, Haiku, or GLM graphs** under primary Jev scores: correct counts remain **108, 105, 104**. Thus the Terra full-graph result and its direct-model comparison survive. A passing `analyze.py --check` certifies the selected CBC outcome against the hardcoded count, not uniqueness or agreement across evaluators.

**Correction:** specify a deterministic lexicographic tie policy, store both conditional objectives and prediction-level outputs, and distinguish tie-sensitive results. Preserve the historical 101 as an earlier evaluator result with an explanation.

### I4. Saved scoring provenance is inconsistent, and a scoring change can hide behind equal accuracy

**Classification:** proven provenance mismatch; sensitivity threat. **Severity: medium. Confidence: high.**

Sources: [Terra manifest](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/results/wu_graph_terra/manifest.json), [analyze.py:178–182](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/analyze.py#L178), [score_run.py:95–99](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/score_run.py#L95).

The Terra manifest identifies rebuttal strength as `validity*grounding*countering`; current primary analysis uses `countering*grounding`. Applying the manifest's triple product changes Terra predictions on **IDs 110 and 74**, while retaining **108/150** correct. Equal headline accuracy therefore does not certify the same evaluation. As sensitivity checks, triple products change Haiku from **105 to 108** correct and GLM from **104 to 107**; these are unselected exploratory perturbations, not replacement headline scores.

All 150 Terra and Haiku Jev score rows record `jev-1.14.0`. All 150 GLM score rows omit the model field: `score_run.py` exports only ID and answers. This prevents independently checking their resolved Jev version from the committed score file. Separately, released-arm rescoring uses rebuttal `v*r` in [analyze.py:100](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/analyze.py#L100), meaning validity times countering; rebuilt analysis uses countering times grounding. Those are different estimands, not interchangeable scorers.

**Correction:** retain historical collection manifests, add a distinct evaluation manifest specifying exact formula, quantization and solver, preserve model/version metadata in exports, and report released/rebuilt scoring differences explicitly. **Counterargument:** the report states the rebuilt formula and discloses alternative scoring in historical output. That supports transparency, but does not reconcile the manifest or identify prediction-level changes.

### I5. Numerical recomputation is stronger than the replayable collection provenance

**Classification:** proven operational gaps plus disclosed replication limits. **Severity: medium. Confidence: high.**

Sources: [wu_codex_pipeline.py:327–333](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/wu_codex_pipeline.py#L327), [provenance.json](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/results/wu_graph_terra/provenance.json), [analyze.py:107](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/analyze.py#L107), [report.tex:382–386](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L382).

Terra collection's overridden template loader reads a historical `work/speaker-audit/upstream` path rather than downloading its pinned templates. That tree is not supplied by the collection instructions. Its saved generation-script hash begins `73b9fc...`, whereas the committed script hashes to `83ae7d...`; the original evaluated `evaluation.json`, referenced by `codex_results.txt`, is absent. These facts do not imply invalid model answers; they mean the exact historical collection/evaluation cannot be reconstructed solely from the saved hashes and current scripts.

“Every number” is also broader than the self-contained checks: `analyze.py` explicitly attributes proposed grounded, quote-filter, and Gemma results to another repository rather than recomputing them; the report's earlier logistic-regression range also lacks an input-to-output reproduction here. Other supplemental scripts calculate and overwrite outputs without asserting every corresponding LaTeX value. The report correctly distinguishes stored-answer recomputation from nondeterministic hosted-model replication, but should bound the former too.

**Correction:** make the collection loader portable, archive executed scripts and complete evaluation outputs, and publish a report-value manifest identifying each value's producing command or external provenance. Do not characterize missing historical artifacts as a failed result.

## What survives and next steps

The direct Jev outputs have complete, unique IDs and one recorded model version: 151 rows in each released arm and 450 `(ID, condition)` rows for rebuilt conditions. The rebuilt argument-score files each cover all 150 gold IDs with 168 answers each. Primary full-graph counts are robust to speaker-level tie checking. The grounded degeneration is accurately disclosed, not a hidden labelling bug. The integer-program substitution, new generators/scorers, Haiku's one-pass collection and coarse stated scores, exploratory history, and limited sample are all disclosed limitations; matching 82/151 alone does not prove decision-level equivalence to Wu's AD3 implementation.

First reconcile tie policy and evaluation manifests. Then expose the simple equivalent baselines and separate relation ablations. Any new claim of an argumentation advantage should use a frozen development protocol, fresh meetings or speakers, and prediction-level paired uncertainty. Current evidence is sufficient for the bounded conclusion that these saved argument pipelines demonstrate no reliable advantage over direct questioning; the stronger introduction claim that graphs “do not improve ... for any ... models” should be softened, since Haiku reasons-only and preference grounded each exceed Haiku direct by 5.3 points in the reported table.

**Ready for round-2 discussion:** yes. Main challenges to test with the other auditors are the scope of the negative graph conclusion, whether attribution comparisons isolate a single intervention, and whether expanded report checks should be required before publication.
