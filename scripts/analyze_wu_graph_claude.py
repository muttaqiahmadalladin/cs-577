import json, sys, math, os, numpy as np, collections
sys.path.insert(0, 'nlp_research/src')
from quote_power.inference import xor
from scipy.stats import binomtest
from sklearn.metrics import roc_auc_score
FX = json.load(open('./fixed_index.json')); ids = [o['id'] for o in FX]; y = np.array([o['label'] == 'A' for o in FX]); N = len(ids)
meet = np.array([o['meeting'] for o in FX]); rules = open('./data/rules.txt').read()
ASP = ['style', 'content', 'coordination', 'engagement']
bat = {x['id']: k for k in range(10) for x in json.load(open(f'in/score_{k}.json'))}
S = {i: json.load(open(f'score/{i}.json'))['aspects'] for i in ids}
# quality check per scoring batch
for k in range(10):
    v = [p for i in ids if bat[i] == k for a in ASP for kind in ('reason', 'rebuttal') for s in 'AB' for pr in S[i][a][kind][s] for p in pr]
    uniq_rows = len({json.dumps(S[i], sort_keys=True) for i in ids if bat[i] == k})
    print(f"batch {k}: n={len(v)} mean={np.mean(v):.2f} sd={np.std(v):.2f} distinct values={len(set(np.round(v, 2)))} distinct snippets={uniq_rows}/15")
def row(i, mode):
    args = []; rel = []
    for ai, a in enumerate(ASP):
        b = S[i][a]; base = 2 + 24 * ai
        for si, s in enumerate('AB'):
            for j in range(3):
                v, g = b['reason'][s][j]
                args.append(dict(id=f'r{base+3*si+j}', variable=base+3*si+j, kind='reason', side=s, aspect=a, validity=math.log(max(v, 1e-6)), grounding=math.log(max(g, 1e-6)), target=None))
                if mode != 'reasons':
                    v, g = b['rebuttal'][s][j]
                    args.append(dict(id=f'b{base+6+3*si+j}', variable=base+6+3*si+j, kind='rebuttal', side=s, aspect=a, validity=math.log(max(v, 1e-6)), grounding=math.log(max(g, 1e-6)), target=f'r{base+3*si+j}'))
        if mode == 'all':
            for j, sc in enumerate(b['similar'] + b['contra_A'] + b['contra_B']): rel.append({'variable': base + 12 + j, 'score': sc / 5})
    return dict(arguments=args, relations=rel)
maj = np.ones(N, bool); res = {}
def rep(name, pred, score=None):
    c = int((pred == y).sum()); w = int(((pred == y) & (maj != y)).sum()); l = int(((pred != y) & (maj == y)).sum()); p = binomtest(w, w + l, .5).pvalue
    rng = np.random.default_rng(2026); ms = sorted(set(meet)); idx = {m: np.where(meet == m)[0] for m in ms}
    d = [((pred[s] == y[s]).mean() - y[s].mean()) for s in (np.concatenate([idx[m] for m in rng.choice(ms, len(ms))]) for _ in range(5000))]
    res[name] = dict(correct=c, acc=round(100*c/N, 1), wins=w, losses=l, p=p, boot=[round(100*np.percentile(d, 2.5), 1), round(100*np.percentile(d, 97.5), 1)])
    print(f"{name:44s} {c}/{N} = {100*c/N:.1f}%  vs majority +{w}/-{l} p={p:.2g} boot{res[name]['boot']}" + (f" AUC={roc_auc_score(y, score):.3f}" if score is not None else "")); return pred
print("majority", int(y.sum()))
P = {}
for mode, nm in (('reasons', 'Wu graph, reasons only'), ('rr', 'Wu graph, reasons + rebuttals'), ('all', 'Wu graph, all relations')):
    P[mode] = rep(f"{nm} (Haiku args, Haiku scores)", np.array([xor(row(i, mode), rules)['prediction'] == 'A' for i in ids]))
# no-graph baseline from the same scores: sum of valid*grounded for reasons
d = np.array([sum(v * g * (1 if s == 'A' else -1) for a in ASP for s in 'AB' for v, g in S[i][a]['reason'][s]) for i in ids]); rep("sum of reason scores, no graph", d >= 0, d)
for m in ('haiku', 'sonnet'):
    Z = {}
    for k in range(3): Z.update(json.load(open(f'zero_{m}/zero_{k}.json')))
    p = np.array([float(Z[i]['p_A']) for i in ids]); P['z' + m] = rep(f"zero-shot {m}", np.array([Z[i]['answer'] == 'A' for i in ids]), p)
A4 = {}
for l in open('./jev_arm4.jsonl'):
    dd = json.loads(l)
    if dd['cond'] == 'fixed': A4[dd['id']] = dd['answers']
pj = np.array([A4[i]['professor_A'] / (A4[i]['professor_A'] + A4[i]['professor_B']) for i in ids]); P['jev'] = rep("Jev direct (for reference)", pj >= .5, pj)
for a, b in (('all', 'zhaiku'), ('all', 'zsonnet'), ('all', 'jev'), ('all', 'reasons'), ('zsonnet', 'jev')):
    ca, cb = P[a] == y, P[b] == y; w, l = int((ca & ~cb).sum()), int((~ca & cb).sum()); print(f"paired {a} vs {b}: +{w}/-{l} p={binomtest(w, w+l, .5).pvalue if w+l else 1:.2g}")
json.dump(res, open('wu_claude_results.json', 'w'), indent=1)
