import os
"""All numbers for the report. Writes results.json."""
import json, sys, math, re, collections, numpy as np
sys.path.insert(0, '.'); sys.path.insert(0, os.path.join(os.environ.get('KRISH_REPO', 'nlp_research'), 'src'))
from icsi import *
from quote_power.inference import xor
from scipy.stats import binomtest
from sklearn.metrics import roc_auc_score, cohen_kappa_score
M = meetings(); FX = json.load(open('fixed_index.json')); rows = json.load(open('rows.json'))
R = {r['id']: r for r in (json.loads(l) for l in open('data/snippets.jsonl'))}; rules = open('data/rules.txt').read()
A1 = {json.loads(l)['id']: json.loads(l)['answers'] for l in open('jev_arm1.jsonl')}
A3 = {json.loads(l)['id']: json.loads(l)['answers'] for l in open('jev_arm3.jsonl')}
A4 = collections.defaultdict(dict); models = set()
for l in open('jev_arm4.jsonl'):
    d = json.loads(l); A4[d['cond']][d['id']] = d['answers']; models.add(d['model'])
ids = [o['id'] for o in FX]; N = len(ids); y = np.array([o['label'] == 'A' for o in FX]); yw = np.array([o['wu_label'] == 'A' for o in FX])
meet = np.array([o['meeting'] for o in FX]); res = dict(n=N, label_A=int(y.sum()), models=sorted(models), meetings=len(set(meet)))
ASP = ('style', 'content', 'coordination', 'engagement')
def typed_row(a):
    args = []
    for ai, asp in enumerate(ASP):
        base = 2 + 24 * ai
        for si, s in enumerate('AB'):
            o = 'B' if s == 'A' else 'A'
            for j in range(3):
                args.append(dict(id=f'r{base+3*si+j}', variable=base+3*si+j, kind='reason', side=s, aspect=asp, validity=math.log(max(a[f'{asp}{j}_{s}'], 1e-6)), grounding=0.0, target=None))
                args.append(dict(id=f'b{base+6+3*si+j}', variable=base+6+3*si+j, kind='rebuttal', side=s, aspect=asp, validity=math.log(max(a[f'{asp}{j}_{o}'], 1e-6)), grounding=0.0, target=f'r{base+3*si+j}'))
    return dict(arguments=args, relations=[])
def mcnemar(p, q, gold):
    a = (p == gold); b = (q == gold); w = int((a & ~b).sum()); l = int((~a & b).sum())
    return w, l, (binomtest(w, w + l, .5).pvalue if w + l else 1.0)
def boot(p, q, gold, B=10000, seed=2026):
    rng = np.random.default_rng(seed); ms = sorted(set(meet)); idx = {m: np.where(meet == m)[0] for m in ms}; d = []
    for _ in range(B):
        s = np.concatenate([idx[m] for m in rng.choice(ms, len(ms))]); d.append((p[s] == gold[s]).mean() - (q[s] == gold[s]).mean())
    return [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
maj = np.ones(N, bool)
def entry(name, pred, gold, score=None, vs=maj):
    c = int((pred == gold).sum()); lo, hi = binomtest(c, N).proportion_ci(.95); w, l, p = mcnemar(pred, vs, gold)
    e = dict(correct=c, acc=round(100 * c / N, 1), ci=[round(100 * lo, 1), round(100 * hi, 1)], vs_majority=dict(wins=w, losses=l, mcnemar_p=p, cluster_boot_ci=[round(100 * v, 1) for v in boot(pred, vs, gold)]))
    if score is not None: e['auc'] = round(float(roc_auc_score(gold, score)), 3)
    res[name] = e; print(f"{name:34s} {c:3d}/{N} {e['acc']:5.1f}%  vs majority: +{w}/-{l} p={p:.2g} bootCI{e['vs_majority']['cluster_boot_ci']}" + (f" AUC={e['auc']}" if score is not None else "")); return pred
res['majority_A'] = dict(correct=int(y.sum()), acc=round(100 * y.mean(), 1)); print("majority A", int(y.sum()), "/", N, " Wu-label majority A", int(yw.sum()))
# released attribution (Wu's text and labels), restricted to the same 150 ids
def direct(A, k):
    a = np.array([A[i][k + '_A'] for i in ids]); b = np.array([A[i][k + '_B'] for i in ids]); return a / (a + b)
def graph(A): return np.array([xor(typed_row(A[i]), rules)['prediction'] == 'A' for i in ids])
P = {}
p = direct(A1, 'professor'); P['rel_prof'] = entry('released/jev_professor', p >= .5, yw, p, vs=maj)
p = direct(A1, 'more_power'); entry('released/jev_power', p >= .5, yw, p)
P['rel_graph'] = entry('released/jev_graph', graph(A3), yw)
for c in ('fixed', 'ctx15', 'ctx60'):
    p = direct(A4[c], 'professor'); P[c + '_prof'] = entry(f'{c}/jev_professor', p >= .5, y, p); res[f'{c}/jev_professor']['brier'] = round(float(np.mean((p - y) ** 2)), 3)
    conf = np.abs(p - .5); o = np.argsort(-conf); res[f'{c}/jev_professor']['acc_top'] = {f: round(100 * float(((p >= .5) == y)[o][:int(N * f / 100)].mean()), 1) for f in (20, 40, 60, 100)}
    p2 = direct(A4[c], 'more_power'); entry(f'{c}/jev_power', p2 >= .5, y, p2)
    P[c + '_graph'] = entry(f'{c}/jev_graph', graph(A4[c]), y)
    lin = np.array([sum(A4[c][i][f'{a}{j}_A'] - A4[c][i][f'{a}{j}_B'] for a in ASP for j in range(3)) for i in ids]); entry(f'{c}/jev_statement_sum', lin >= 0, y, lin)
res['brier_base_rate'] = round(float(np.mean((y.mean() - y) ** 2)), 3)
# heuristics
def turns(o, k):
    S = M[o['meeting']]; a = max(0, o['start'] - k); b = min(len(S), o['start'] + o['n'] + k); let = dict(o['letters']); T = []
    for _, sp, tx in S[a:b]:
        if sp not in let: let[sp] = [c for c in 'CDEFGHIJKLMN' if c not in let.values()][0]
        if T and T[-1]['speaker'] == let[sp]: T[-1]['text'] += ' ' + tx
        else: T.append({'speaker': let[sp], 'text': tx})
    return T
for c, k in (('fixed', 0), ('ctx15', 15), ('ctx60', 60)):
    W = []; LT = []
    for o in FX:
        w = collections.Counter(); nt = collections.Counter()
        for t in turns(o, k): w[t['speaker']] += len(t['text'].split()); nt[t['speaker']] += 1
        W.append(w['A'] - w['B']); LT.append(w['A'] / max(nt['A'], 1) - w['B'] / max(nt['B'], 1))
    W = np.array(W); LT = np.array(LT); P[c + '_words'] = entry(f'{c}/more_words', W >= 0, y, W); entry(f'{c}/longer_turns', LT >= 0, y, LT)
Wd = []
for i in ids:
    t = re.split(r'(?m)^\s*([AB]):', R[i]['transcript']); w = {'A': 0, 'B': 0}
    for j in range(1, len(t) - 1, 2): w[t[j]] += len(t[j + 1].split())
    Wd.append(w['A'] - w['B'])
Wd = np.array(Wd); entry('released/more_words', Wd >= 0, yw, Wd)
# paired: corrected vs released, and context
for a, b, ga, gb in (('fixed_prof', 'rel_prof', y, yw), ('fixed_graph', 'rel_graph', y, yw), ('ctx15_prof', 'fixed_prof', y, y), ('ctx60_prof', 'ctx15_prof', y, y), ('ctx60_prof', 'fixed_prof', y, y), ('fixed_prof', 'fixed_words', y, y), ('fixed_graph', 'fixed_prof', y, y), ('ctx60_graph', 'ctx60_prof', y, y)):
    ca = P[a] == ga; cb = P[b] == gb; w = int((ca & ~cb).sum()); l = int((~ca & cb).sum()); p = binomtest(w, w + l, .5).pvalue if w + l else 1.0
    res[f'paired/{a}_vs_{b}'] = dict(wins=w, losses=l, p=p); print(f"paired {a} vs {b}: +{w}/-{l} p={p:.2g}")
# attribution audit numbers
cons = [x for x in rows if x['consistent'] and len(x['profs']) == 1]
res['audit'] = dict(matched=151, consistent=len(cons))
wrong = tot = heavy = 0
for x in cons:
    L = snippet_lines(R[x['id']]['transcript']); segs = M[x['meeting']][x['start']:x['start'] + x['n']]; wr = tw = 0
    for (lab, t), s in zip(L, segs):
        n = len(t.split()); tw += n; wr += n * (s[1] != (x['mapA'] if lab == 'A' else x['mapB']))
    wrong += wr; tot += tw; heavy += wr / tw > .5
res['audit'].update(words_wrong=wrong, words_total=tot, pct=round(100 * wrong / tot, 1), heavy=heavy)
# professors, per-professor accuracy, label by professor
profs = collections.Counter(); byp = collections.defaultdict(list)
for o, ok in zip(FX, P['fixed_prof'] == y):
    pr = [s for s, l in o['letters'].items() if l == o['label']][0]; profs[pr] += 1; byp[pr].append(ok)
res['professors'] = {p: dict(n=n, fixed_acc=round(100 * float(np.mean(byp[p])), 1)) for p, n in profs.most_common()}
res['labels_changed_vs_wu'] = int((y != yw).sum()); res['multi_speaker'] = sum(len(o['letters']) > 2 for o in FX)
print(res['audit'], res['professors'], "labels changed", res['labels_changed_vs_wu'], "brier base", res['brier_base_rate'])
for c in ('fixed', 'ctx15', 'ctx60'): print(c, res[f'{c}/jev_professor']['brier'], res[f'{c}/jev_professor']['acc_top'])
json.dump(res, open('results.json', 'w'), indent=1)
