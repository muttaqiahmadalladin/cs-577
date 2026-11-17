"""Behavioral checks for the separately named post-audit evaluation."""
import importlib.util
import itertools
import json
import sys
import math
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts/post_audit_evaluation.py'
spec = importlib.util.spec_from_file_location('post_audit', MODULE)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


class ConditionalGraphTests(unittest.TestCase):
    def test_equal_objectives_choose_A_with_explicit_tolerance(self):
        self.assertEqual(e.choose(12.0, 12.0), 'A')
        self.assertEqual(e.choose(12.0, 12.0 + e.OBJECTIVE_TOLERANCE / 2), 'A')
        self.assertEqual(e.choose(12.0, 12.0 + 2 * e.OBJECTIVE_TOLERANCE), 'B')

    def test_quantization_matches_literal_exp_logs_including_half_cent(self):
        for v, g in [(0, 0), (.1, .95), (.29, .5), (.7, .35), (1, 1)]:
            expected = 20 * round(math.exp(math.log(max(v, 1e-6)) + math.log(max(g, 1e-6))), 2)
            self.assertEqual(e.quantized_weight(v, g, 20), expected)

    def test_product_round_sensitivity_is_explicitly_separate(self):
        bank = e.synthetic_bank()
        bank['style|rv|A0'], bank['style|rg|A0'] = .55, .9
        literal = e.conditional_objectives(bank, 'reasons', e.default_pairs())
        product = e.conditional_objectives(bank, 'reasons', e.default_pairs(), quantization='product_round')
        self.assertAlmostEqual(product['values'][0] - literal['values'][0], .2)
        self.assertEqual(product['values'][1], literal['values'][1])

    def test_all_eight_masks_and_nonempty_global_constraint(self):
        r, b = [2., 3., 4.], [5., 2., 7.]
        penalties = [(0, 1, .4), (0, 2, .7), (1, 2, .9)]
        actual = e.aspect_options(r, b, penalties)
        expected = [sum(r[k] - b[k] for k in range(3) if m >> k & 1)
                    - sum(w for k, l, w in penalties if m >> k & 1 and m >> l & 1)
                    for m in range(8)]
        self.assertEqual(actual, expected)
        # All deltas are negative; the conditional speaker still needs one reason.
        value, masks = e.best_nonempty([[-float(m.bit_count()) for m in range(8)]] * 4)
        self.assertEqual(value, -1.)
        self.assertTrue(any(masks))
        # Compare dynamic program with complete 8**4 enumeration.
        options = [actual, actual[::-1], [-x for x in actual], actual]
        exhaustive = max(sum(options[k][m] for k, m in enumerate(ms))
                         for ms in itertools.product(range(8), repeat=4) if any(ms))
        self.assertAlmostEqual(e.best_nonempty(options)[0], exhaustive)

    def test_contradictions_can_change_winner_similarities_cannot(self):
        bank = e.synthetic_bank(reason_A=.5, reason_B=.49, rebuttal=0)
        base = e.conditional_objectives(bank, 'rr', e.default_pairs())
        for a in e.ASPECTS:
            for pair in ('01', '02', '12'):
                bank[f'{a}|cA|{pair}'] = 1.
            for pair in e.SIMILARITIES:
                bank[f'{a}|sim|{pair}'] = 1.
        sim = e.conditional_objectives(bank, 'similarity_only', e.default_pairs())
        con = e.conditional_objectives(bank, 'contradiction_only', e.default_pairs())
        self.assertEqual(e.choose(*base['values']), 'A')
        self.assertEqual(e.choose(*sim['values']), 'A')
        self.assertAlmostEqual(sim['values'][0] - base['values'][0], 24.)
        self.assertEqual(e.choose(*con['values']), 'B')


    def test_literal_conditionals_match_CBC_including_ID142(self):
        sys.path.insert(0, str(MODULE.parent))
        from factor_graph import xor
        from score_run import graph_rows
        root = MODULE.parents[1]
        rules = (root / 'work/rules.txt').read_text()
        pairs = e.parse_rules(rules)
        for folder, sample in [('wu_graph_terra', ['0', '142']), ('wu_graph_claude', ['0']), ('glm_run', ['0'])]:
            rows = {r['id']: r['answers'] for r in map(json.loads, (root / f'results/{folder}/jev_scores.jsonl').read_text().splitlines())}
            for i in sample:
                for mode in ('reasons', 'rr', 'all'):
                    actual = e.conditional_objectives(rows[i], mode, pairs)
                    with self.subTest(folder=folder, id=i, mode=mode):
                        self.assertEqual(e.choose(*actual['values']), xor(*graph_rows(rows[i], mode), rules))
                    if folder == 'wu_graph_terra' and i == '142' and mode == 'reasons':
                        self.assertAlmostEqual(actual['values'][0], 112.6)
                        self.assertAlmostEqual(actual['values'][1], 113.)
                        self.assertEqual(e.choose(*actual['values']), 'B')

    def test_removed_reason_drops_XOR_and_nonempty_constraint_remains(self):
        bank = e.synthetic_bank(reason_A=.9, reason_B=.1, rebuttal=.2)
        active = set(range(2, 98)) - {2 + 24 * ai + k for ai in range(4) for k in range(3)}
        result = e.conditional_objectives(bank, 'all', e.default_pairs(), active_variables=active)
        self.assertEqual(result['values'][0], -math.inf)
        self.assertTrue(math.isfinite(result['values'][1]))
        self.assertEqual(e.choose(*result['values']), 'B')
        none = e.conditional_objectives(bank, 'all', e.default_pairs(), active_variables=set())
        self.assertEqual(e.choose(*none['values']), 'A')

    def test_literal_triple_rebuttal_sensitivity(self):
        bank = e.synthetic_bank()
        bank['style|bv|A0'] = .5
        base = e.conditional_objectives(bank, 'all', e.default_pairs())
        triple = e.conditional_objectives(bank, 'all', e.default_pairs(), rebuttal_formula='validity_countering_grounding')
        self.assertNotEqual(base['values'], triple['values'])


class ValidationTests(unittest.TestCase):
    def test_missing_duplicate_and_mismatched_ids_fail(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            e.index_records([{'id': '0'}, {'id': '0'}], {'0'}, 'sample')
        with self.assertRaisesRegex(ValueError, 'alignment'):
            e.index_records([{'id': '0'}], {'0', '1'}, 'sample')
        with self.assertRaisesRegex(ValueError, 'alignment'):
            e.index_records([{'id': '0'}, {'id': '2'}], {'0', '1'}, 'sample')
        with self.assertRaisesRegex(ValueError, 'id'):
            e.index_records([{}], set(), 'sample')

    def test_duplicate_json_keys_are_rejected_before_ID_indexing(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'duplicate.json').write_text('{"0":{"answer":"A"},"0":{"answer":"B"}}')
            with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
                e.Inputs(Path(tmp)).read('duplicate.json')

    def test_probability_validation(self):
        bank = e.synthetic_bank()
        e.validate_scores(bank, 'good')
        for bad in (-.01, 1.01, float('nan'), float('inf')):
            broken = dict(bank, **{'style|rv|A0': bad})
            with self.assertRaises(ValueError): e.validate_scores(broken, 'broken')
        del bank['style|rv|A0']
        with self.assertRaisesRegex(ValueError, '168'): e.validate_scores(bank, 'missing')


class BootstrapTests(unittest.TestCase):
    def test_resamples_whole_paired_meetings_with_variable_denominator(self):
        # One size-two cluster contributes +2; the size-one cluster contributes -1.
        # Whole-cluster resampling permits only {-1, 1/3, 1} differences.
        a, b, meetings = [True, True, False], [False, False, True], ['m1', 'm1', 'm2']
        result = e.paired_meeting_bootstrap(a, b, meetings, resamples=10000, seed=2026)
        self.assertAlmostEqual(result['difference_pp'], 100 / 3, places=6)
        self.assertEqual(result['meeting_bootstrap_95_pp'], [-100., 100.])
        self.assertEqual(result, e.paired_meeting_bootstrap(a, b, meetings, resamples=10000, seed=2026))
        same = e.paired_meeting_bootstrap(a, a, meetings, resamples=10000, seed=2026)
        self.assertEqual(same['meeting_bootstrap_95_pp'], [0., 0.])
        with self.assertRaises(ValueError): e.paired_meeting_bootstrap(a, b[:-1], meetings)


if __name__ == '__main__': unittest.main()
