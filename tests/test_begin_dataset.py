"""BEGIN gates: official splits, source integrity, labels and prompt isolation."""
import csv
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import begin_dataset as begin


def tsv(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=begin.COLUMNS, delimiter='\t')
    writer.writeheader()
    for i, label in enumerate(rows):
        writer.writerow(dict(model_name='t5', data_source='cmu', knowledge='Quoted\nknowledge',
                             message='Question?', response=f'Response {i}', begin_label=label))
    stream.seek(0)
    return stream


class ImportTests(unittest.TestCase):
    def test_quoted_newlines_and_distinct_generic_label(self):
        rows = begin.read_tsv(tsv(['Fully attributable', 'Not fully attributable', 'Generic']), 'cmu-dog', 'dev')
        self.assertEqual([r['label'] for r in rows], list(begin.LABEL_MAP.values()))
        self.assertEqual(rows[2]['evidence_decision'], 'abstain')
        self.assertEqual(rows[0]['knowledge'], 'Quoted\nknowledge')
        self.assertEqual(len({r['id'] for r in rows}), 3)
        self.assertEqual(rows, begin.read_tsv(tsv(['Fully attributable', 'Not fully attributable', 'Generic']), 'cmu-dog', 'dev'))

    def test_bad_label_missing_input_wrong_domain_and_wrong_split_fail(self):
        empty_msg = begin.read_tsv(io.StringIO(tsv(['Generic']).getvalue().replace('Question?', '')), 'cmu-dog', 'dev')
        self.assertTrue(empty_msg[0]['empty_message'])
        for stream, domain, split, message in [
            (tsv(['']), 'cmu-dog', 'dev', 'label'),
            (tsv(['supported']), 'cmu-dog', 'dev', 'label'),
            (io.StringIO(tsv(['Generic']).getvalue().replace('Response 0', '')), 'cmu-dog', 'dev', 'empty'),
            (tsv(['Generic']), 'wow', 'dev', 'data_source'),
            (tsv(['Generic']), 'cmu-dog', 'train', 'split'),
        ]:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                begin.read_tsv(stream, domain, split)

    def test_source_checksum_detects_corruption(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'bad.tsv'
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                begin.check_hash(path, next(iter(begin.SOURCES.values())))

    def test_overlap_detects_shared_inputs_responses_and_knowledge(self):
        dev = begin.read_tsv(tsv(['Generic']), 'cmu-dog', 'dev')
        test = begin.read_tsv(tsv(['Generic']), 'cmu-dog', 'test')
        report = begin.overlap_report(dev, test)
        self.assertEqual(report['input']['shared_unique_hashes'], 1)
        self.assertEqual(report['response']['test_rows_matching_dev'], 1)
        self.assertEqual(report['knowledge']['dev_rows_matching_test'], 1)


class PilotTests(unittest.TestCase):
    def records(self):
        return begin.read_tsv(tsv(['Fully attributable'] * 8 + ['Not fully attributable'] * 8 + ['Generic'] * 8), 'cmu-dog', 'dev')

    def test_balanced_frozen_dev_only_pilot_and_prompt_isolation(self):
        records = self.records()
        pilot = begin.select_pilot(records, limit=12, seed='freeze')
        self.assertEqual(len(pilot), 12)
        self.assertEqual(pilot, begin.select_pilot(list(reversed(records)), limit=12, seed='freeze'))
        from collections import Counter
        self.assertEqual(set(Counter(r['label'] for r in pilot).values()), {4})
        prompt = begin.format_request(pilot[0])
        content = json.loads(prompt[1]['content'])
        self.assertEqual(set(content), {'knowledge', 'message', 'response'})
        with self.assertRaisesRegex(ValueError, 'dev'):
            begin.select_pilot([{**records[0], 'split': 'test'}])
        with self.assertRaisesRegex(ValueError, '12'):
            begin.select_pilot(records, limit=15)

    def test_prediction_is_strict_and_generic_stays_abstain(self):
        self.assertEqual(begin.validate_prediction('{"label":"generic"}'), 'generic')
        for value in ['supported', '{"label":"Generic"}', '{"label":"generic","reason":"x"}', '```json\n{"label":"generic"}\n```']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                begin.validate_prediction(value)

    def test_calibration_evaluation_and_actual_offline_build(self):
        records = self.records()[:3]
        records[0]['label'], records[1]['label'], records[2]['label'] = 'fully_attributable', 'not_fully_attributable', 'generic'
        preds = [{'id': records[0]['id'], 'response': '{"label":"not_fully_attributable"}'},
                 {'id': records[1]['id'], 'response': '{"label":"fully_attributable"}'},
                 {'id': records[2]['id'], 'response': '{"label":"generic"}'}]
        report = begin.evaluate_predictions(preds, records)
        self.assertEqual(report['exact_matches'], 1)
        self.assertEqual(report['false_rejections'], 1)
        self.assertEqual(report['false_acceptances'], 1)
        self.assertEqual(report['predicted_abstain'], 1)
        with self.assertRaisesRegex(ValueError, 'dev'):
            begin.evaluate_predictions(preds, [{**records[0], 'split': 'test'}, *records[1:]])
        cache = ROOT / 'sources/external/begin' / begin.COMMIT
        if not cache.exists():
            self.skipTest('run fetch first for the optional official-source integration gate')
        manifest = begin.build(cache, ROOT / 'work/external_begin', ROOT / 'results/external_begin/manifest.json')
        self.assertEqual(manifest['totals'], {'dev': 1229, 'test': 11059})
        self.assertEqual(manifest['empty_message_rows']['dev']['cmu-dog'], 2)
        self.assertEqual(manifest['exact_dev_test_overlap']['input']['shared_unique_hashes'], 0)
        self.assertEqual(manifest['pilot']['labels'], {'fully_attributable': 4, 'generic': 4, 'not_fully_attributable': 4})


if __name__ == '__main__':
    unittest.main()
