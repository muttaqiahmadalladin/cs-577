# Validated external dominance benchmark

The active external benchmark uses **existing human DOME rankings**, joined to the official AMI manual transcripts. No new manual labeling CSV is required to construct these dominance labels. The importer has fetched and built the current official files locally: **58 windows, 34 unanimously most-dominant windows, and 102 top-versus-challenger pairs**, with 20 participants across five independent participant groups. A/B gold labels are counterbalanced 51/51.

This changes the prediction target to **human-perceived dominance**. It does not validate professor identity, assigned organizational role, the evidential support of an argument, or whether a rebuttal answers its target. Those targets must be evaluated separately. This is a small benchmark/calibration candidate; no model training or validation performance is claimed.

## Reproduce

From this repository root, using Python 3.9 or newer and the standard library:

```sh
python3 scripts/dome_dataset.py fetch
python3 scripts/dome_dataset.py build
python3 -m unittest discover -s tests -p 'test_dome_dataset.py' -v
```

`fetch` is the explicit network operation. It downloads the official rankings, flags, and manual annotation archive to ignored `sources/external/`, checks pinned SHA-256 hashes, and reuses existing matching files. A changed upstream artifact fails validation rather than silently changing the benchmark. `build` is offline and performs no model calls. Existing paths can be supplied with `--rankings`, `--flags`, and `--ami`.

The [aggregate manifest](../../results/external_dome/manifest.json) records source URLs/hashes, all counts, split rules, source exclusions, export hashes, and limitations. Raw labels, participant crosswalks, and transcript examples remain in ignored `work/external_dome/`:

| Local file | Contents |
| --- | --- |
| `diagnostic_windows.jsonl` | All 58 windows, three original rank permutations, agreement flags, exact camera/participant joins and transcript windows |
| `primary_windows.jsonl` | All 34 windows where all three annotators choose the same most-dominant person; includes mapped four-way gold |
| `dominance_pairs.jsonl` | 102 binary focal comparisons, with separate `prompt_input`, `gold`, and `provenance` objects |
| `pair_inputs.jsonl` | Only the 102 model inputs; no gold labels, rank arrays, meeting identities, original participant IDs, or roles |
| `text_evaluable_pairs.jsonl` | Predeclared secondary subset: 90 pairs from 30 windows with lexical speech by every participant |

The output location is restricted to repository `work/` so the conversion command does not accidentally publish derivative raw data.

## Identity and transcript validation

DOME persons 1–4 denote **closeup-camera numbers**. The importer resolves these through `corpusResources/meetings.xml` to transcript agents and global participant IDs. It never assumes camera 1 means speaker A. For example, in `IS1003b` camera 1 maps to transcript speaker C. Camera mappings must be complete, one-to-one, and accompanied by all four word files; malformed or missing mappings/files fail the build.

CSV headers and values are stripped before joining the exact `(meeting, start, end)` keys. Duplicate or misaligned keys, nonfinite/reversed bounds, non-permutation rankings, nonbinary flags, and flags inconsistent with the three rankings fail validation. Recomputed agreement totals are:

| Target | All three agree | At least two agree |
| --- | ---: | ---: |
| Most dominant | 34 | 56 |
| Least dominant | 31 | 54 |

Transcript windows use the half-open rule `window.start <= word.start < window.end`. Only timed `<w>` tokens are included; non-speech XML events are excluded. Words are ordered by their source start times, consecutive same-speaker words are grouped, punctuation is preserved, and turn end times are clipped to the window. Speech text is retained without synthesizing utterances. Role/identity metadata is omitted from model inputs; a participant's spoken references to roles or names remain ordinary transcript text.

Each full-agreement top participant is compared against each of the other three people. The entire four-person conversation remains visible. The focal pair is relabeled A/B and the remaining speakers C/D. IDs hash the window and **unordered camera pair**; neither the human winner nor its assigned A/B label enters the ID. Candidates are ordered by these stable IDs and winner-side placement alternates deterministically. Ranks, mapped source identities and gold are stored outside `prompt_input`. Models must consume `pair_inputs.jsonl`, or explicitly extract only `prompt_input`.

Four full-agreement windows contain a mapped participant with no lexical speech. All four metadata/word-file sources exist. These windows remain in the canonical 34-window/102-pair benchmark; silence may itself be relevant to dominance. The input's four-person `participant_roster` gives exact lexical word counts, including zero, without inventing a silence utterance. The secondary 30-window/90-pair subset selects on coverage alone and should be reported separately.

## Frozen participant-disjoint split

All sessions of each meeting-prefix group stay together. Groups sharing any global participant are connected into a single component before splitting. Components are sorted by the SHA-256 of their sorted group IDs joined by `|`: the first becomes dev, the second test, and all remaining components train. This rule is deterministic and uses no model outcome. Fewer than three independent components would produce an explicit blocked split state.

| Split | Participant groups | All windows | Full-agreement windows | Canonical pairs | Secondary pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train/calibration | 3 | 34 | 19 | 57 | 54 |
| Dev | 1 | 5 | 4 | 12 | 12 |
| Test | 1 | 19 | 11 | 33 | 24 |

The actual global participant sets are disjoint across these splits. **Five groups is the effective independent scale**; 102 related pairs do not constitute 102 independent meetings. This split supports a small exploratory external check, not a strong confirmatory training/test claim. If train/calibration examples are used to select a method, dev/test labels must stay held out.

## Provenance and limits

Primary downloads: [DOME rankings](https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/dome_annotations_M1.csv), [DOME subset flags](https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/dome_dataset_M1.csv), [AMI manual archive](https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip). Annotation interpretation follows [DOME documentation](https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/DOME_documentation.pdf) and [AMI participant/camera documentation](https://groups.inf.ed.ac.uk/ami/corpus/participantids.shtml). See the [source review](EXTERNAL-DATASET-REVIEW.md) for alternatives.

The DOME PDF describes 125 segments. The currently linked `_M1` files contain **58**, totaling 285.65 annotated minutes. The importer does not invent or infer the missing historical portion. The archive filename says `1.6.2` while its internal README says release `1.7`; the recorded SHA-256 identifies the exact bytes used.

DOME raters used audio/video. A text-only model therefore predicts a judgment made with additional modalities. The AMI archive contains a CC BY 4.0 license, while coverage of the separately served DOME annotation files remains unverified. Consequently this repository publishes code and aggregate provenance only; raw DOME labels and converted transcript examples are fetched/generated locally and remain ignored. Cite the official DOME documentation and AMI corpus when reporting results, and resolve DOME's exact redistribution terms before releasing the derived examples.

## Validated external evidence-grounding benchmark (Google BEGIN)

To replace manual CSV annotation for **evidence-support calibration**, [`scripts/begin_dataset.py`](../../scripts/begin_dataset.py) imports Google's [BEGIN benchmark](https://aclanthology.org/2022.tacl-1.62/) (`google/BEGIN-dataset`, pinned commit `6e65f0d5a1ed1b9574643a7640ff1678d4e979b5`), where humans labeled whether generated dialogue responses are grounded in their supplied source text (`Fully attributable`, `Not fully attributable`, or `Generic`).

```sh
python3 scripts/begin_dataset.py fetch-build
python3 -m unittest discover -s tests -p 'test_begin_dataset.py' -v
```

The offline build verifies all 14 pinned source/license files and exports aggregate provenance to [`results/external_begin/manifest.json`](../../results/external_begin/manifest.json) while keeping raw/derived examples in ignored `work/external_begin/`:

| Split | `cmu-dog` | `topicalchat` | `wow` | Total | Intended use |
| --- | ---: | ---: | ---: | ---: | --- |
| `dev` | 416 (59 full / 278 not-full / 79 generic) | 383 (74 / 307 / 2) | 430 (180 / 250 / 0) | **1,229** | Evidence-checker calibration only (includes frozen 12-item class-balanced pilot) |
| `test` | 3,607 (508 / 2,442 / 657) | 3,845 (677 / 3,128 / 40) | 3,607 (1,392 / 2,209 / 6) | **11,059** | Held-out evaluation after freezing calibration |

Key verified properties in `results/external_begin/manifest.json`:

- **Label semantics:** `fully_attributable` maps to `supported`, `not_fully_attributable` maps to `not_fully_supported`, and `generic` maps to `abstain` (never conflated with supported evidence).
- **Opening turns:** 9 official rows (`2` in `cmu-dog/dev`, `6` in `cmu-dog/test`, `1` in `topicalchat/test`) have an empty prior-turn `message` field while retaining non-empty `knowledge`, `response`, and human labels.
- **Dev/test overlap diagnostics:** `0` exact full-input (`knowledge + message + response`) matches between `dev` and `test`, but `496` shared unique `knowledge` passages (`1,098` dev rows / `7,290` test rows) and `157` shared `(knowledge, message)` pairs. Calibration and held-out claims must account for shared background passages.
