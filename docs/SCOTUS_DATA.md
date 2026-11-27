# SCOTUS OT2026 post-cutoff conversational power dataset

This directory and [`data/scotus_ot2026/`](../data/scotus_ot2026/) add a fresh, post-training-cutoff evaluation set and the perturbation / precision-recall tools requested in the post-PR #2 advisor review.

## Why this dataset exists

1. **Pretraining contamination cannot be ruled out on ICSI by choosing an older LLM.** The ICSI Meeting Corpus (2000–2002) has been public for two decades, and Wu et al.'s `meeting.csv` has been on GitHub since 2025. The 30 unused ICSI meetings contain no new professor + known non-professor focal pair.
2. **Every dialogue here was heard and first published between 2026-10-05 and 2026-11-10** (October Term 2026 of the U.S. Supreme Court). The dialogue text cannot appear in any pretraining corpus with a cutoff before 2026-10-05.
3. **Speaker attribution and institutional power labels are official facts.** Heritage Reporting Corporation's same-day transcripts label every turn (`CHIEF JUSTICE ROBERTS:`, `JUSTICE KAGAN:`, `MR. WESSLER:`, `GENERAL PRELOGAR:`), and the `APPEARANCES` page lists every advocate. A Justice holds the higher institutional role; an advocate arguing before the Court holds the lower role. This is the same institutional-power operationalization used by Danescu-Niculescu-Mizil et al. (2012, *Echoes of Power*, WWW).

## Sources

All 13 oral argument transcripts posted on `supremecourt.gov` for the October and November 2026 sittings as of 2026-11-27 (public domain U.S. government works). Exact URLs and SHA-256 checksums are pinned in [`scripts/build_scotus_dataset.py`](../scripts/build_scotus_dataset.py) and [`data/scotus_ot2026/manifest.json`](../data/scotus_ot2026/manifest.json). Raw PDFs are downloaded into ignored `sources/scotus_ot2026/`.

| Docket | Case | Argument date | Split | Turns | Snippets |
| --- | --- | --- | --- | ---: | ---: |
| `25-170` | Suncor Energy (U.S.A.) Inc. v. Commissioners of Boulder County | 2026-10-05 | test | 427 | 29 |
| `25-735` | Johnson v. United States Congress | 2026-10-05 | dev | 334 | 28 |
| `25-498` | Anderson v. Intel Corp. Investment Policy Committee | 2026-10-06 | test | 243 | 20 |
| `25-579` | Department of Air Force v. Prutehi Guahan | 2026-10-07 | test | 370 | 31 |
| `25-5343` | Beaird v. United States | 2026-10-13 | test | 496 | 31 |
| `25-459` | Salazar v. Paramount Global | 2026-10-14 | test | 286 | 29 |
| `25-5930` | Maxwell v. Dinis | 2026-11-02 | dev | 209 | 19 |
| `25-352` | Younge v. Fulton Judicial Circuit Dist. Attorney's Office | 2026-11-02 | dev | 272 | 23 |
| `25-581` | St. Mary Catholic Parish v. Roy | 2026-11-03 | test | 428 | 30 |
| `25-1003` | Guerrero v. Johnson | 2026-11-04 | test | 197 | 18 |
| `25-417` | Nielsen v. Watanabe | 2026-11-09 | test | 349 | 26 |
| `25-159` | Hoffmann v. WBI Energy Transmission, Inc. | 2026-11-09 | test | 196 | 18 |
| `25-966` | Department of Labor v. Sun Valley Orchards, LLC | 2026-11-10 | test | 383 | 31 |

**Totals:** 333 snippets across 13 cases (70 `dev` across 3 cases; 263 `test` across 10 cases). All nine Justices appear as the focal Justice (`Roberts` 9, `Alito` 21, `Thomas` 23, `Barrett` 42, `Gorsuch` 45, `Sotomayor` 45, `Kagan` 47, `Kavanaugh` 47, `Jackson` 54). The 3 `dev` cases share **zero advocates** with the 10 `test` cases.

## How the dataset is built

Run `python3 scripts/build_scotus_dataset.py --download` (or `--check` to verify byte-for-byte reproducibility against the committed files).

1. **Transcript extraction.** Keep only lines between `Official - Subject to Final Review` and `Heritage Reporting Corporation` on each page; stop at `(Whereupon, ... the case was submitted.)`.
2. **Turn parsing.** Split at reporter headers (`CHIEF JUSTICE X:`, `JUSTICE X:`, `MR./MS./MRS./GENERAL/DR. X:`). Normalize reporter header typos against the `APPEARANCES` block (e.g. `MR. FEIGN:` → `MR. FEIGIN:`, `MR. HAMMACH:` → `MR. HAMMACK:`). Remove stage directions such as `(Laughter.)`.
3. **Procedural turn filter.** Exclude advocate opening statements containing `"may it please the Court"` and short Chief Justice transitions (`"We will hear argument..."`, `"Thank you, counsel."`, calling on each Justice in seriatim questioning, `"The case is submitted."`).
4. **Dyadic snippet extraction.** Find maximal non-overlapping runs of consecutive non-procedural turns within one argument section in which **exactly one Justice and the advocate at the lectern** speak. Keep runs with $\ge 4$ turns, $\ge 2$ turns per speaker, and $\ge 40$ words; take the first 6 turns (matching the ICSI 6-turn median). Non-overlapping extraction guarantees that no two `turns_same_span` snippets share a turn.
5. **Focal-only extended context (`turns_pm15`, `turns_pm60`).** Because an advocate faces up to nine Justices across an hour, keeping third-party `C..I` turns in $\pm 15 / \pm 60$ windows would trivially identify the advocate as the one person who answers everyone else. Extended windows therefore retain only turns by the two focal speakers `A` and `B` within $\pm 15$ or $\pm 60$ transcript turns.
6. **50/50 letter assignment.** A seeded shuffle (`seed = 2026`) assigns the Justice to `A` in 166 of 333 snippets (49.8%) and to `B` in 167.
7. **Role and identity masking (`snippets_masked.jsonl`).** Both raw and masked versions are committed:
   - Mention of the focal speaker `A` or `B` by title+name (`Justice Kagan`, `Mr. McCloud`, `General Prelogar`) → `Speaker A` / `Speaker B`.
   - Mention of any other current Justice or advocate by title+name or bare surname → `[PERSON]` (with a case-citation guard so precedent names such as `in Thomas` or `Jackson v.` are preserved).
   - Forms of address (`Your Honor`, `Mr. Chief Justice`, vocative `Counsel,`, `General,`, `Justice,`, `Chief?`) → `[ADDRESS]`.
   - Any `"may it please the Court"` clause in extended context → removed.
   - Automatic leak verification checks both `turns_same_span` and all context windows for remaining current-Justice titles, vocative `Chief`/`Counsel`, `Your Honor`, `"may it please the Court"`, and non-case-citation participant surnames. All six counts are **0** (recorded in `manifest.json`; the builder exits non-zero if any leak remains).

## Schema

Matches [`data/icsi_rebuilt_snippets.jsonl`](DATA.md) so existing evaluation scripts work unchanged (`professor` holds the gold high-power letter `A` or `B`):

| Field | Meaning |
| --- | --- |
| `id` | `scotus-<docket>-<start_turn>` (e.g. `scotus-25-170-0006`) |
| `meeting` | Supreme Court docket number (`25-170`); used as the cluster ID for bootstrap CIs |
| `case`, `argument_date` | Full case name and ISO argument date (`2026-10-05` .. `2026-11-10`) |
| `split` | `dev` (3 cases, 70 snippets) or `test` (10 cases, 263 snippets), advocate-disjoint |
| `speakers` | `{"A": "<reporter header>", "B": "<reporter header>"}` (metadata only; never shown to models) |
| `roles` | `{"A": "justice"\|"advocate", "B": "justice"\|"advocate"}` |
| `professor` | Gold higher-power letter (`"A"` or `"B"`), named `professor` for drop-in compatibility with the ICSI evaluator |
| `turns_same_span`, `turns_pm15`, `turns_pm60` | Lists of `{"speaker": "A"\|"B", "text": "..."}` |
| `masked` | `true` in `snippets_masked.jsonl`, `false` in `snippets_raw.jsonl` |

## Simple baselines and limitations

Running `python3 scripts/perturb_and_metrics.py --baselines` on `snippets_masked.jsonl` (`turns_same_span`):

| Baseline | All (333) | Dev (70) | Test (263) | Note |
| --- | ---: | ---: | ---: | --- |
| Always `A` | 49.8% | 51.4% | 49.4% | By construction (seeded 50/50 split) |
| More words | 48.3% | 50.0% | 47.9% | Unlike ICSI (where professors speak more: 66.7%), advocates speak slightly more than Justices |
| Shorter turns | 51.4% | 50.0% | 51.7% | Near chance |
| **More `?` questions** | **86.8%** | **85.7%** | **87.1%** | Justices ask questions; advocates answer them |

**Important caveat for interpretation:** in oral argument, questioning *is* the institutional role behavior, so a simple question-mark heuristic reaches 87.1% on test while word-count heuristics fail (47.9%, the reverse of ICSI). Any LLM evaluation on this set must therefore be compared against **both** the 49.4% majority baseline and the 87.1% question-mark heuristic, and paired with the ICSI perturbation suite in [`scripts/perturb_and_metrics.py`](../scripts/perturb_and_metrics.py) (`no_commas`, `extra_commas`, `no_punct`, `no_disfluencies`, `lowercase`, `letter_swap`).
