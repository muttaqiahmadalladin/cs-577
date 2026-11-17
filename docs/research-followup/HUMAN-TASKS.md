# Optional manual-annotation fallback

**Current direction:** the user requested an existing, independently validated external dataset instead of manual CSV annotation. This document preserves the prepared fallback only; do not ask the user to fill these worksheets or treat them as the active next step. The external-data selection and suitability checks are coordinated separately. Existing worksheet bytes, including user formatting, must be preserved.

If the manual fallback is later explicitly chosen, two actual people independently check the clean evidence. An assistant, the quote model and the prior assistant-proxy audit cannot perform that independent validation. The prepared clean-bank study is exploratory; completed worksheets alone would not create a fresh confirmatory test set.

## 1. If the fallback is chosen, give each annotator only one worksheet

The organizer copies these two files into the ignored working directory, or sends each human their own CSV:

```sh
mkdir -p work/clean_quote_study
cp data/clean_quote_study/annotator_1.csv work/clean_quote_study/annotator_1_completed.csv
cp data/clean_quote_study/annotator_2.csv work/clean_quote_study/annotator_2_completed.csv
```

Annotator 1 edits only `work/clean_quote_study/annotator_1_completed.csv`; annotator 2 edits only `work/clean_quote_study/annotator_2_completed.csv`. If either working file already exists, preserve it instead of copying over it. Each has 96 items with the full clean same-span speaker-letter transcript in `transcript_json`. A spreadsheet program can edit the CSV; preserve UTF-8 and CSV quoting when saving. Use pseudonymous annotator IDs rather than personal identifying details.

Do not give annotators the answer key at `work/clean_quote_study/private_answer_key.json`, the participant crosswalk, model output files, evaluation results or the other person's answers. Ask them to avoid consulting the public role labels while annotating. The transcript and argumentative claims remain visible; inferable role cues within that material are legitimate evidence, not concealed metadata. Annotators must work separately before discussion.

## 2. Fill these columns on every row

Do not edit `argument_id`, `snippet_id`, `aspect`, `kind`, `intended_side`, `claim`, `paired_reason` or `transcript_json`. IDs identify the exact frozen claim. The intended side is the conclusion supported by the argument; a rebuttal's paired reason supports the opposite side.

| Column | What to enter |
| --- | --- |
| `annotator_id` | The same unique pseudonym on all 96 rows, distinct from the other human's. |
| `annotator_type` | Exactly `human`. |
| `quote` | A contiguous verbatim passage from one actual transcript turn supporting this particular claim. Preserve punctuation and spelling; no ellipses or joining different turns. Leave empty if none exists. |
| `quote_speaker` | The actual letter of the person who said that quote, including C/D/etc. where applicable. It may differ from `intended_side`. Leave empty if no quote exists. |
| `quote_present` | `yes`, `no` or `uncertain`: does the supplied passage actually occur verbatim in that speaker's turn? |
| `attribution_correct` | `yes`, `no` or `uncertain`: does the claim correctly attribute the quoted conduct, question, information or response to the person it describes? |
| `claim_supported` | `yes`, `no` or `uncertain`: does the quote support this specific claim, beyond merely sharing its topic? |
| `rebuttal_answers_reason` | For rebuttals: `yes`, `no` or `uncertain` for whether it answers the displayed paired reason. For reason rows this field may remain blank. |
| `should_keep` | `yes`, `no` or `uncertain`: your holistic judgment whether this is usable evidence for its specific argumentative claim. Judge evidence quality without checking the professor gold label or classification outcome. |
| `comment` | Optional short explanation, especially for ambiguity or rejection. Do not insert gold role labels, model judgments or other identifying information. |

`uncertain` is a completed judgment and remains separate in agreement reporting. Do not guess to remove uncertainty. For an absent quote, use `quote_present=no`, leave quote/speaker empty, and judge support/attribution honestly (`no` or `uncertain` as appropriate). A single short quotation may be insufficient to establish a claim about a larger interaction; use `uncertain` when you cannot fairly decide from the supplied evidence. The primary strict filter will reject uncertain required fields, but that policy must not dictate your independent `should_keep` judgment.

## 3. Measure agreement before discussing differences

From the repository root, run with the project's Python environment:

```sh
python scripts/clean_quote_study.py agreement \
  --first work/clean_quote_study/annotator_1_completed.csv \
  --second work/clean_quote_study/annotator_2_completed.csv \
  --out results/clean_quote_study/human_agreement.json
```

The currently committed pending report has **0/96 complete for each person**. The command reports completion and uncertainty separately, binary/three-valued agreement, kappa where defined and disagreement IDs. If the coordinator has a checker pilot, add `--predictions results/clean_quote_study/pilot/model_annotations.jsonl` to count false rejection of human-valid evidence and false acceptance of human-invalid evidence against each annotator. Partial pilot coverage is reported only for overlapping cases; it cannot establish a full-bank error rate.

After freezing the two independent originals and their hashes, have the humans discuss disagreements, or ask a third independent human to adjudicate. Preserve original answers; create a separate `work/clean_quote_study/adjudicated.csv` with the same IDs and comments describing the adjudication. Keep unresolved uncertainty as `uncertain`; the software does not invent consensus. Report original inter-annotator agreement before any adjudication. Calibrate a checker using development evidence judgments, without selecting by final role-label accuracy.

## 4. What these human actions unlock

Completed independent annotations unlock an evidence-quality/false-rejection audit of the sampled clean arguments. They do **not** supply annotations for the other 7,104 arguments. A full 150-snippet paired filter comparison requires valid quote annotations for all 7,200 fixed arguments (or a complete 48-argument set per explicitly scoped snippet); model collection can provide proposed judgments, with humans validating checker quality independently. The coordinator is responsible for the exact provider/model/key setup. The collection CLI defaults to dry run and is documented in [CLEAN-STUDY.md](CLEAN-STUDY.md).

A confirmatory improvement claim also requires genuinely new, independently labeled professors and nonprofessors, meeting/participant separation, a locked protocol and effect/precision target. Available ICSI archives offer 16 unused-meeting exploratory windows and a separate single-meeting new-professor packet, but no additional professor with an unseen **known nonprofessor** focal counterpart. The organizer must obtain another appropriately labeled corpus or new participants. The prepared Buw001 packet is professor-disjoint only and retains shared nonprofessor/context participants; it cannot satisfy an all-speaker-disjoint claim.
