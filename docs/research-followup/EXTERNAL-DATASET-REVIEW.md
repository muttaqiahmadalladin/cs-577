# External role and dominance data review

Verified 2026-11-17 against primary sources and the downloadable DOME files. Scope: replace manual collection of **role/power labels**; evidence-support calibration is a separate task. MISeD and QMSum evidence annotations are being evaluated separately.

## Recommendation

Use **AMI assigned project-manager roles** for a larger, fresh institutional-role benchmark. Add **DOME** as a small, separately reported human-perceived-dominance diagnostic. Neither supplies gold judgments that an argument's quotation supports its particular claim or that a rebuttal answers its target. Do not train an evidence checker by relabeling roles/dominance as evidence validity.

| Candidate | Existing ground truth and access | Practical decision |
| --- | --- | --- |
| AMI scenario meetings | Participants are assigned project manager, industrial designer, interface designer, or marketing roles. Official manual transcripts/metadata are downloadable; manual archive v1.6.2 is listed as 22 MB, CC BY 4.0. | Best readily available replacement for institutional-role evaluation. Assigned role is an experimental fact, **not** an independent judgment of behavioral power. |
| DOME, AMI subset | Three humans rank four participants' perceived dominance in five-minute segments; actual linked files contain 58 segments. Small public semicolon-separated files require no credentials. | Best directly verified human-labeled behavioral-power supplement; too few independent groups for a strong confirmatory training/test study. |
| PAVIS Leadership Corpus | Official site reports 16 meetings/64 participants, most/least emergent leader and leadership-style annotations. | Not immediately usable: signed institutional request followed by credentials; official contents list audio/video and manual diarization but do not establish a released textual transcript. Research-only access. |
| Enron power/hierarchy | Columbia release documents email, thread, entity and organizational hierarchy structures and a BSON/MongoDB restore workflow. | Alternative modality with substantial preprocessing. This bounded review did not verify a currently downloadable, explicitly licensed package of the *human perceived-power* annotations; do not treat the generic Enron email download as that annotation set. |

Sources: [AMI overview](https://groups.inf.ed.ac.uk/ami/corpus/overview.shtml), [AMI download](https://groups.inf.ed.ac.uk/ami/download/), [DOME documentation](https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/DOME_documentation.pdf), [PAVIS access and contents](https://pavis.iit.it/leadership-corpus), [Columbia Enron overview](https://www.cs.columbia.edu/~rambow/enron/), [Enron restore instructions](https://www.cs.columbia.edu/~rambow/enron/Setup.html).

## DOME: verified artifact, historical-document discrepancy

Download the [rankings](https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/dome_annotations_M1.csv) and [subset flags](https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/dome_dataset_M1.csv). Current files have 58 data rows each, across 11 meetings and five session prefixes (`IS1000`, `IS1001`, `IS1003`, `IS1006`, `IS1008`). Recomputing agreement from rankings reproduces all flags:

| Task | All three agree | At least two agree |
| --- | ---: | ---: |
| Most dominant | 34 | 56 |
| Least dominant | 31 | 54 |

The PDF describes 125 segments and larger counts (67/71 full, 121/117 majority); these are **not** the contents of the two currently linked `_M1` downloads. No missing subset was verified. The 58 windows total 285.65 annotated minutes (some terminal windows are shorter than five minutes).

Rankings schema: `name;start (sec);end (sec);A11;...;A14;A21;...;A24;A31;...;A34`. `Axy` means annotator x, person y; rank 1 is highest and 4 lowest. Flags schema: `name;start (sec);end (sec);FMD;FLD;MMD;MLD`. Strip leading whitespace from meeting IDs before joining. The first segment is `IS1000a`, 0–300 seconds, with all three rankings `(4,1,3,2)`.

**Critical join:** DOME person numbers are closeup-camera IDs, not transcript letters. Resolve through AMI `corpusResources/meetings.xml`, which maps channels/cameras to participant IDs and scenario roles; [official participant documentation](https://groups.inf.ed.ac.uk/ami/corpus/participantids.shtml). Never assume person 1 = speaker A. Participant IDs permit explicit leakage checks. Keep all sessions of each group together, then verify actual participant disjointness; no official train/dev/test split was established in this review.

Limits: rankings were collected from multimodal meetings, so a text-only experiment predicts multimodally perceived dominance. Public availability is verified, but DOME's standalone license is not explicit: AMI's download page says **some** annotations are CC BY 4.0. Check its exact redistribution coverage before vendoring DOME. Referencing original download URLs avoids claiming a license that was not verified.

Local inspected artifacts: ignored `work/dataset-research/`. SHA-256 rankings `32ad863958306e85f02fa96b6a0da73c3b9aa6f49f667415d85a23dad4b91c17`; flags `1b596e64f5329da5376582478b5455161589419e68f93a4abf9c215f56315454`. No model calls, annotation fabrication, access requests, or media downloads were performed.

Confidence: **verified** for URLs, schema, downloaded counts and agreement; **unresolved** for complete historical DOME release, DOME redistribution license, and a sufficiently powered participant-disjoint split.

## Evidence-grounding datasets (replacing manual CSV evidence judgments)

| Candidate | Existing ground truth and access | Practical decision |
| --- | --- | --- |
| Google BEGIN (`google/BEGIN-dataset`, commit `6e65f0d5a1ed1b9574643a7640ff1678d4e979b5`) | Human three-way attribution labels (`Fully attributable`, `Not fully attributable`, `Generic`) across 1,229 official `dev` rows and 11,059 `test` rows (`cmu-dog`, `topicalchat`, `wow`). Public TSVs with domain licenses/notices. | **Selected** for calibrating/evaluating evidence-grounding checkers on `dev` while keeping `test` held out. See [VALIDATED-DATASET.md](VALIDATED-DATASET.md). |
| MISeD WOZ (`google-research-datasets/MISeD`, commit `870d1aaf1063193d508e0224b86e011f921fd262`) | 70 manual information-seeking dialogues across 35 meetings (700 turns; 617 with transcript span attributions). | Inventoried in [`results/external_evidence/woz_inventory.json`](../../results/external_evidence/woz_inventory.json). Useful for positive span-attribution checks after excluding the 4 overlapping DOME `IS1003` meetings (`62` remaining dialogues), but lacks validated unsupported-claim negatives and has 49 range records with omitted `startIndex` endpoints. |
