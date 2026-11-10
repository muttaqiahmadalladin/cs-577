import os
import json, math, sys, numpy as np
sys.path.insert(0, os.path.join(os.environ.get('KRISH_REPO', 'nlp_research'), 'src'))
from quote_power.inference import xor, grounded_labels
from scipy.stats import binomtest
from sklearn.metrics import roc_auc_score
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
R = [json.loads(l) for l in open('data/snippets.jsonl')]; rules = open('data/rules.txt').read()
A1 = {json.loads(l)['id']: json.loads(l)['answers'] for l in open('jev_arm1.jsonl')}
A2 = {json.loads(l)['id']: json.loads(l)['answers'] for l in open('jev_arm2.jsonl')}
y = np.array([r['label'] == 'A' for r in R]); N = len(R)
zs = {json.loads(l)['id']: json.loads(l)['probability_A'] for l in open(os.path.join(os.environ.get('KRISH_REPO', 'nlp_research'), 'results/experiment/zero_shot.jsonl'))}
pz = np.array([zs[r['id']] for r in R])
def rep(name, pred, score=None):
    pred = np.array(pred); c = int((pred == y).sum()); lo, hi = binomtest(c, N).proportion_ci(.95)
    s = f"{name:44s} {c:3d}/151 = {100*c/N:5.1f}%  CI[{100*lo:.0f},{100*hi:.0f}] predA={int(pred.sum()):3d}"
    if score is not None: s += f"  AUC={roc_auc_score(y, score):.3f}"
    print(s); return c
def brier(p): return float(np.mean((p - y) ** 2))
def cov(p, name):
    conf = np.abs(p - .5); o = np.argsort(-conf); corr = ((p >= .5) == y)[o]
    print(f"  {name}: acc at top 20/40/60/100% confident = " + " / ".join(f"{100*corr[:int(N*f)].mean():.0f}%" for f in (.2, .4, .6, 1)) + f"   Brier={brier(p):.3f}  mean|p-.5|={conf.mean():.2f}")
print("== ARM 1: System 1 on the raw snippet ==")
rep("majority A", np.ones(N, bool)); rep("Gemma4 zero-shot (Krish)", pz >= .5, pz)
g = lambda k: np.array([A1[r['id']][k] for r in R])
P = {}
for k in ('professor', 'more_power'):
    a, b = g(k + '_A'), g(k + '_B'); P[k] = a / (a + b)
    rep(f"Jev direct: {k}", P[k] >= .5, P[k])
    print(f"   consistency: mean(pA+pB)={np.mean(a+b):.2f}, both>0.5 in {int(((a>.5)&(b>.5)).sum())}, both<0.5 in {int(((a<.5)&(b<.5)).sum())}")
print("calibration / selective prediction (base-rate Brier = %.3f):" % brier(np.full(N, y.mean())))
cov(pz, "Gemma4 "); cov(P['professor'], "Jev prof"); cov(P['more_power'], "Jev power")
SIGN = dict(evaluates=1, directs=1, asks_status=1, picks_topic=1, explains_own=-1, seeks_assent=-1, unsure=-1, backchannels=-1)
D = {k: g(k + '_A') - g(k + '_B') for k in SIGN}
print("per-cue AUC for 'A is professor' (expected sign in brackets):")
for k, s in SIGN.items(): print(f"   {k:14s} [{'+' if s>0 else '-'}] AUC={roc_auc_score(y, D[k]):.3f}   mean|diff|={np.abs(D[k]).mean():.2f}")
cue = sum(s * D[k] for k, s in SIGN.items()); rep("Jev cue score (fixed signs, equal weights)", cue >= 0, cue)
X = np.c_[[D[k] for k in SIGN]].T
for C in (.1, 1.):
    p = cross_val_predict(make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=2000)), X, y, cv=LeaveOneOut(), method='predict_proba')[:, 1]
    rep(f"LOO logistic on 8 cue diffs C={C}", p >= .5, p)
print("\n== ARM 2: Jev scores Wu's cached arguments ==")
gs = lambda r, a, t: max(A2[r['id']][f"{t}{a['variable']}"], 1e-6)
allr = [(r, a) for r in R for a in r['arguments']]
for kind in ('reason', 'rebuttal'):
    xs = [(r, a) for r, a in allr if a['kind'] == kind]
    print(f"{kind}s: grounded>=.5 {np.mean([gs(r,a,'g')>=.5 for r,a in xs]):.1%}, valid>=.5 {np.mean([gs(r,a,'v')>=.5 for r,a in xs]):.1%}" + (f", rebuttal counters its reason>=.5 {np.mean([gs(r,a,'r')>=.5 for r,a in xs]):.1%}" if kind == 'rebuttal' else ""))
def rescored(r):
    r2 = dict(r); r2['arguments'] = []
    for a in r['arguments']:
        b = dict(a); b['validity'] = math.log(gs(r, a, 'v')); b['grounding'] = math.log(gs(r, a, 'g' if a['kind'] == 'reason' else 'r')); r2['arguments'].append(b)
    return r2
R2 = [rescored(r) for r in R]
rep("XOR graph, cached GPT-3.5 scores", [xor(r, rules)['prediction'] == 'A' for r in R])
rep("XOR graph, Jev scores", [xor(r, rules)['prediction'] == 'A' for r in R2])
def sc(a): return math.exp(a['validity'] + a['grounding'])
def gr(r, reb, cross):
    args = r['arguments']; reasons = [a for a in args if a['kind'] == 'reason']; byid = {a['id']: a for a in args}; att = []
    for a in args:
        if a['kind'] != 'rebuttal': continue
        t = byid[a['target']]
        ok = {'all': True, 'gate': math.exp(a['grounding']) >= .5, 'pref': sc(a) >= sc(t)}[reb]
        if ok: att.append((a['id'], t['id']))
    if cross == 'mutual': att += [(a['id'], b['id']) for a in reasons for b in reasons if a['side'] != b['side']]
    if cross == 'pref': att += [(a['id'], b['id']) for a in reasons for b in reasons if a['side'] != b['side'] and sc(a) > sc(b)]
    lab = grounded_labels({a['id'] for a in args}, att)
    c = {s: sum(lab[a['id']] == 'IN' for a in reasons if a['side'] == s) for s in 'AB'}
    sm = {s: sum(sc(a) for a in reasons if a['side'] == s) for s in 'AB'}
    return c, sm, sum(lab[a['id']] == 'IN' for a in reasons)
for reb, cross in (('all', 'mutual'), ('gate', 'mutual'), ('gate', 'none'), ('gate', 'pref'), ('pref', 'pref')):
    o = [gr(r, reb, cross) for r in R2]; d = np.array([c['A'] - c['B'] for c, sm, n in o]); tb = np.array([sm['A'] - sm['B'] for c, sm, n in o])
    pred = np.where(d != 0, d > 0, tb >= 0)
    rep(f"grounded, rebuttal={reb}, cross={cross}", pred, d + 1e-3 * np.sign(tb))
    print(f"   IN reasons={sum(n for c,sm,n in o)}, snippets decided by IN count={int((d!=0).sum())}, correct among those={int(((d>0)==y)[d!=0].sum())}")
dq = np.array([sum(sc(a) * (1 - sc(next(b for b in r['arguments'] if b['kind']=='rebuttal' and b['target']==a['id']))) * (1 if a['side']=='A' else -1) for a in r['arguments'] if a['kind']=='reason') for r in R2])
rep("gradual (DF-QuAD style) on Jev scores", dq >= 0, dq)
gd = np.array([sum(math.exp(a['grounding']) * (1 if a['side']=='A' else -1) for a in r['arguments'] if a['kind']=='reason') for r in R2]); rep("sum of grounded-reason probs, no graph", gd >= 0, gd)
print("\nneeded to beat 55% base rate at p<.05: 94/151; to beat 50% chance: ", next(k for k in range(76, 152) if binomtest(k, N, .5, alternative='greater').pvalue < .05), "/151")
print("agreement Jev prof vs Gemma:", np.mean((P['professor']>=.5)==(pz>=.5)).round(2), " Jev prof vs Jev power:", np.mean((P['professor']>=.5)==(P['more_power']>=.5)).round(2))
