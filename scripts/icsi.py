"""ICSI MRT parsing and snippet matching shared by the other scripts."""
import re, json, glob, os, collections
ICSI = os.environ.get('ICSI_DIR', 'icsi')  # unzip icsi_mrt.zip to $ICSI_DIR/mrt and icsi_core_nxt.zip to $ICSI_DIR/nxt
EDU = dict(re.findall(r'<speaker[^>]*tag="(\w+)">\s*<education[^>]*>([^<]*)<', open(f'{ICSI}/nxt/ICSI/speakers.xml', encoding='latin-1').read()))
def clean(t):
    t = re.sub(r'<[^>]+>', '', t)
    return ' '.join(t.split())
def meetings():
    M = {}
    for f in sorted(glob.glob(f'{ICSI}/mrt/transcripts/B*.mrt')):
        x = open(f, encoding='latin-1').read(); segs = []
        for m in re.finditer(r'<Segment\s+StartTime="([\d.]+)"\s+EndTime="([\d.]+)"([^>]*)>(.*?)</Segment>', x, re.S):
            p = re.search(r'Participant="(\w+)"', m.group(3)); txt = clean(m.group(4))
            if p and txt: segs.append((float(m.group(1)), p.group(1), txt))
        M[os.path.basename(f)[:-4]] = segs
    return M
def snippet_lines(tr):
    out = []
    for ln in tr.split('\n'):
        m = re.match(r'\s*([AB]):\s?(.*)', ln)
        if m: lab = m.group(1); txt = m.group(2)
        else: txt = ln
        if ' '.join(txt.split()): out.append((lab, ' '.join(txt.split())))
    return out
def locate(lines, M):
    texts = [t for _, t in lines]; hits = []
    for name, segs in M.items():
        st = [s[2] for s in segs]
        for i in range(len(st) - len(texts) + 1):
            if st[i] == texts[0] and st[i:i + len(texts)] == texts: hits.append((name, i))
    return hits
