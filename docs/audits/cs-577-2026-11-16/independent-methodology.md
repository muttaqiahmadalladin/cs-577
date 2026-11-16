# Independent methodology and construct-validity audit

Audited commit: [`2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa`](https://github.com/muttaqiahmadalladin/cs-577/tree/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa). First pass, 2026-11-16; conducted without other reviewers’ findings. Read-only inspection of report, builder, prompts, analyses, stored outputs, and downloaded primary corpus inputs. No model calls. Severity concerns the scientific claim, not deployment security.

## Assessment

The central artifact finding survives: the released conversations mix real participants under displayed letters, and repairing attribution produces a substantial improvement on this selected benchmark. The repository supports an empirical conclusion about **professor identification in these ICSI snippets**. It does not establish general conversational-power recognition, isolate why added context helps, or demonstrate that argumentation has no benefit. Most threats are disclosed, but some headline wording outruns those disclosures. One alternative-mapping explanation is demonstrably incorrect.

## Findings

### M1 — Medium; proven analytical-description error: “majority speaker” does not define the proposed alternative mapping

**Location:** [report/report.tex:150–156](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L150), [docs/DATA.md:27–30](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/docs/DATA.md#L27), and [scripts/analyze.py:119–125](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/analyze.py#L119).

**Evidence/reproduction:** Aggregate corpus word counts separately for displayed A and B using `released_turns()` and located MRT segments; executable recipe below. In **86/128** snippets both letters’ majority speaker is the *same person*, with no majority ties. Only 42 yield distinct majority speakers; their released label identifies the professor in 33 cases. Example ID 0: A contains 86 professor words and 5 other words; B contains 4 professor words and 3 other words. Both majority mappings point to the professor. The reported 69/128 instead asks which letter contains **more of the professor’s words**; that is a different calculation.

**Consequence:** The claimed second “reading” is generally not a bijection between two letters and two people. Its 69/128 statistic cannot be interpreted as label accuracy under such a mapping. The conditional 57.6% under the last-line mapping remains correct. For perspective, choosing the better of the two focal-speaker orientations separately per snippet leaves 3,706/13,185 words misplaced (28.1%), counting third-speaker words as misplaced under either orientation. Thus 57.6% should retain its explicit conditional qualification.

**Correction:** Replace the second-reading explanation with the literal 69/128 statistic; separately report the 86 ambiguous majority assignments. Prefer a per-letter speaker confusion table and the minimum error under either bijection. **Confidence: high.** Counterargument: the abstract already qualifies 57.6%, and mixed-speaker corruption remains directly demonstrable; this does not overturn the central discovery.

### M2 — High; construct-validity threat: institutional role is the label, conversational power is unvalidated

**Location:** [report/report.tex:56–58](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L56), [174–181](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L174), [scripts/build_dataset.py:38–39](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/build_dataset.py#L38), [105–115](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/build_dataset.py#L105), and [scripts/wu_pipeline.py:51–52](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/wu_pipeline.py#L51).

**Evidence/reproduction:** `load_education()` plus the committed `speakers`/`professor` fields confirms labels are generated from the metadata value `Professor`; no independent power annotation enters the builder. The non-professor is classified as PhD in 117 cases, Grad in 30, and Postdoc in 3. Jev receives the assertion that the other person is a student and is asked to identify the professor. GLM/Terra direct prompts ask who has more power without this role assertion.

**Consequence:** Accuracy measures agreement with institutional-role metadata, not observed dominance, decision authority, expertise, or perceived power in the excerpt. “PhD” does not establish current student status; “Postdoc” particularly undermines the universal student assertion. Comparisons across direct Jev and LLMs also vary the task framing. A successful role classifier need not be a valid power classifier.

**Correction/experiment:** Describe the target consistently as professor versus non-professor. Run every model under both identical role-identification and identical behavioral-power prompts. Obtain blinded human annotations of behavioral power, with uncertain/tied cases permitted, and compare their agreement with role labels before making the broader claim. **Confidence: high for target mismatch; unknown magnitude of performance effect.** Counterargument: professor-as-higher-power is inherited from the original benchmark, so the experiment remains a legitimate correction and reevaluation of that operationalization. The title and much of the report already emphasize speaker attribution and professor identification.

### M3 — Medium; inferential overstatement: absence of detected improvement is not evidence of no improvement

**Location:** [report/report.tex:50](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L50), [83](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L83), [309–348](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L309).

**Evidence/reproduction:** Read Table 3 and the corresponding stored counts in `results/report_numbers.json` and `results/grounded_results.json`. Haiku arguments with Jev scoring reach 73.3% for reasons-only and the preference grounded extension, versus 68.0% for direct Haiku. Full Haiku/Jev inference reaches 70.0%. Rebuttals improve the Terra graph from 66.7% to 72.0%. These are numerical improvements even though the reported paired comparisons do not establish a reliable gain. The original GPT-3.5 generation/scoring configuration is not rerun; two modern runs replace the scorer with Jev and Haiku generation is one-pass.

**Consequence:** “Do not improve … for any of three” is stronger than the evidence and literally inaccurate as an unqualified numerical statement. There is no equivalence/noninferiority analysis or prespecified smallest meaningful gain. The 150 dependent excerpts also limit precision. These experiments assess particular implementations and model/scorer combinations, rather than argumentation generally or a controlled replication of the original pipeline.

**Correction/experiment:** Use the report’s better sentence, “We find no evidence … adds accuracy,” throughout, qualified by tested configurations. Report clustered paired confidence intervals and a prespecified practical margin. Use identical target prompts, generator/scorer factorial comparisons, multiple generations, and a new untouched speaker-disjoint test set. **Confidence: high.** Counterargument: the discussion explicitly acknowledges low power; the negative finding is reasonable when phrased as failure to demonstrate a benefit, especially given the broad set of tested variants.

### M4 — Medium; disclosed sampling limitation with additional untested context mechanism

**Location:** [report/report.tex:175–181](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L175), [294–297](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L294), [352–380](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L352), and [scripts/grounded_policy_search.py:73–78](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/grounded_policy_search.py#L73).

**Evidence/reproduction:** Count committed dataset fields: four professors contribute 110, 23, 15, and 2 examples. Median text grows from 87 to 328.5 to 1,008.5 words. Third-party speech occurs in 3/150 original spans, 115/150 ±15 windows, and 148/150 ±60 windows. Using corpus offsets, original spans have no overlap; 27 same-meeting pairs overlap at ±15 and 75 at ±60. Meeting splits prevent this overlap from crossing their development/test boundary, but repeatedly reuse the same small set of people.

**Consequence:** The context intervention simultaneously changes length, third-party participation, role/identity evidence, and redundancy. A flat word-count baseline does not identify the mechanism of the model’s gain. Excluding the dominant professor is a useful robustness check, but the remainder still comprises only three professors, one represented twice; it does not establish broad speaker generalization. Meeting-level intervals do not capture uncertainty from sampling new professors. Training-data contamination is **unmeasured, not demonstrated**; “None … trained on the task” should mean “we did not fine-tune these models,” unless stronger provenance exists.

**Correction/experiment:** Keep the descriptive within-dataset context result. Add fixed-token-length neighboring versus unrelated-context controls, focal-speakers-only context, and masking of personal names/explicit status references. Collect additional independently selected speakers and corpora, then evaluate speaker-disjoint. **Confidence: high for sampling/intervention facts; moderate for their external-validity impact.** Counterargument: third-party cues are legitimate information if the intended task allows a surrounding meeting. Independent meeting-bootstrap checks using stored answers still support positive context gains: approximately +6.1 to +20.5 points for ±15 and +9.8 to +26.0 for ±60.

### M5 — Low; improve the controlled attribution contrast rather than discarding it

**Location:** [report/report.tex:175–178](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L175), [282–286](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/report/report.tex#L282), and [scripts/jev_collect.py:76–80,104–110](https://github.com/muttaqiahmadalladin/cs-577/blob/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa/scripts/jev_collect.py#L76).

**Evidence/reproduction:** Join arm 1 and fixed arm 4 by ID and stratify `letters_from_released`. The full contrast changes eight gold letters among 22 reassigned snippets and changes the co-batched question set from 20 to 28 questions. On the **128 retained-letter cases**, however, gold is unchanged and Jev rises from 63/128 to 90/128, with 42 wins versus 15 losses. An independent meeting bootstrap gives roughly +9.5 to +32.6 points.

**Consequence/correction:** The all-150 comparison is a valid before/after reconstruction comparison, but “only who is shown saying them differs” omits changed gold coding and request composition. Lead the causal attribution argument with the unchanged-gold subset and rerun both conditions with the identical minimal question payload and letter swaps. Whether co-batching affects Jev is **unknown**, not a proven confound. **Confidence: high for design differences; low for any batching effect.** The subset result strongly supports the central explanation despite this qualification.

## Reproduction notes and findings that survive

From the pinned checkout, a read-only rebuild using the parent’s separately downloaded, checksum-verified source directory:

```sh
python3 scripts/build_dataset.py --sources ../cs-577-2026-11-16-reproduction/sources --check
```

The majority-mapping check can be rerun without APIs or writes:

```python
import csv, collections, json, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
import build_dataset as b
src = Path('../cs-577-2026-11-16-reproduction/sources')
M = b.load_corpus(src)
R = list(csv.DictReader(open(src / 'meeting.csv')))
rows = json.load(open('../cs-577-2026-11-16-reproduction/work/rows.json'))
same = unique = correct = 0
for r in rows:
    if not r['consistent'] or len(r['profs']) != 1:
        continue
    turns, lines = b.released_turns(R[int(r['id'])]['conversation'])
    S = M[r['meeting']][r['start']:r['start'] + r['n']]
    C = {s: collections.Counter() for s in 'AB'}
    for letter, indices in turns:
        for i in indices:
            C[letter][S[i][1]] += len(lines[i].split())
    major = {s: C[s].most_common(1)[0][0] for s in 'AB'}
    if major['A'] == major['B']:
        same += 1
    else:
        unique += 1
        correct += major[R[int(r['id'])]['power']] == r['profs'][0]
print(same, unique, correct)  # 86 42 33
```

The corpus-aligned counts independently reproduce 7,596/13,185 misplaced words and 121/128 affected snippets under the stated last-line rule. Dataset construction drops only one single-participant case; it is not selective pruning of hard examples based on model success. Stored outputs reproduce Jev’s 107/150 and 134/150 correct at the original and longest spans. The concentration and exploratory history are explicitly disclosed. No evidence found here supports an allegation that the original paper’s humans necessarily saw these corrupted inputs; the repository properly leaves that unresolved.

**Next steps in priority order:** correct M1 and headline claim scope; report the unchanged-gold attribution comparison; unify role/power prompts and add letter-swap controls; run context-mechanism controls; commission an independently selected, speaker-disjoint benchmark with validated power annotations. Ready for round-2 reviewer discussion.
