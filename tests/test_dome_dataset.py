"""DOME import gates: real human ranks, camera identities, timing and leakage."""
import copy
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import dome_dataset as dome

RANK_HEADER = ' name ; start (sec) ; end (sec) ;' + ';'.join(f'A{r}{p}' for r in range(1, 4) for p in range(1, 5))
RANK_ROW = ' M1a ;0;300;' + ';'.join(map(str, [4, 1, 3, 2] * 3))
FLAGS = 'name;start (sec);end (sec);FMD;FLD;MMD;MLD\nM1a;0;300;1;1;1;1\n'


def read_rows(rank_row=RANK_ROW, flags=FLAGS):
    return dome.read_annotations(io.StringIO(RANK_HEADER + '\n' + rank_row + '\n'), io.StringIO(flags))


class AnnotationTests(unittest.TestCase):
    def test_strips_keys_and_validates_human_rank_agreement(self):
        rows = read_rows()
        self.assertEqual(rows[0]['meeting'], 'M1a')
        self.assertEqual(rows[0]['top_camera'], 2)
        self.assertEqual(rows[0]['ranks'], [[4, 1, 3, 2]] * 3)
        self.assertEqual(rows[0]['flags'], dict(FMD=1, FLD=1, MMD=1, MLD=1))

    def test_duplicate_misaligned_invalid_permutation_and_flag_fail(self):
        for bad, flags, message in [
            (RANK_ROW + '\n' + RANK_ROW, FLAGS, 'duplicate'),
            (RANK_ROW, FLAGS.replace('M1a;', 'M2a;'), 'keys'),
            (RANK_ROW.replace('4;1;3;2', '4;1;3;3', 1), FLAGS, 'permutation'),
            (RANK_ROW, FLAGS.replace(';1;1;1;1', ';0;1;1;1'), 'agreement'),
            (RANK_ROW, FLAGS.replace(';1;1;1;1', ';2;1;1;1'), 'binary'),
        ]:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                read_rows(bad, flags)

    def test_nonfinite_or_reversed_bounds_fail(self):
        for row in [RANK_ROW.replace(';0;300;', ';nan;300;'), RANK_ROW.replace(';0;300;', ';300;0;')]:
            with self.assertRaisesRegex(ValueError, 'bounds'):
                read_rows(row)


class TranscriptTests(unittest.TestCase):
    def test_camera_to_agent_is_metadata_based(self):
        xml = b'<root><meeting observation="M1a">' + b''.join(
            f'<speaker camera="Closeup{c}" nxt_agent="{a}" global_name="p{c}" role="PM"/>'.encode()
            for c, a in [(1, 'C'), (2, 'D'), (3, 'B'), (4, 'A')]) + b'</meeting></root>'
        mapping = dome.read_meetings(xml, {'M1a'})
        self.assertEqual(mapping['M1a'][1], {'agent': 'C', 'participant': 'p1'})
        self.assertNotIn('role', str(mapping))
        with self.assertRaisesRegex(ValueError, 'camera'):
            dome.read_meetings(xml.replace(b'Closeup4', b'Closeup3'), {'M1a'})

    def test_half_open_window_excludes_noise_and_keeps_timing(self):
        xml = b'''<root><w starttime="-1" endtime="0">before</w>
        <w starttime="0" endtime="0.3">First</w><vocalsound starttime="1" endtime="2">laugh</vocalsound>
        <w starttime="299.9" endtime="300.2">last</w><w starttime="300" endtime="301">next</w></root>'''
        words, dropped = dome.read_words(xml, 'C')
        turns = dome.window_turns(words, 0, 300)
        self.assertEqual([t['text'] for t in turns], ['First last'])
        self.assertEqual(turns[0]['speaker'], 'C')
        self.assertEqual(turns[0]['start'], 0)
        self.assertEqual(turns[0]['end'], 300)
        self.assertEqual(dropped['non_word_events'], 1)


class SplitAndPairTests(unittest.TestCase):
    def test_connected_participants_join_groups_and_block_if_too_few(self):
        groups = {'G1': {'p1'}, 'G2': {'p1', 'p2'}, 'G3': {'p3'}, 'G4': {'p4'}}
        split = dome.make_splits(groups)
        self.assertEqual(split['status'], 'ready')
        self.assertEqual(split['group_to_split']['G1'], split['group_to_split']['G2'])
        self.assertEqual(len(set(split['group_to_split'].values())), 3)
        self.assertEqual(split, dome.make_splits(dict(reversed(list(groups.items())))))
        self.assertEqual(dome.make_splits({'G1': {'p1'}, 'G2': {'p1'}})['status'], 'blocked')

    def test_pairs_counterbalance_and_keep_gold_out_of_prompt(self):
        row = dict(id='window1', meeting='M1a', start=0, end=300, group='G1', split='train',
                   top_camera=2, ranks=[[4, 1, 3, 2]] * 3,
                   flags=dict(FMD=1, FLD=1, MMD=1, MLD=1),
                   camera_mapping={1: {'agent': 'C', 'participant': 'p1'}, 2: {'agent': 'D', 'participant': 'p2'},
                                   3: {'agent': 'B', 'participant': 'p3'}, 4: {'agent': 'A', 'participant': 'p4'}},
                   turns=[{'speaker': s, 'start': i, 'end': i+1, 'text': 'token' + s} for i, s in enumerate('ABCD')])
        other = copy.deepcopy(row)
        other.update(id='window2', start=300, end=600)
        pairs = dome.make_pairs([row, other])
        self.assertEqual(len(pairs), 6)
        self.assertEqual(sorted(p['gold']['dominant_speaker'] for p in pairs), ['A'] * 3 + ['B'] * 3)
        for p in pairs:
            self.assertEqual(set(t['speaker'] for t in p['prompt_input']['turns']), set('ABCD'))
            self.assertEqual(len(p['prompt_input']['turns']), 4)
            self.assertEqual(p['prompt_input']['focal_speakers'], ['A', 'B'])
            self.assertEqual(p['provenance']['anonymous_to_participant'][p['gold']['dominant_speaker']], 'p2')
            self.assertNotIn('rank', str(p['prompt_input']))
            for original_id in ['p1', 'p2', 'p3', 'p4']:
                self.assertNotIn(original_id, str(p['prompt_input']))
            self.assertNotIn('dominant', p['id'])
        self.assertEqual(pairs, dome.make_pairs([other, row]))
        row['turns'] = row['turns'][:-1]
        silent_pairs = dome.make_pairs([row])
        self.assertEqual(len(silent_pairs), 3)
        self.assertTrue(all(len(p['prompt_input']['participant_roster']) == 4 for p in silent_pairs))
        self.assertTrue(all(sum(r['word_count'] == 0 for r in p['prompt_input']['participant_roster']) == 1 for p in silent_pairs))
        self.assertTrue(all(len(p['prompt_input']['turns']) == 3 for p in silent_pairs))
        del row['camera_mapping'][1]
        with self.assertRaisesRegex(ValueError, 'four cameras'):
            dome.make_pairs([row])

    def test_actual_offline_sources_build_expected_counts(self):
        rank = ROOT / 'sources/external/dome_annotations_M1.csv'
        if not rank.exists():
            rank = ROOT / 'work/dataset-research/dome_annotations_M1.csv'
        flags = ROOT / 'sources/external/dome_dataset_M1.csv'
        if not flags.exists():
            flags = ROOT / 'work/dataset-research/dome_dataset_M1.csv'
        ami = ROOT / 'sources/external/ami_public_manual_1.6.2.zip'
        if not all(p.exists() for p in [rank, flags, ami]):
            self.skipTest('run fetch first for the optional official-source integration gate')
        windows, pairs, manifest = dome.build_dataset(rank, flags, ami)
        self.assertEqual(len(windows), 58)
        self.assertEqual(len(pairs), 102)
        self.assertEqual(manifest['agreement_counts'], dict(FMD=34, FLD=31, MMD=56, MLD=54))
        self.assertEqual(manifest['participant_count'], 20)
        self.assertEqual(manifest['split']['component_count'], 5)
        self.assertEqual(manifest['split']['status'], 'ready')
        self.assertEqual(manifest['primary_windows'], 34)
        self.assertEqual(manifest['text_evaluable_windows'], 30)
        self.assertEqual(manifest['text_evaluable_pairs'], 90)
        self.assertEqual(manifest['pair_label_counts'], {'A': 51, 'B': 51})
        self.assertEqual(manifest['eligibility_drops'], 0)
        self.assertEqual(manifest['text_coverage_excluded_windows'], 4)
        by_id = {w['id']: w for w in windows}
        for pair in pairs:
            window = by_id[pair['provenance']['window_id']]
            top_participant = window['camera_mapping'][window['top_camera']]['participant']
            self.assertEqual(pair['provenance']['anonymous_to_participant'][pair['gold']['dominant_speaker']], top_participant)
        swapped = next(w for w in windows if w['meeting'] == 'IS1003b' and w['start'] == 1200)
        self.assertEqual(swapped['top_camera'], 1)
        self.assertEqual(swapped['top_speaker'], 'C')
        for a in ['train', 'dev', 'test']:
            pa = {v['participant'] for w in windows if w['split'] == a for v in w['camera_mapping'].values()}
            for b in ['train', 'dev', 'test']:
                if a != b:
                    pb = {v['participant'] for w in windows if w['split'] == b for v in w['camera_mapping'].values()}
                    self.assertFalse(pa & pb)


if __name__ == '__main__':
    unittest.main()
