"""Face-first quality gate: marks cases whose cached portrait is a real, clear photo (c['fq'] = 1).
Placeholders (FBI seal, grey silhouette) are detected by comparing a 16x16 thumbnail with reference
signatures in face_refs.json; tiny files and hand-reviewed weak portraits (face_skip.txt) are skipped."""
import os, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NEVER = {'missing', 'parental', 'seeking'}

def _load():
    refs = json.load(open(os.path.join(HERE, 'face_refs.json')))
    skip = set()
    p = os.path.join(HERE, 'face_skip.txt')
    if os.path.exists(p):
        skip = {l.strip() for l in open(p) if l.strip() and not l.startswith('#')}
    return {k: bytes.fromhex(v) for k, v in refs.items()}, skip

def _dist(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)

def mark(cases):
    from PIL import Image
    refs, skip = _load()
    n = 0
    for c in cases:
        c.pop('fq', None)
        im = c.get('im')
        if not im or c['id'] in skip or c.get('c') in NEVER: continue   # victims / missing people are never game rounds
        p = os.path.join(ROOT, im)
        if not os.path.exists(p) or os.path.getsize(p) < 2000: continue
        try: s = Image.open(p).convert('RGB').resize((16, 16)).tobytes()
        except Exception: continue
        if min(_dist(s, r) for r in refs.values()) < 30: continue
        c['fq'] = 1; n += 1
    return n
