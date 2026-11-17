#!/usr/bin/env python3
"""Fetch and validate genuine DOME dominance rankings against AMI transcripts.

Raw annotations and converted examples remain in ignored local directories.
Only aggregate manifests may be published until DOME redistribution is clarified.
No model inference, training, or automatic evidence-validity labeling occurs here.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/'
SOURCES = {
    'rankings': {'filename': 'dome_annotations_M1.csv', 'url': BASE + 'dome_annotations_M1.csv',
                 'sha256': '32ad863958306e85f02fa96b6a0da73c3b9aa6f49f667415d85a23dad4b91c17'},
    'flags': {'filename': 'dome_dataset_M1.csv', 'url': BASE + 'dome_dataset_M1.csv',
              'sha256': '1b596e64f5329da5376582478b5455161589419e68f93a4abf9c215f56315454'},
    'ami': {'filename': 'ami_public_manual_1.6.2.zip', 'url': BASE + 'ami_public_manual_1.6.2.zip',
            'sha256': 'b56e5babb2496b8795deeeda7e71178d7fbc9963f94276cf2a3f4b56ebbc9f9d'},
}
KEY_FIELDS = ['name', 'start (sec)', 'end (sec)']
FLAG_FIELDS = ['FMD', 'FLD', 'MMD', 'MLD']
RANK_FIELDS = [f'A{r}{p}' for r in range(1, 4) for p in range(1, 5)]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_hash(path, source):
    actual = sha256(path)
    if actual != SOURCES[source]['sha256']:
        raise ValueError(f'{source} SHA256 mismatch: {actual}; expected pinned source bytes')
    return actual


def fetch(cache_dir):
    """Explicit network operation; reuse verified files, never silently replace them."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for source, spec in SOURCES.items():
        path = cache_dir / spec['filename']
        if not path.exists():
            temporary = path.with_suffix(path.suffix + '.part')
            request = urllib.request.Request(spec['url'], headers={'User-Agent': 'DOME-reproducible-import/1'})
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    temporary.write_bytes(response.read())
                check_hash(temporary, source)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        check_hash(path, source)
    return {key: cache_dir / spec['filename'] for key, spec in SOURCES.items()}


def _csv_rows(handle, fields):
    reader = csv.DictReader(handle, delimiter=';')
    if reader.fieldnames is None:
        raise ValueError('missing CSV header')
    headers = [h.strip() for h in reader.fieldnames]
    if len(headers) != len(set(headers)) or set(headers) != set(fields):
        raise ValueError(f'CSV schema mismatch: expected {fields}; got {headers}')
    reader.fieldnames = headers
    rows = {}
    for raw in reader:
        if None in raw or any(v is None for v in raw.values()):
            raise ValueError('malformed CSV row')
        row = {k: v.strip() for k, v in raw.items()}
        try:
            start, end = float(row['start (sec)']), float(row['end (sec)'])
        except ValueError as exc:
            raise ValueError('invalid window bounds') from exc
        if not row['name'] or not all(math.isfinite(t) for t in [start, end]) or start < 0 or end <= start:
            raise ValueError('invalid window bounds')
        key = row['name'], start, end
        if key in rows:
            raise ValueError(f'duplicate segment key: {key}')
        rows[key] = row
    if not rows:
        raise ValueError('empty annotations')
    return rows


def read_annotations(rankings, flags):
    """Join exact segment keys and recompute all agreement flags from three ranks."""
    ranks = _csv_rows(rankings, KEY_FIELDS + RANK_FIELDS)
    subsets = _csv_rows(flags, KEY_FIELDS + FLAG_FIELDS)
    if ranks.keys() != subsets.keys():
        raise ValueError('rankings/flags segment keys differ')
    records = []
    for (meeting, start, end), row in sorted(ranks.items()):
        try:
            ratings = [[int(row[f'A{r}{p}']) for p in range(1, 5)] for r in range(1, 4)]
        except ValueError as exc:
            raise ValueError('rank permutation must contain integers 1..4') from exc
        if any(sorted(rating) != [1, 2, 3, 4] for rating in ratings):
            raise ValueError('each human rank must be a permutation of 1..4')
        top_votes = Counter(rating.index(1) + 1 for rating in ratings)
        low_votes = Counter(rating.index(4) + 1 for rating in ratings)
        computed = dict(FMD=int(max(top_votes.values()) == 3), FLD=int(max(low_votes.values()) == 3),
                        MMD=int(max(top_votes.values()) >= 2), MLD=int(max(low_votes.values()) >= 2))
        flags_row = subsets[meeting, start, end]
        if any(flags_row[k] not in ['0', '1'] for k in FLAG_FIELDS):
            raise ValueError('agreement flags must be binary')
        observed = {k: int(flags_row[k]) for k in FLAG_FIELDS}
        if computed != observed:
            raise ValueError(f'agreement flags disagree with human ranks for {meeting}:{start}')
        records.append(dict(meeting=meeting, start=start, end=end, ranks=ratings, flags=computed,
                            top_camera=top_votes.most_common(1)[0][0] if computed['FMD'] else None))
    return records


def read_meetings(xml, wanted):
    mappings = {}
    for meeting in ET.fromstring(xml).iter('meeting'):
        name = meeting.get('observation')
        if name not in wanted:
            continue
        if name in mappings:
            raise ValueError(f'duplicate meeting metadata: {name}')
        cameras = {}
        for speaker in meeting.findall('speaker'):
            camera = speaker.get('camera', '')
            if not re.fullmatch(r'Closeup[1-4]', camera):
                raise ValueError(f'invalid camera metadata in {name}')
            number = int(camera[-1])
            if number in cameras:
                raise ValueError(f'duplicate camera in {name}')
            cameras[number] = {'agent': speaker.get('nxt_agent'), 'participant': speaker.get('global_name')}
        if (set(cameras) != {1, 2, 3, 4} or {s['agent'] for s in cameras.values()} != set('ABCD')
                or len({s['participant'] for s in cameras.values()}) != 4
                or any(not s['participant'] for s in cameras.values())):
            raise ValueError(f'incomplete or ambiguous four-camera mapping in {name}')
        mappings[name] = cameras
    if set(mappings) != set(wanted):
        raise ValueError('missing meeting camera metadata')
    return mappings


def read_words(xml, speaker):
    words, dropped = [], Counter()
    for order, token in enumerate(ET.fromstring(xml)):
        if token.tag != 'w':
            dropped['non_word_events'] += 1
            continue
        text = ''.join(token.itertext()).strip()
        try:
            start, end = float(token.attrib['starttime']), float(token.attrib['endtime'])
        except (KeyError, ValueError):
            dropped['untimed_words'] += 1
            continue
        if not all(math.isfinite(t) for t in [start, end]) or end < start:
            dropped['untimed_words'] += 1
            continue
        if not text:
            dropped['empty_words'] += 1
            continue
        words.append(dict(speaker=speaker, start=start, end=end, text=text, order=order,
                          is_punctuation=token.get('punc') == 'true'))
    return words, dict(dropped)


def window_turns(words, start, end):
    """Include a word iff start <= word.start < end; retain exact word timings."""
    selected = sorted((w for w in words if start <= w['start'] < end),
                      key=lambda w: (w['start'], w['speaker'], w['order']))
    turns = []
    for word in selected:
        if not turns or turns[-1]['speaker'] != word['speaker']:
            turns.append(dict(speaker=word['speaker'], start=word['start'], end=min(word['end'], end),
                              text=word['text'], word_count=int(not word.get('is_punctuation', False))))
        else:
            turn = turns[-1]
            separator = '' if re.fullmatch(r'[.,?!;:]+', word['text']) else ' '
            turn['text'] += separator + word['text']
            turn['word_count'] += int(not word.get('is_punctuation', False))
            turn['end'] = max(turn['end'], min(word['end'], end))
    return turns


def make_splits(group_participants):
    """Connect shared participants; assign whole components with a frozen hash rule."""
    remaining = set(group_participants)
    components = []
    while remaining:
        members = {min(remaining)}
        participants = set(group_participants[next(iter(members))])
        while True:
            neighbors = {g for g in remaining if g in members or group_participants[g] & participants}
            if neighbors == members:
                break
            members = neighbors
            participants = set().union(*(group_participants[g] for g in members))
        remaining -= members
        components.append(sorted(members))
    components.sort(key=lambda c: hashlib.sha256('|'.join(c).encode()).hexdigest())
    result = dict(status='ready' if len(components) >= 3 else 'blocked', component_count=len(components),
                  components=components, rule='sha256(sorted group IDs joined by |); first=dev, second=test, remainder=train',
                  group_to_split={})
    if len(components) >= 3:
        for i, component in enumerate(components):
            name = ['dev', 'test'][i] if i < 2 else 'train'
            for group in component:
                result['group_to_split'][group] = name
    else:
        result['blocked_reason'] = 'fewer than three participant-disjoint components'
    return result


def make_pairs(windows):
    """Full-MD top vs each challenger, four-speaker context, separate model input."""
    candidates = []
    for row in windows:
        if not row['flags']['FMD']:
            continue
        mapping = row['camera_mapping']
        if set(mapping) != {1, 2, 3, 4} or {v['agent'] for v in mapping.values()} != set('ABCD'):
            raise ValueError(f"primary window lacks metadata for four cameras: {row['id']}")
        top = row['top_camera']
        for challenger in sorted(set(mapping) - {top}):
            # ID uses the unordered pair, never its human winner or an assigned A/B label.
            key = f"{row['meeting']}:{row['start']:g}:{row['end']:g}:" + '-'.join(map(str, sorted([top, challenger])))
            identifier = 'DOME_' + hashlib.sha256(key.encode()).hexdigest()[:24]
            candidates.append((identifier, row, challenger))
    pairs = []
    for index, (identifier, row, challenger) in enumerate(sorted(candidates, key=lambda p: p[0])):
        mapping, top = row['camera_mapping'], row['top_camera']
        focal = [top, challenger] if index % 2 == 0 else [challenger, top]
        camera_order = focal + sorted(set(mapping) - set(focal))
        camera_to_anonymous = dict(zip(camera_order, 'ABCD'))
        agent_to_anonymous = {mapping[c]['agent']: a for c, a in camera_to_anonymous.items()}
        turns = [dict(t, speaker=agent_to_anonymous[t['speaker']]) for t in row['turns']]
        counts = {a: sum(t.get('word_count', len(t['text'].split())) for t in turns if t['speaker'] == a)
                  for a in 'ABCD'}
        pairs.append(dict(id=identifier, prompt_input=dict(id=identifier, speakers=list('ABCD'),
                          participant_roster=[{'speaker': a, 'word_count': counts[a]} for a in 'ABCD'],
                          focal_speakers=['A', 'B'], turns=turns),
                          gold=dict(target='human_perceived_dominance', dominant_speaker=camera_to_anonymous[top],
                                    agreement='3/3 most-dominant rankings'),
                          provenance=dict(window_id=row['id'], meeting=row['meeting'], group=row['group'],
                                          start=row['start'], end=row['end'], split=row['split'],
                                          anonymous_to_participant={a: mapping[c]['participant'] for c, a in camera_to_anonymous.items()},
                                          anonymous_to_ami_agent={a: mapping[c]['agent'] for c, a in camera_to_anonymous.items()},
                                          anonymous_to_camera={a: c for c, a in camera_to_anonymous.items()},
                                          text_evaluable=all(counts.values()),
                                          rater_ranks_by_camera=row['ranks'])))
    if len({p['id'] for p in pairs}) != len(pairs):
        raise ValueError('duplicate pair IDs')
    return pairs


def build_dataset(rankings_path, flags_path, ami_path):
    inputs = {name: dict(SOURCES[name], actual_sha256=check_hash(path, name))
              for name, path in [('rankings', rankings_path), ('flags', flags_path), ('ami', ami_path)]}
    with Path(rankings_path).open(newline='', encoding='utf-8-sig') as ranks, Path(flags_path).open(newline='', encoding='utf-8-sig') as flags:
        windows = read_annotations(ranks, flags)
    meetings = {w['meeting'] for w in windows}
    drop_counts = Counter()
    with zipfile.ZipFile(ami_path) as archive:
        mapping = read_meetings(archive.read('corpusResources/meetings.xml'), meetings)
        words = {}
        for meeting in sorted(meetings):
            words[meeting] = []
            for agent in 'ABCD':
                filename = f'words/{meeting}.{agent}.words.xml'
                if filename not in archive.namelist():
                    raise ValueError(f'missing source word file: {filename}')
                tokens, dropped = read_words(archive.read(filename), agent)
                words[meeting].extend(tokens)
                drop_counts.update(dropped)
        archive_readme = archive.read('00README_MANUAL.txt').decode('utf-8').splitlines()[0]
    groups = defaultdict(set)
    for meeting in meetings:
        groups[meeting[:-1]].update(s['participant'] for s in mapping[meeting].values())
    split = make_splits(groups)
    for row in windows:
        row.update(id=f"{row['meeting']}:{row['start']:g}-{row['end']:g}", group=row['meeting'][:-1],
                   camera_mapping=mapping[row['meeting']],
                   turns=window_turns(words[row['meeting']], row['start'], row['end']))
        row['split'] = split['group_to_split'].get(row['group'], 'blocked')
        row['top_speaker'] = mapping[row['meeting']][row['top_camera']]['agent'] if row['top_camera'] else None
        if not row['turns']:
            raise ValueError(f"empty transcript window: {row['id']}")
    for row in windows:
        row['word_count_by_agent'] = {a: sum(t['word_count'] for t in row['turns'] if t['speaker'] == a) for a in 'ABCD'}
        row['missing_lexical_speakers'] = sorted(a for a, n in row['word_count_by_agent'].items() if n == 0)
        row['text_evaluable'] = not row['missing_lexical_speakers']
    text_evaluable = [w for w in windows if w['flags']['FMD'] and w['text_evaluable']]
    pairs = make_pairs(windows)
    manifest = dict(schema_version=1, dataset='DOME M1 + AMI manual transcripts', sources=inputs,
                    downloaded_windows=len(windows), documentation_windows=125,
                    documentation_discrepancy='current linked M1 files have 58 windows; PDF describes 125; no missing release verified',
                    meeting_count=len(meetings), session_group_count=len(groups),
                    participant_count=len(set().union(*groups.values())),
                    agreement_counts={flag: sum(w['flags'][flag] for w in windows) for flag in FLAG_FIELDS},
                    annotated_minutes=sum(w['end']-w['start'] for w in windows)/60,
                    primary_windows=sum(w['flags']['FMD'] for w in windows), primary_pairs=len(pairs),
                    text_evaluable_windows=len(text_evaluable),
                    text_evaluable_pairs=sum(p['provenance']['text_evaluable'] for p in pairs),
                    eligibility_drops=0, text_coverage_excluded_windows=sum(w['flags']['FMD'] for w in windows)-len(text_evaluable),
                    eligibility_rule='All four cameras must map to participants and existing word files; zero words is permitted silence',
                    secondary_subset_rule='Predeclared lexical coverage: all four participants have at least one non-punctuation word in the window',
                    mapping_all_validated=True, source_word_exclusions=dict(drop_counts),
                    split=split,
                    split_counts={name: dict(windows=sum(w['split'] == name for w in windows),
                                            primary_windows=sum(w['split'] == name and w['flags']['FMD'] for w in windows),
                                            text_evaluable_windows=sum(w['split'] == name for w in text_evaluable),
                                            text_evaluable_pairs=sum(p['provenance']['split'] == name and p['provenance']['text_evaluable'] for p in pairs),
                                            pairs=sum(p['provenance']['split'] == name for p in pairs),
                                            groups=sum(s == name for s in split['group_to_split'].values()))
                                  for name in ['train', 'dev', 'test']},
                    pair_label_counts=dict(sorted(Counter(p['gold']['dominant_speaker'] for p in pairs).items())),
                    participant_disjoint=True, archive_internal_readme_title=archive_readme,
                    archive_version_note='download filename is 1.6.2; internal README says release 1.7; pinned SHA256 identifies bytes',
                    purpose='small benchmark/calibration candidate; no model training or validation performance established',
                    target='multimodally human-perceived dominance; not professor identity, institutional role, or evidence-support validity',
                    limitations=['Only five independent participant groups; pair/window counts are not independent sample sizes.',
                                 'DOME raters used audio/video; text-only inputs may omit cues underlying gold ranks.',
                                 'DOME standalone redistribution license remains unverified; raw labels and derived text stay ignored locally.',
                                 'Role metadata is omitted from model inputs; words spoken in meetings remain unchanged.'],
                    ami_license='CC BY 4.0 in archive LICENCE.txt',
                    citation_links=[BASE+'DOME_documentation.pdf', 'https://groups.inf.ed.ac.uk/ami/corpus/',
                                    'https://groups.inf.ed.ac.uk/ami/download/'])
    return windows, pairs, manifest


def write_dataset(windows, pairs, manifest, output, manifest_path):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / 'work').resolve()):
        raise ValueError('raw/derived DOME output must stay in ignored repository work/ directory')
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {'diagnostic_windows.jsonl': windows,
                 'primary_windows.jsonl': [w for w in windows if w['flags']['FMD']],
                 'dominance_pairs.jsonl': pairs, 'pair_inputs.jsonl': [p['prompt_input'] for p in pairs],
                 'text_evaluable_pairs.jsonl': [p for p in pairs if p['provenance']['text_evaluable']]}
    hashes = {}
    for filename, records in artifacts.items():
        path = output / filename
        path.write_text(''.join(json.dumps(r, sort_keys=True, ensure_ascii=False) + '\n' for r in records), encoding='utf-8')
        hashes[filename] = sha256(path)
    manifest = dict(manifest, local_export_sha256=hashes)
    encoded = json.dumps(manifest, indent=2, sort_keys=True) + '\n'
    (output / 'manifest.json').write_text(encoded)
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(encoded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    get = commands.add_parser('fetch', help='explicitly fetch hash-pinned official public inputs')
    get.add_argument('--cache-dir', type=Path, default=ROOT / 'sources/external')
    build = commands.add_parser('build', help='offline validated import; no model calls')
    build.add_argument('--rankings', type=Path, default=ROOT / 'sources/external/dome_annotations_M1.csv')
    build.add_argument('--flags', type=Path, default=ROOT / 'sources/external/dome_dataset_M1.csv')
    build.add_argument('--ami', type=Path, default=ROOT / 'sources/external/ami_public_manual_1.6.2.zip')
    build.add_argument('--output', type=Path, default=ROOT / 'work/external_dome')
    build.add_argument('--manifest', type=Path, default=ROOT / 'results/external_dome/manifest.json')
    args = parser.parse_args()
    if args.command == 'fetch':
        paths = fetch(args.cache_dir)
        print(json.dumps({k: str(v) for k, v in paths.items()}, sort_keys=True))
    else:
        windows, pairs, manifest = build_dataset(args.rankings, args.flags, args.ami)
        write_dataset(windows, pairs, manifest, args.output, args.manifest)
        print(json.dumps({key: manifest[key] for key in ['downloaded_windows', 'primary_windows', 'primary_pairs',
                                                         'participant_count', 'split_counts']}, sort_keys=True))


if __name__ == '__main__':
    main()
