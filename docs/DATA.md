# Data: the ICSI-rebuilt snippet set

`data/icsi_rebuilt_snippets.jsonl` holds 150 short professor and non-professor exchanges from the ICSI Meeting Corpus, each at three context lengths. It is built by `scripts/build_dataset.py` from public sources only, and the build is deterministic: `python3 scripts/build_dataset.py --check` rebuilds it and compares it byte for byte with the committed file.

## Sources

| File | What it provides | Where it comes from |
| --- | --- | --- |
| `meeting.csv` | The 151 released snippets (`conversation`) and their labels (`power`) | [kandicew/social-reasoning](https://github.com/kandicew/social-reasoning), commit `fed11b69765b4a398ce4a985adedfb65ec3098ab`, `data/meeting.csv` |
| `icsi_mrt.zip` | Original MRT transcripts: one `<Segment>` per utterance with start time, participant ID and text | [ICSI_original_transcripts.zip](https://groups.inf.ed.ac.uk/ami/ICSICorpusAnnotations/ICSI_original_transcripts.zip) |
| `icsi_core_nxt.zip` | `ICSI/speakers.xml`: education level of each participant | [ICSI_core_NXT.zip](https://groups.inf.ed.ac.uk/ami/ICSICorpusAnnotations/ICSI_core_NXT.zip) |

`python3 scripts/build_dataset.py --download` fetches all three into `sources/` (ignored by git).

## How the two sources are combined

1. **Parse the corpus.** Every MRT transcript (75 meetings) is read in file order. A segment is kept if it has a participant ID and at least one word after markup such as `<VocalSound/>`, `<Comment/>` and `<Pause/>` is removed and whitespace is collapsed. This gives 108,975 segments.
2. **Locate each released snippet.** The non-empty lines of a released snippet, with the `A:` / `B:` prefixes removed, must equal a run of consecutive segment texts in one meeting. All 151 snippets are found, each in exactly one place. This step uses only the released text, never its labels.
3. **Speakers and labels.** Speakers are the participant IDs of the located segments. The professor is the participant whose `education` field in `speakers.xml` is `Professor`. A snippet is kept if it has exactly one professor and at least two speakers; this drops one snippet, leaving 150.
4. **Letters.** Where the released file's letters map one-to-one onto the two participants (reading each letter as the speaker of the last line of its turns), that mapping is kept, so labels remain comparable with the released file: 128 snippets. For the other 22, the first of the two speakers to talk is A. Any further participant is C, D, and so on (three snippets have a third speaker).
5. **Turns and context.** Consecutive segments by the same participant are merged into one turn. Each snippet is rendered at three windows: its own segments, and 15 or 60 additional corpus segments on each side (clipped at meeting boundaries).

## Schema

One JSON object per line:

| Field | Meaning |
| --- | --- |
| `id` | Row index of the snippet in the released `meeting.csv` (as a string) |
| `meeting` | ICSI meeting ID, for example `Bro025` |
| `start_time` | Start time in seconds of the first segment, as given in the MRT file |
| `n_segments` | Number of corpus segments the snippet spans |
| `speakers` | Letter to ICSI participant ID, for example `{"A": "mn007", "B": "me013"}` |
| `professor` | The gold label: the letter of the professor |
| `released_label` | The `power` value for this row in the released file |
| `letters_from_released` | `true` if the letters follow the released mapping (step 4) |
| `turns_same_span` | Turns over the snippet's own segments: `[{"speaker": "B", "text": "..."}, ...]` |
| `turns_pm15`, `turns_pm60` | Turns with 15 or 60 extra segments on each side |

## Counts

- 150 snippets from 45 meetings; the professor is A in 85 (56.7%).
- 142 labels equal the released label; 8 differ.
- Four professors appear; one is the professor in 110 snippets.
- The other focal speaker's education in `speakers.xml` is PhD in 117 snippets, Grad in 30 and Postdoc in 3.

## Licence

The ICSI Meeting Corpus and its annotations are distributed under CC BY 4.0. The rebuilt snippets are derived from that corpus (Janin et al., 2003, *The ICSI Meeting Corpus*, ICASSP). The released `meeting.csv` belongs to its authors and is downloaded at build time, not redistributed here.

## Checking a snippet by hand

`python3 scripts/check_against_released.py --show 0` prints a released snippet line by line next to the corpus participant and role for each line, with the meeting ID and the line number in the `.mrt` file, so any row can be checked against the raw transcript.
