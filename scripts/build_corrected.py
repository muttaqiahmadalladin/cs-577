"""Locate Wu et al.'s 151 released snippets in the ICSI corpus and rebuild them with true speakers.

Inputs : data/snippets.jsonl (from `quote-power prepare` in KrishMay05/nlp_research), ICSI_DIR with mrt/ and nxt/
Outputs: rows.json (audit per snippet), fixed_index.json (corrected set), contexts.jsonl (states sent to Jev)
"""
import json, re, collections
from icsi import meetings, snippet_lines, locate, EDU

M = meetings(); R = [json.loads(l) for l in open('data/snippets.jsonl')]
SET2 = "Excerpt from a university research group meeting. Exactly one of the two speakers, A and B, is a professor and the other is a student."
SET3 = SET2 + " Other people in the meeting are labeled C, D, and so on."
rows, fixed = [], []
for r in R:
    L = snippet_lines(r['transcript']); hits = locate(L, M); assert len(hits) == 1, (r['id'], len(hits))
    name, i = hits[0]; segs = M[name][i:i + len(L)]; spk = [s[1] for s in segs]
    # Wu's displayed turns: a new "A:" / "B:" prefix opens a turn; each letter is taken to be the
    # speaker of the turn's last line (the only mapping under which the released labels are right)
    tl, idx = [], 0
    for ln in r['transcript'].split('\n'):
        m = re.match(r'\s*([AB]):\s?(.*)', ln); txt = m.group(2) if m else ln
        if m: tl.append([m.group(1), []])
        if ' '.join(txt.split()): tl[-1][1].append(idx); idx += 1
    assign = collections.defaultdict(set)
    for lab, ids in tl:
        if ids: assign[lab].add(spk[ids[-1]])
    a = next(iter(assign['A']), None); b = next(iter(assign['B']), None)
    consistent = len(assign['A']) == 1 and len(assign['B']) == 1 and a != b
    real = list(dict.fromkeys(spk)); profs = [s for s in real if EDU.get(s) == 'Professor']
    rows.append(dict(id=r['id'], meeting=name, start=i, n=len(L), mapA=a, mapB=b, consistent=consistent, profs=profs, real=sorted(real)))
    if len(profs) != 1 or len(real) < 2: continue
    prof = profs[0]
    if consistent: let = {a: 'A', b: 'B'}
    else:
        other = [s for s in real if s != prof][0]; first = [s for s in real if s in (prof, other)][0]
        let = {first: 'A', (other if first == prof else prof): 'B'}
    for s in real:
        if s not in let: let[s] = 'CDEFGH'[len(let) - 2]
    fixed.append(dict(id=r['id'], meeting=name, start=i, n=len(L), letters=let, label=let[prof], wu_label=r['label'], wu_consistent=consistent))

def turns(o, k):
    S = M[o['meeting']]; lo = max(0, o['start'] - k); hi = min(len(S), o['start'] + o['n'] + k); let = dict(o['letters']); T = []
    for _, sp, tx in S[lo:hi]:
        if sp not in let: let[sp] = [c for c in 'CDEFGHIJKLMN' if c not in let.values()][0]
        if T and T[-1]['speaker'] == let[sp]: T[-1]['text'] += ' ' + tx
        else: T.append({'speaker': let[sp], 'text': tx})
    return T

json.dump(rows, open('rows.json', 'w')); json.dump(fixed, open('fixed_index.json', 'w'))
with open('contexts.jsonl', 'w') as f:
    for o in fixed:
        for cond, k in (('fixed', 0), ('ctx15', 15), ('ctx60', 60)):
            T = turns(o, k)
            f.write(json.dumps(dict(id=o['id'], cond=cond, state=dict(setting=SET3 if any(t['speaker'] not in 'AB' for t in T) else SET2, turns=T))) + '\n')
print(f"located {len(rows)} snippets; corrected set {len(fixed)}; professor is A in {sum(o['label'] == 'A' for o in fixed)}")
