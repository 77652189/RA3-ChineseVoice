"""Median pitch of every movie line: clean English reference vs current Chinese dub (CPU only).

  third_party/index-tts/.venv/Scripts/python -I -X utf8 docs/article/pitch_snapshot.py <label>

Writes docs/article/data/pitch_<label>.json  {asset: [ref_hz, dub_hz]}  for the article's before/after figure.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from speakers import load_16k, median_f0, REF, DUB   # noqa: E402

out = {}
names = sorted(n for n in os.listdir(DUB) if n.endswith('.wav'))
for i, n in enumerate(names):
    ref = os.path.join(REF, n)
    if not os.path.exists(ref):
        continue
    out[n[:-4]] = [median_f0(load_16k(ref)), median_f0(load_16k(os.path.join(DUB, n)))]
    if i % 500 == 0:
        print(i, len(names), flush=True)
d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(d, exist_ok=True)
json.dump(out, open(os.path.join(d, f'pitch_{sys.argv[1]}.json'), 'w'), indent=0)
print('lines', len(out))
