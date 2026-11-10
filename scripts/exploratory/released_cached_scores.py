import os
import json, math, re, sys, numpy as np
sys.path.insert(0, os.path.join(os.environ.get('KRISH_REPO', 'nlp_research'), 'src'))
from quote_power.inference import xor, grounded, grounded_labels, kept
from scipy.stats import binomtest
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
R = [json.loads(l) for l in open('data/snippets.jsonl')]; rules = open('data/rules.txt').read()
y = np.array([r['label'] == 'A' for r in R]); N = len(R)
ann = {}
for l in open(os.path.join(os.environ.get('KRISH_REPO', 'nlp_research'), 'results/experiment/quote_annotations.jsonl')):
    d = json.loads(l); ann[d['id']] = d
zs = {}
for l in open(os.path.join(os.environ.get('KRISH_REPO', 'nlp_research'), 'results/experiment/zero_shot.jsonl')):
    d = json.loads(l); zs[d['id']] = d['probability_A']
pz = np.array([zs[r['id']] for r in R])
def rep(name, pred):
    pred = np.array(pred); c = int((pred == y).sum())
    lo, hi = binomtest(c, N).proportion_ci(0.95)
    print(f"{name:52s} {c:3d}/151 = {100*c/N:5.1f}%  CI[{100*lo:.0f},{100*hi:.0f}]  predA={int(pred.sum())}")
    return pred
print("labels A:", y.sum())
rep("majority A", np.ones(N, bool))
px = rep("XOR cached (Krish repro)", [xor(r, rules)['prediction'] == 'A' for r in R])
rep("grounded unfiltered", [grounded(r)['prediction'] == 'A' for r in R])
rep("zero-shot Gemma4", pz >= .5); rep("zero-shot Gemma4 FLIPPED", pz < .5)
print("zero-shot AUC for label A:", round(roc_auc_score(y, pz), 3))
# ---- hybrid 1: grounded labelling as a pre-filter, then XOR factor graph
def hybrid(r, quote):
    args = kept(r, ann, quote); ids = {a['id'] for a in args}; reasons = [a for a in args if a['kind'] == 'reason']
    att = [(a['id'], a['target']) for a in args if a['kind'] == 'rebuttal' and a['target'] in ids]
    att += [(a['id'], b['id']) for a in reasons for b in reasons if a['side'] != b['side']]
    lab = grounded_labels(ids, att)
    keep_ids = {i for i, v in lab.items() if v != 'OUT'}
    fake = {a['id']: dict(evidence_speaker='A', supports=a['id'] in keep_ids, attribution_correct=True, quote='') for a in r['arguments']}
    # reuse xor with a custom kept set
    import quote_power.inference as inf
    old = inf.kept; inf.kept = lambda row, an, qf: [a for a in row['arguments'] if a['id'] in keep_ids]
    try: out = inf.xor(r, rules)
    finally: inf.kept = old
    return out
for q in (False, True):
    o = [hybrid(r, q) for r in R]
    rep(f"HYBRID grounded-prune -> XOR (quote filter={q})", [x['prediction'] == 'A' for x in o])
    print("    fallbacks (no surviving reasons):", sum('fallback' in x for x in o))
# ---- gradual semantics (DF-QuAD style) on cached scores: strength = base * (1 - attacker strength)
def base(a, mode):
    v, g = math.exp(a['validity']), math.exp(a['grounding'])
    return {'vg': v * g, 'v': v, 'g': g}[mode]
def gradual(r, mode, agg, use_reb=True):
    byid = {a['id']: a for a in r['arguments']}; s = {'A': [], 'B': []}
    reb = {a['target']: a for a in r['arguments'] if a['kind'] == 'rebuttal'}
    for a in r['arguments']:
        if a['kind'] != 'reason': continue
        b = base(a, mode)
        if use_reb and a['id'] in reb: b *= 1 - base(reb[a['id']], mode)
        s[a['side']].append(b)
    f = {'sum': np.sum, 'max': np.max, 'mean': np.mean}[agg]
    return f(s['A']) - f(s['B'])
G = {}
for use_reb in (False, True):
    for mode in ('vg', 'v', 'g'):
        for agg in ('sum', 'max'):
            d = np.array([gradual(r, mode, agg, use_reb) for r in R]); G[(use_reb, mode, agg)] = d
            rep(f"gradual reb={use_reb} base={mode} agg={agg}", d >= 0)
            print("    AUC:", round(roc_auc_score(y, d), 3))
# ---- is there ANY signal in the cached scores? leave-one-out logistic regression
def feats(r):
    f = []
    for asp in ('style', 'content', 'coordination', 'engagement'):
        for kind in ('reason', 'rebuttal'):
            for key in ('validity', 'grounding'):
                v = {s: np.mean([math.exp(a[key]) for a in r['arguments'] if a['aspect'] == asp and a['kind'] == kind and a['side'] == s]) for s in 'AB'}
                f.append(v['A'] - v['B'])
    return f
X = np.array([feats(r) for r in R])
for C in (0.01, 0.1, 1.0):
    p = cross_val_predict(make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=2000)), X, y, cv=LeaveOneOut())
    rep(f"LOO logistic on 16 cached-score features C={C}", p)
# ---- surface features of the transcript, no LLM
def surf(r):
    t = re.split(r'(?m)^\s*([AB]):', r['transcript']); w = {'A': 0, 'B': 0}; q = {'A': 0, 'B': 0}; n = {'A': 0, 'B': 0}
    for i in range(1, len(t) - 1, 2):
        w[t[i]] += len(t[i + 1].split()); q[t[i]] += t[i + 1].count('?'); n[t[i]] += 1
    return [w['A'] - w['B'], q['A'] - q['B'], math.log((w['A'] + 1) / (w['B'] + 1)), 1.0 * (t[1] == 'A')]
S = np.array([surf(r) for r in R])
print("first speaker is A in", int(S[:, 3].sum()), "snippets")
rep("rule: more words => power", S[:, 0] >= 0); rep("rule: FEWER words => power", S[:, 0] < 0)
rep("rule: more questions => power", S[:, 1] >= 0); print("    AUC words:", round(roc_auc_score(y, S[:, 0]), 3), " AUC questions:", round(roc_auc_score(y, S[:, 1]), 3))
p = cross_val_predict(make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000)), S[:, :3], y, cv=LeaveOneOut()); rep("LOO logistic on surface features", p)
p = cross_val_predict(make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000)), np.c_[X, S[:, :3], pz], y, cv=LeaveOneOut()); rep("LOO logistic on everything", p)
# permutation null: best of the 12 gradual variants under shuffled labels
rng = np.random.default_rng(0); best = max(((d >= 0) == y).sum() for d in G.values()); cnt = 0
for _ in range(5000):
    yy = rng.permutation(y); cnt += max(((d >= 0) == yy).sum() for d in G.values()) >= best
print(f"best gradual variant {best}/151; P(best-of-12 >= that | shuffled labels) = {cnt/5000:.3f}")
print("needed for p<.05 one-sided vs 55% base rate:", next(k for k in range(83, 152) if binomtest(k, N, 83/151, alternative='greater').pvalue < .05), "/151")
