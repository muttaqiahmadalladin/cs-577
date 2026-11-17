#!/usr/bin/env python3
"""Separate, retrospective post-audit evaluation. No model calls or historical writes.

Run: python scripts/post_audit_evaluation.py [--check]
Conditional graph optimization enumerates eight masks per aspect and enforces
one nonempty reason set across aspects. Relations follow the literal pinned
rules, including their repeated style-A pair. Both conditional objectives are
exported; near ties within 1e-9 objective units choose A.
"""
import argparse
import ast
from collections import Counter
import hashlib
import importlib.metadata
import itertools
import json
import math
from pathlib import Path
import platform
import subprocess

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ASPECTS = ('style', 'content', 'coordination', 'engagement')
SIMILARITIES = ('00', '01', '02', '11', '12', '22')
OBJECTIVE_TOLERANCE = 1e-9
MODES = ('reasons', 'rr', 'all', 'similarity_only', 'contradiction_only')
SEED, RESAMPLES = 2026, 10000


def choose(a, b):
    """A wins an objective tie; tolerate arithmetic noise only, not score rounding."""
    if a == b or abs(a - b) <= OBJECTIVE_TOLERANCE:
        return 'A'
    return 'A' if a > b else 'B'


def probability(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f'{label}: probability must be finite and in [0, 1]')
    return value


def quantized_weight(v, g, multiplier):
    # Literal historical computation; round(v*g, 2) is NOT interchangeable at half cents.
    return multiplier * round(math.exp(math.log(max(v, 1e-6)) + math.log(max(g, 1e-6))), 2)


def synthetic_bank(reason_A=.5, reason_B=.5, rebuttal=.2):
    out = {}
    for a in ASPECTS:
        for side in 'AB':
            for k in range(3):
                for key, value in [('rv', reason_A if side == 'A' else reason_B), ('rg', 1.),
                                   ('bv', 1.), ('bg', 1.), ('ba', rebuttal)]:
                    out[f'{a}|{key}|{side}{k}'] = value
            for p in ('01', '02', '12'):
                out[f'{a}|c{side}|{p}'] = 0.
        for p in SIMILARITIES:
            out[f'{a}|sim|{p}'] = 0.
    return out


SCORE_KEYS = frozenset(synthetic_bank())


def validate_scores(answers, label):
    if not isinstance(answers, dict) or set(answers) != SCORE_KEYS:
        raise ValueError(f'{label}: expected exact 168-answer score schema')
    for key, value in answers.items():
        probability(value, f'{label}/{key}')


def index_records(rows, expected_ids, label):
    out = {}
    for row in rows:
        i = row.get('id')
        if not isinstance(i, str) or not i:
            raise ValueError(f'{label}: missing or non-string id')
        if i in out:
            raise ValueError(f'{label}: duplicate id {i}')
        out[i] = row
    if set(out) != set(expected_ids):
        missing, extra = sorted(set(expected_ids) - set(out)), sorted(set(out) - set(expected_ids))
        raise ValueError(f'{label}: ID alignment failure, missing={missing}, extra={extra}')
    return out


def default_pairs():
    pairs = {(a, s): [(0, 1), (0, 2), (1, 2)] for a in ASPECTS for s in 'AB'}
    pairs['style', 'A'] = [(0, 1), (1, 2), (1, 2)]
    return pairs


def parse_rules(text):
    """Verify the fixed graph topology and extract its literal contradiction pairs."""
    rows = []
    for line in text.splitlines():
        if not line.strip(): continue
        kind, count, *raw = line.split()
        tokens = [int(t) for t in raw]
        if int(count) != len(tokens): raise ValueError('malformed rule count')
        rows.append((kind, tokens))
    expected_prefix = [('XOR', [1, 2])]
    for s in range(2):
        expected_prefix.append(('OROUT', [3 + 24 * a + 3 * s + j for a in range(4) for j in range(3)] + [s + 1]))
    if rows[:3] != expected_prefix or len(rows) != 75:
        raise ValueError('unsupported graph topology; expected pinned 75 rules')
    pairs = {}
    for ai, a in enumerate(ASPECTS):
        base = 3 + 24 * ai  # one-based first reason
        chunk = rows[3 + 18 * ai:3 + 18 * (ai + 1)]
        if chunk[:6] != [('XOR', [base + k, base + 6 + k]) for k in range(6)]:
            raise ValueError('unsupported reason/rebuttal rules')
        expected_sim = [('OR', [-(base + int(p[0])), -(base + 12 + k), -(base + 3 + int(p[1]))]) for k, p in enumerate(SIMILARITIES)]
        if chunk[6:12] != expected_sim: raise ValueError('unsupported similarity rules')
        for si, side in enumerate('AB'):
            pp = []
            for k, (kind, ts) in enumerate(chunk[12 + 3 * si:15 + 3 * si]):
                relation = base + 18 + 3 * si + k
                if kind != 'OR' or len(ts) != 3 or -relation not in ts or any(t >= 0 for t in ts):
                    raise ValueError('unsupported contradiction rule')
                reason_tokens = [-t - base - 3 * si for t in ts if t != -relation]
                if len(reason_tokens) != 2 or any(t not in range(3) for t in reason_tokens):
                    raise ValueError('unsupported contradiction pair')
                pp.append(tuple(reason_tokens))
            pairs[a, side] = pp
    return pairs


def aspect_options(reasons, rebuttals, penalties):
    return [sum(reasons[k] - rebuttals[k] for k in range(3) if mask >> k & 1)
            - sum(w for k, l, w in penalties if mask >> k & 1 and mask >> l & 1)
            for mask in range(8)]


def best_nonempty(options):
    """Two-state dynamic program; exact maxima, lexicographic mask tie policy."""
    states = {False: (0., ())}
    for aspect in options:
        next_states = {}
        for used, (value, masks) in states.items():
            for mask, delta in enumerate(aspect):
                if delta == -math.inf: continue
                new = (value + delta, masks + (mask,))
                key = used or bool(mask)
                old = next_states.get(key)
                if old is None or new[0] > old[0] or (new[0] == old[0] and new[1] < old[1]):
                    next_states[key] = new
        states = next_states
    return states.get(True, (-math.inf, ()))


def conditional_objectives(answers, mode, pairs, active_variables=None, quantization="literal_exp_logs", rebuttal_formula="countering_grounding"):
    """Return values in A,B order, chosen reason masks, and objective constants.

    active_variables optionally filters 0-based reason/rebuttal variables. As in
    factor_graph.xor, a missing XOR endpoint drops that XOR. A surviving rebuttal
    without its reason remains freely ON with its nonnegative weight. If no
    feasible reason remains for a side, its conditional objective is -inf.
    """
    if mode not in MODES: raise ValueError(f'unknown mode {mode}')
    if quantization not in ('literal_exp_logs', 'product_round'): raise ValueError('unknown quantization')
    weight = quantized_weight if quantization == 'literal_exp_logs' else lambda v, g, m: m * round(v * g, 2)
    if rebuttal_formula not in ('countering_grounding', 'validity_countering_grounding'): raise ValueError('unknown rebuttal formula')
    def rebuttal_weight(a, side, k):
        if rebuttal_formula == 'countering_grounding':
            return weight(answers[f'{a}|ba|{side}{k}'], answers[f'{a}|bg|{side}{k}'], 18)
        values = [answers[f'{a}|{key}|{side}{k}'] for key in ('ba', 'bg', 'bv')]
        return 18 * round(math.exp(sum(math.log(max(v, 1e-6)) for v in values)), 2)
    has_rebuttals = mode != 'reasons'
    include_sim = mode in ('all', 'similarity_only')
    include_con = mode in ('all', 'contradiction_only')
    r, b = {}, {}
    active = set(range(98)) if active_variables is None else set(active_variables)
    for ai, a in enumerate(ASPECTS):
        for si, side in enumerate('AB'):
            r[a, side] = [weight(answers[f'{a}|rv|{side}{k}'], answers[f'{a}|rg|{side}{k}'], 20)
                          if 2 + 24 * ai + 3 * si + k in active else None for k in range(3)]
            b[a, side] = [rebuttal_weight(a, side, k)
                          if has_rebuttals and 8 + 24 * ai + 3 * si + k in active else 0. for k in range(3)]
    base = sum(sum(v) for v in b.values())
    if include_sim: base += sum(answers[f'{a}|sim|{p}'] for a in ASPECTS for p in SIMILARITIES)
    if include_con: base += sum(answers[f'{a}|c{s}|{p}'] for a in ASPECTS for s in 'AB' for p in ('01', '02', '12'))
    values, masks = [], {}
    for side in 'AB':
        options = []
        for a in ASPECTS:
            rr = r[a, side]
            penalties = [(k, l, answers[f'{a}|c{side}|{p}']) for p, (k, l) in zip(('01', '02', '12'), pairs[a, side])] if include_con else []
            local = aspect_options([v or 0. for v in rr], b[a, side], penalties)
            for mask in range(8):
                if any(v is None and mask >> k & 1 for k, v in enumerate(rr)): local[mask] = -math.inf
            options.append(local)
        optimum, selected = best_nonempty(options)
        values.append(base + optimum)
        masks[side] = list(selected)
    return dict(values=values, reason_masks=masks, common_constant=base)


def paired_meeting_bootstrap(a_ok, b_ok, meetings, resamples=RESAMPLES, seed=SEED):
    """Paired, snippet-weighted differences, resampling entire meetings together."""
    if not len(a_ok) or len(a_ok) != len(b_ok) or len(a_ok) != len(meetings):
        raise ValueError('paired arrays must have identical nonempty lengths')
    if resamples < 10000: raise ValueError('at least 10000 resamples required')
    aa, bb = np.asarray(a_ok, bool), np.asarray(b_ok, bool)
    labels = sorted(set(meetings))
    delta = aa.astype(int) - bb.astype(int)
    sums = np.array([delta[np.array(meetings) == m].sum() for m in labels])
    sizes = np.array([sum(x == m for x in meetings) for m in labels])
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(labels), size=(resamples, len(labels)))
    values = sums[samples].sum(axis=1) / sizes[samples].sum(axis=1)
    return dict(difference_pp=round(100 * float(delta.mean()), 6),
                meeting_bootstrap_95_pp=[round(100 * float(v), 6) for v in np.percentile(values, [2.5, 97.5])],
                wins=int(np.sum(aa & ~bb)), losses=int(np.sum(~aa & bb)),
                meetings=len(labels), snippets=len(meetings), resamples=resamples, seed=seed)


def plain_baselines(j):
    totals = {s: sum(j[f'{a}|rv|{s}{k}'] * j[f'{a}|rg|{s}{k}'] for a in ASPECTS for k in range(3)) for s in 'AB'}
    survivors = {s: [j[f'{a}|rv|{s}{k}'] * j[f'{a}|rg|{s}{k}'] for a in ASPECTS for k in range(3)
                     if j[f'{a}|rv|{s}{k}'] * j[f'{a}|rg|{s}{k}'] > j[f'{a}|ba|{s}{k}'] * j[f'{a}|bg|{s}{k}']] for s in 'AB'}
    strongest = {s: max(v, default=0.) for s, v in survivors.items()}
    # These baseline ties use exact computed strengths, then the reason sum, then A.
    sum_pred = 'A' if totals['A'] >= totals['B'] else 'B'
    survivor_pred = max('AB', key=lambda s: (strongest[s], totals[s], s == 'A'))
    return dict(reason_sum=dict(prediction=sum_pred, side_values=totals),
                strongest_survivor=dict(prediction=survivor_pred, side_values=strongest,
                                        survivors={s: len(v) for s, v in survivors.items()}, fallback_reason_sum=totals))


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def sha(data): return hashlib.sha256(data).hexdigest()


def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out: raise ValueError(f'duplicate JSON key: {key}')
        out[key] = value
    return out


class Inputs:
    def __init__(self, root):
        self.root, self.hashes, self.versions = root, {}, {}

    def read(self, path, lines=False):
        p = self.root / path
        data = p.read_bytes()
        self.hashes[path] = sha(data)
        return [json.loads(line, object_pairs_hook=unique_pairs) for line in data.splitlines() if line.strip()] if lines else json.loads(data, object_pairs_hook=unique_pairs)

    def records(self, path, ids):
        rows = self.read(path, True)
        result = index_records(rows, ids, path)
        self.versions[path] = dict(Counter(str(r.get('model', 'unknown')) for r in rows))
        return result


def haiku_scores(raw, label):
    if set(raw) != set(ASPECTS): raise ValueError(f'{label}: aspect alignment')
    j = {}
    for a in ASPECTS:
        for side in 'AB':
            for kind, vkey, gkey in [('reason', 'rv', 'rg'), ('rebuttal', 'ba', 'bg')]:
                if len(raw[a][kind][side]) != 3: raise ValueError(f'{label}: expected three arguments')
                for k, values in enumerate(raw[a][kind][side]):
                    if len(values) != 2: raise ValueError(f'{label}: expected validity/grounding pair')
                    j[f'{a}|{vkey}|{side}{k}'], j[f'{a}|{gkey}|{side}{k}'] = values
                    if kind == 'rebuttal': j[f'{a}|bv|{side}{k}'] = 1.
        for kind, prefix, keys in [('similar', 'sim', SIMILARITIES), ('contra_A', 'cA', ('01', '02', '12')), ('contra_B', 'cB', ('01', '02', '12'))]:
            if len(raw[a][kind]) != len(keys): raise ValueError(f'{label}: relation alignment')
            for p, value in zip(keys, raw[a][kind]):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 5:
                    raise ValueError(f'{label}: Haiku relation must be in [0,5]')
                j[f'{a}|{prefix}|{p}'] = value / 5
    validate_scores(j, label)
    return j


def validate_arguments(rows, label):
    for i, row in rows.items():
        if set(row['aspects']) != set(ASPECTS): raise ValueError(f'{label}/{i}: aspect alignment')
        for a in ASPECTS:
            for kind in ('reasons', 'rebuttals'):
                for side in 'AB':
                    text = row['aspects'][a][kind][side]
                    if len(text) != 3 or any(not isinstance(t, str) for t in text):
                        raise ValueError(f'{label}/{i}: three argument strings required')


def historical_assertion_map(root, inputs):
    """Map original assertions without executing or changing historical analysis."""
    path = 'scripts/analyze.py'
    raw = (root / path).read_bytes()
    inputs.hashes[path] = sha(raw)
    tree = ast.parse(raw)
    entries = []
    def record(parts, expected, line):
        pointer = '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in parts)
        entries.append(dict(value_pointer='results/report_numbers.json#/' + pointer, expected=expected,
                            assertion_source=f'{path}:{line}', command='python scripts/analyze.py --check',
                            status='historical asserted value; new runner maps provenance but does not rerun historical analysis'))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign): continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if 'expect' in names:
            for parts, value in ast.literal_eval(node.value).items(): record([*parts, 'correct'], value, node.lineno)
        elif 'audit_expect' in names:
            for item in node.value.keywords: record(['data_audit', item.arg], ast.literal_eval(item.value), node.lineno)
        elif any(isinstance(t, ast.Tuple) and any(isinstance(x, ast.Name) and x.id == 'rb_expect' for x in t.elts) for t in node.targets):
            for parts, value in ast.literal_eval(node.value.elts[1]).items(): record(['robustness', *parts], value, node.lineno)
    record(['rebuilt_fixed', 'Jev, professor'], dict(meeting_bootstrap_95=[6.7, 22.0], brier=.189, accuracy_most_confident_fifth=93.3), 'combined interval/Brier/top-fifth assertion')
    record(['rebuilt_fixed', 'Jev, professor', 'auc'], .79, 'AUC assertion')
    if len(entries) != 60: raise ValueError('historical assertion map changed; review its coverage')
    return entries


def evaluate(root):
    inputs = Inputs(root)
    gold_rows = inputs.read('data/icsi_rebuilt_snippets.jsonl', True)
    ids = [r['id'] for r in gold_rows]
    gold = index_records(gold_rows, set(ids), 'gold')
    if len(ids) != 150 or any(r['professor'] not in ('A', 'B') or not r['meeting'] for r in gold_rows):
        raise ValueError('expected 150 gold rows with binary labels and meeting IDs')
    rules_bytes = (root / 'work/rules.txt').read_bytes()
    inputs.hashes['work/rules.txt'] = sha(rules_bytes)
    pairs = parse_rules(rules_bytes.decode())
    meetings = [gold[i]['meeting'] for i in ids]
    predictions = {i: dict(id=i, gold=gold[i]['professor'], meeting=gold[i]['meeting'], methods={}) for i in ids}
    banks = {}
    folders = {'terra': 'wu_graph_terra', 'haiku': 'wu_graph_claude', 'glm': 'glm_run'}
    for name, folder in folders.items():
        path = f'results/{folder}/jev_scores.jsonl'
        raw = inputs.records(path, ids)
        banks[f'{name}_jev'] = {i: raw[i]['answers'] for i in ids}
        for i, j in banks[f'{name}_jev'].items(): validate_scores(j, f'{path}/{i}')
        if name != 'haiku':
            args = inputs.records(f'results/{folder}/arguments.jsonl', ids)
        else:
            rows = [inputs.read(f'results/{folder}/arguments/{i}.json') for i in ids]
            args = index_records(rows, ids, 'haiku arguments')
        validate_arguments(args, f'{name} arguments')
        if name == 'haiku': inputs.versions['Haiku argument files'] = dict(Counter(str(r.get('model', 'unknown')) for r in args.values()))
    own = [inputs.read(f'results/wu_graph_claude/scores/{i}.json') for i in ids]
    own = index_records(own, ids, 'haiku own scores')
    banks['haiku_haiku'] = {i: haiku_scores(own[i]['aspects'], f'haiku/{i}') for i in ids}
    inputs.versions['Haiku own scores'] = {'unknown (no model version field)': len(own)}
    for bank_name, scores in banks.items():
        for i in ids:
            for mode in MODES:
                objectives = conditional_objectives(scores[i], mode, pairs)
                predictions[i]['methods'][f'{bank_name}/{mode}'] = dict(prediction=choose(*objectives['values']),
                    conditional_objectives=dict(zip('AB', objectives.pop('values'))), **objectives)
            if bank_name != 'haiku_haiku':
                triple = conditional_objectives(scores[i], 'all', pairs, rebuttal_formula='validity_countering_grounding')
                predictions[i]['methods'][f'{bank_name}/all_triple_rebuttal'] = dict(prediction=choose(*triple['values']), conditional_objectives=dict(zip('AB', triple.pop('values'))), **triple)
            product = conditional_objectives(scores[i], 'reasons', pairs, quantization='product_round')
            predictions[i]['methods'][f'{bank_name}/reasons_product_round'] = dict(prediction=choose(*product['values']), conditional_objectives=dict(zip('AB', product.pop('values'))), **product)
            for name, row in plain_baselines(scores[i]).items():
                predictions[i]['methods'][f'{bank_name}/{name}'] = row

    for name, folder in [('terra', 'wu_graph_terra'), ('glm', 'glm_run')]:
        path = f'results/{folder}/zero_shot.jsonl'
        rows = inputs.records(path, ids)
        for i, row in rows.items():
            if name == 'terra': pred = row['prediction']
            else:
                probability(row['p_A'], f'{path}/{i}')
                pred = 'A' if row['p_A'] >= .5 else 'B'
            if pred not in ('A', 'B'): raise ValueError(f'{path}/{i}: binary prediction required')
            predictions[i]['methods'][f'direct/{name}'] = dict(prediction=pred)
    for name in ('haiku', 'sonnet'):
        flat = []
        for k in range(3):
            path = f'results/wu_graph_claude/zero_{name}/zero_{k}.json'
            flat.extend(dict(id=i, **row) for i, row in inputs.read(path).items())
        rows = index_records(flat, ids, f'direct/{name}')
        inputs.versions[f'direct/{name}'] = {'unknown (batch files omit model field)': len(rows)}
        for i, row in rows.items():
            probability(row['p_A'], f'direct/{name}/{i}')
            if row['answer'] not in ('A', 'B'): raise ValueError('invalid direct answer')
            # Historical analyze.py uses answer, including any rounded confidence disagreement.
            predictions[i]['methods'][f'direct/{name}'] = dict(prediction=row['answer'], p_A=row['p_A'])
    direct_jev = inputs.read('results/jev_arm4.jsonl', True)
    if set(r.get('cond') for r in direct_jev) != {'fixed', 'ctx15', 'ctx60'}:
        raise ValueError('unexpected Jev conditions')
    inputs.versions['results/jev_arm4.jsonl'] = dict(Counter(str(r.get('model', 'unknown')) for r in direct_jev))
    for cond in ('fixed', 'ctx15', 'ctx60'):
        rows = index_records([r for r in direct_jev if r['cond'] == cond], ids, f'Jev/{cond}')
        for i, row in rows.items():
            for key, value in row['answers'].items(): probability(value, f'Jev/{cond}/{i}/{key}')
            a, b = row['answers']['professor_A'], row['answers']['professor_B']
            if a + b <= 0: raise ValueError('cannot normalize zero direct probabilities')
            name = 'jev' if cond == 'fixed' else f'jev_{cond}'
            predictions[i]['methods'][f'direct/{name}'] = dict(prediction='A' if a >= b else 'B', normalized_p_A=a / (a + b))
    judges = inputs.records('results/glm_run/judge.jsonl', ids)
    changed = []
    for i, row in judges.items():
        for order in ('A_first', 'B_first'):
            if row[order] not in ('A', 'B'): raise ValueError('invalid judge letter')
            predictions[i]['methods'][f'judge/{order}'] = dict(prediction=row[order])
        same = row['A_first'] == row['B_first']
        if not same: changed.append(i)
        predictions[i]['methods']['judge/disagreement_to_direct'] = dict(prediction=row['A_first'] if same else predictions[i]['methods']['direct/glm']['prediction'])
        vote = sum(predictions[i]['methods'][f'direct/{n}']['prediction'] == 'A' for n in ('glm', 'terra', 'sonnet', 'jev'))
        predictions[i]['methods']['ensemble/majority_ties_jev'] = dict(prediction=predictions[i]['methods']['direct/jev']['prediction'] if vote == 2 else 'A' if vote > 2 else 'B')
        predictions[i]['methods']['baseline/always_A'] = dict(prediction='A')
    keys = list(predictions[ids[0]]['methods'])
    for i in ids:
        if set(predictions[i]['methods']) != set(keys): raise ValueError('per-example method alignment failure')
    ok = {key: [predictions[i]['methods'][key]['prediction'] == gold[i]['professor'] for i in ids] for key in keys}
    counts = {key: dict(correct=sum(values), n=len(ids), accuracy_pp=round(100 * sum(values) / len(ids), 6)) for key, values in ok.items()}
    contrasts = set()
    for bank in banks:
        writer = bank.split('_')[0]
        for mode in ('reasons', 'rr', 'all'):
            for direct in (writer, 'jev'):
                contrasts.add((f'{bank}/{mode}', f'direct/{direct}'))
        if bank != 'haiku_haiku': contrasts.add((f'{bank}/all_triple_rebuttal', f'{bank}/all'))
        for left, right in [('rr', 'reasons'), ('all', 'rr'), ('all', 'reasons'), ('similarity_only', 'rr'), ('contradiction_only', 'rr'), ('reason_sum', 'reasons'), ('strongest_survivor', 'all')]:
            contrasts.add((f'{bank}/{left}', f'{bank}/{right}'))
    for judge in ('A_first', 'B_first', 'disagreement_to_direct'):
        for direct in ('glm', 'jev'): contrasts.add((f'judge/{judge}', f'direct/{direct}'))
    contrasts.add(('judge/A_first', 'judge/B_first'))
    for direct in ('glm', 'terra', 'sonnet', 'jev'):
        contrasts.add(('ensemble/majority_ties_jev', f'direct/{direct}'))
    for context in ('ctx15', 'ctx60'):
        contrasts.add((f'direct/jev_{context}', 'direct/jev'))
    contrasts.add(('direct/jev', 'baseline/always_A'))
    intervals = {f'{a} minus {b}': paired_meeting_bootstrap(ok[a], ok[b], meetings) for a, b in sorted(contrasts)}
    summary = dict(status='retrospective exploratory; not preregistered; no equivalence test',
                   rows=counts, paired_comparisons=intervals,
                   judge_order=dict(changed_ids=changed, changed=len(changed), total=len(ids)),
                   objective_ties={key: [i for i in ids if abs(predictions[i]['methods'][key]['conditional_objectives']['A'] - predictions[i]['methods'][key]['conditional_objectives']['B']) <= OBJECTIVE_TOLERANCE]
                                   for key in keys if 'conditional_objectives' in predictions[ids[0]]['methods'][key]},
                   triple_rebuttal_sensitivity={bank: dict(correct=counts[f'{bank}/all_triple_rebuttal']['correct'], changed_ids=[i for i in ids if predictions[i]['methods'][f'{bank}/all_triple_rebuttal']['prediction'] != predictions[i]['methods'][f'{bank}/all']['prediction']]) for bank in banks if bank != 'haiku_haiku'},
                   terra_reason_quantization_sensitivity=dict(id='142', gold=gold['142']['professor'], historical_CBC_prediction='B', historical_correct=100,
                        literal_exp_logs=dict(prediction=predictions['142']['methods']['terra_jev/reasons']['prediction'], correct=counts['terra_jev/reasons']['correct'], conditional_objectives=predictions['142']['methods']['terra_jev/reasons']['conditional_objectives']),
                        product_round=dict(prediction=predictions['142']['methods']['terra_jev/reasons_product_round']['prediction'], correct=counts['terra_jev/reasons_product_round']['correct'], conditional_objectives=predictions['142']['methods']['terra_jev/reasons_product_round']['conditional_objectives']),
                        explanation='The audit product-round approximation has a 112.8/112.8 tie (564 hundredths each) and chooses A:101. Literal historical exp(logs) changes two half-cent roundings, giving A112.6/B113.0 and B:100. The audit tie-only explanation does not hold for the literal implemented weights. Historical artifacts/assertions remain unchanged.'))
    # These are guardrails for this frozen bank, not replacements for historical assertions.
    for bank, expected in [('terra_jev', 108), ('haiku_jev', 105), ('glm_jev', 104)]:
        if counts[f'{bank}/all']['correct'] != expected: raise ValueError(f'{bank}: primary graph count changed')
    if counts['terra_jev/reasons']['correct'] != 100 or counts['terra_jev/reasons_product_round']['correct'] != 101: raise ValueError('Terra quantization sensitivity changed')
    collection = inputs.read('results/wu_graph_terra/manifest.json')
    inputs.read('results/wu_graph_terra/provenance.json')
    prediction_bytes = b''.join(json.dumps(predictions[i], sort_keys=True, allow_nan=False).encode() + b'\n' for i in ids)
    provenance = {key: dict(kind='computed from immutable saved outputs', command='python scripts/post_audit_evaluation.py',
                           value_pointer='results/post_audit/summary.json#/rows/' + key.replace('~', '~0').replace('/', '~1'),
                           prediction_pointer=f'results/post_audit/predictions.jsonl:methods[{key!r}]') for key in keys}
    # Explicitly external rows quoted in the historical released-data table.
    provenance['external_original_rows'] = [
        dict(label='Grounded extension, as proposed', correct=69, n=151, accuracy_pp=45.7),
        dict(label='XOR graph with quote filter', correct=64, n=151, accuracy_pp=42.4),
        dict(label='Gemma 4 zero-shot', correct=66, n=151, accuracy_pp=43.7)]
    for row in provenance['external_original_rows']:
        row.update(kind='external original result; not recomputed by this runner', source='https://github.com/KrishMay05/nlp_research', quoted_by='report/report.tex released-data table', immutable_prediction_artifact='not available in this checkout')
    provenance['historical_original_sixty_assertions'] = historical_assertion_map(root, inputs)
    provenance['historical_report_values'] = dict(kind='historical reproduction; independent of this new evaluation',
        command='python scripts/reproduce.py', assertions='scripts/analyze.py --check retains original sixty asserted values',
        artifact='results/report_numbers.json', warning='Historical exp(logs) weights choose B on reason-only ID142; product-round sensitivity ties and chooses A. Do not substitute post-audit outputs into those tables without relabeling.')
    provenance['other_historical_supplements'] = dict(commands=['python scripts/grounded_extension.py', 'python scripts/grounded_policy_search.py', 'python scripts/data_differences.py', 'python scripts/score_run.py --run glm_run --name glm-5.3', 'python scripts/grounded_policy_search.py --run glm_run', 'python scripts/qbaf.py', 'python scripts/judge_run.py --run glm_run --score'],
        limitation='These scripts compute their documented artifacts; not every prose number is an asserted end-to-end reproduction. Historical logistic-regression range has no local input-to-output reproduction.')
    try:
        input_commit = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--', 'data/icsi_rebuilt_snippets.jsonl', *[p for p in inputs.hashes if p.startswith('results/')]], cwd=root, text=True).strip()
    except subprocess.CalledProcessError: input_commit = 'unknown'
    versions = {'python': platform.python_version(), 'numpy': np.__version__}
    for package in ('PuLP',):
        try: versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: versions[package] = 'not installed; unused by exact enumeration'
    try:
        import pulp
        version_text = subprocess.check_output([pulp.PULP_CBC_CMD().path, '-stop'], text=True)
        versions['CBC'] = next(line.strip() for line in version_text.splitlines() if line.startswith('Version:'))
    except (ImportError, OSError, subprocess.CalledProcessError, StopIteration): versions['CBC'] = 'unavailable; unused by exact enumeration'
    manifest = dict(evaluation='post-audit deterministic conditional enumeration v1', status=summary['status'], source_commit=input_commit,
        input_sha256=dict(sorted(inputs.hashes.items())), recorded_model_versions=inputs.versions, runtime_versions=versions,
        evaluation_code_sha256=sha(Path(__file__).read_bytes()), predictions_sha256=sha(prediction_bytes),
        formulas=dict(reason='P(valid)*P(grounded)', rebuttal='P(counters)*P(grounded)', haiku_own_rebuttal='P(valid)*P(grounded)',
                      graph_quantization='reason:20*round(exp(log(max(v,1e-6))+log(max(g,1e-6))),2); rebuttal:18*same',
                      triple_rebuttal_sensitivity='18*round(exp(log(max(countering,1e-6))+log(max(grounding,1e-6))+log(max(validity,1e-6))),2); exploratory, separately named',
                      product_round_sensitivity='separately named reasons_product_round uses20*round(v*g,2), then A ties; not historical exp(logs) quantization',
                      relations='native Jev probabilities; Haiku own ordinal score / 5',
                      unquantized_baselines='raw products without log floor or round; sum all reasons, or strongest reason strictly surviving its own rebuttal; strongest ties use reason sum then A'),
        tie_policy=dict(speaker='A if abs(objective_A-objective_B)<=1e-9, otherwise larger objective', tolerance_objective_units=OBJECTIVE_TOLERANCE,
                        mask='exact within-side objective maxima; lexicographically smallest optimal mask tuple'),
        optimizer='eight local masks per aspect; dynamic program enforces nonempty across four aspects; no CBC invocation for predictions',
        inherited_rules=dict(sha256=sha(rules_bytes), style_A_pairs=pairs['style', 'A'], similarity='constant under speaker XOR and OROUT; cannot affect winner'),
        uncertainty=dict(unit='paired whole meetings', estimator='snippet-weighted accuracy difference, variable denominator under cluster resampling', seed=SEED, resamples=RESAMPLES, interval='95% percentile; numpy.percentile linear', generalization='45 observed meetings; narrow professor population; retrospective exploration, no equivalence inference'),
        historical_collection_manifest_disagreement=dict(recorded=collection['scoring'], evaluated='reason validity*grounding; rebuttal countering*grounding', action='historical manifest retained verbatim; this evaluation declares its separate formula'),
        report_value_provenance='results/post_audit/report_value_provenance.json')
    return {'predictions.jsonl': prediction_bytes, 'summary.json': canonical(summary), 'manifest.json': canonical(manifest), 'report_value_provenance.json': canonical(provenance)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='recompute and compare byte-for-byte, write nothing')
    args = parser.parse_args()
    outputs = evaluate(ROOT)
    folder = ROOT / 'results/post_audit'
    if args.check:
        bad = [name for name, data in outputs.items() if not (folder / name).exists() or (folder / name).read_bytes() != data]
        if bad: raise SystemExit('post-audit mismatch: ' + ', '.join(bad))
        print(f'post-audit check: {len(outputs)} deterministic outputs match')
    else:
        folder.mkdir(parents=True, exist_ok=True)
        for name, data in outputs.items(): (folder / name).write_bytes(data)
        print(f'wrote {len(outputs)} post-audit outputs to {folder.relative_to(ROOT)}')
    summary = json.loads(outputs['summary.json'])
    for key in ('terra_jev/all', 'haiku_jev/all', 'glm_jev/all', 'terra_jev/reasons'):
        print(f"{key}: {summary['rows'][key]['correct']}/150")


if __name__ == '__main__': main()
