# Round-2 methodology discussion

2026-11-16. Read both independent peer reports after completing the independent methodology pass. Round-1 reports remain unchanged. This record incorporates direct messages exchanged with the implementation and statistics reviewers; it does not invent responses. Parent reports the full 12-step offline replay passed with all 369 tracked files byte-identical.

## Claim, challenge, response, and revised position

### Inert similarity: inherited architecture or new bug?

**Challenge sent to implementation:** Their I1 proof and matching upstream rules establish an inherited structural restriction. Is “high for mechanism claims” warranted when the report already acknowledges little relation impact and equality with a plain sum? Also, GLM's result changes when relations are added, so “relations are inert” would overgeneralize.

**Peer response:** Agreed to reduce I1 to **medium interpretation/scope**, explicitly **not a new implementation defect**. Similarity alone is inert. Contradiction remains active: GLM falls from 106 correct with rebuttals to 104 with all relations. The inherited repeated style-A pair changes no primary predictions when corrected.

**Revised position:** Retain the algebraic similarity finding and simplest equivalent baselines. They explain why parts of the evaluated graph cannot test a useful similarity mechanism. Do not call the entire graph inert, suggest wrong headline accuracy, or treat faithful upstream architecture as a newly introduced bug. New architecture would be a new method requiring separate development and evaluation.

### Does “no graph benefit” warrant high severity?

**Challenge sent to statistics:** Its high-severity negative-headline finding concerns an overstrong abstract/contribution, while the discussion explicitly says no evidence of benefit and acknowledges inadequate sensitivity to small effects. Is there evidence beyond headline prominence supporting high severity?

**Peer response:** Agreed to revise **high → medium**. This is a wording/inference repair, not a refutation of the bounded “no demonstrated benefit” result.

**Revised position:** All reviewers preserve the descriptive counts and accept “no demonstrated improvement among the evaluated implementations.” They reject equivalence or a general failure of argumentation. Positive observed differences, including Haiku/Jev 73.3% versus direct Haiku 68.0%, must remain visible. Clustered paired uncertainty is needed to show what improvements are still compatible with the data. Passing reproduction does not turn nonsignificance into equivalence.

### Do eight changed gold letters explain the attribution improvement?

**Challenge sent to statistics:** Changed letters can require semantic recoding; calling that a confound must not imply it explains away the gain. Their own invariant 128-case sensitivity analysis strongly supports attribution.

**Peer response:** Agreed. This is semantic recoding inherent to reconstruction, not evidence of biased gains. Applying rebuilt gold to unchanged released predictions adds only two correct cases; the overall observed improvement is 35. The 128 invariant cases remain decisive.

**Revised position:** Keep the combined all-150 reconstruction result and lead the attribution explanation with the invariant-letter/gold subset: 63→90 correct, 42 wins/15 losses, positive meeting-bootstrap interval. Avoid treating 2/35 as a formal additive causal decomposition, since gold recoding and changed predictions interact. My M5 remains low severity: improve the description and controlled sensitivity analysis. Any batching effect remains untested; it is not an established explanation.

### Challenge to my role-versus-power severity

**Challenge received from both peers:** M2's high severity is disproportionate because the proxy is inherited and the title, abstract, and contribution foreground professor identification. Does the issue invalidate the task results, or mainly bound their interpretation?

**Response sent:** Agreed to revise **high → medium construct/scope threat**. The professor-role classification result remains valid. Consistent professor/non-professor terminology and identical cross-model prompts are immediate repairs. Independent behavioral-power annotations are needed for a broader claim, not to preserve the bounded role-classification result.

**Revised position:** No claim that the paper's core result collapses. The student assertion is still unsupported universally, including three Postdoc cases, and role-framed Jev versus power-framed direct LLM prompts remain a comparison limitation.

### Challenge to my alternative-mapping finding

**Challenge received from both peers:** The reported 69/128 is valid for the literal “letter carrying most professor words” statistic. Preserve that and the conditional 57.6%; correct only the claimed majority-speaker mapping.

**Response sent:** Agreed. Both displayed letters have the same majority real speaker in 86/128 cases, so that reading generally cannot define two distinct people. The 69/128 calculation and last-line-conditioned 57.6% remain correct.

**Revised position:** M1 survives as a medium explanatory error. It does not establish a wrong underlying corruption count. The central mixed-speaker finding and exact dataset reconstruction survive independently.

## Remaining boundaries

No peer dispute remains on the above points. Broad power validity, context mechanism, generalization to new speakers, model training contamination, and any effect of co-batched questions remain unmeasured. The last two are hypotheses, not findings. The statistics review's 22% judge decision instability supports a wording correction; a same-order repeat control is needed to attribute instability specifically to case order. Offline reproducibility validates stored-output arithmetic, not historical collection equivalence or behavioral-power construct validity.

## Top three next steps

1. **Repair claim scope and analysis descriptions:** use “no demonstrated benefit,” preserve observed improvements, correct the majority-mapping explanation, use professor/non-professor consistently, and describe judge accuracy stability separately from decision stability. Record inherited inert similarity explicitly.
2. **Complete the controlled evidence package from existing outputs:** add the invariant 128-case attribution comparison and clustered intervals for primary graph/judge differences; reconcile evaluation manifests and deterministic objective ties; expose simple equivalent graph baselines. No new model collection is needed for these repairs.
3. **Freeze a prospective experiment:** identical target prompts and letter-swap controls, controlled context ablations, multiple generations/orders, and untouched speaker-disjoint data. Add independent behavioral-power annotations if retaining the broader power interpretation. Design any altered graph on development data before testing it.

**Handback:** Initial cross-review complete; all requested peer exchanges received and answered. Ready for parent consolidation.
