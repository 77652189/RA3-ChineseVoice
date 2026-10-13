"""Drop dub takes that have the wrong voice, before pick.py chooses among the rest (run with the IndexTTS venv).

  third_party/index-tts/.venv/Scripts/python -I -X utf8 tools/speaker_filter.py work/speakers/suspects.json

For each listed movie line, every candidate take in candidates/movie/ is compared with its own actor's clean
reference (original/movie_clean, or the same-actor stand-in from work/speakers/fallback.json for short lines):
  - pitch: pYIN median of take / reference must lie within tools/speakers.py F0_LO..F0_HI
    (YIN, which speakers.py uses for the bulk pass, jumps octaves on short lines; pYIN is steadier), and
  - fingerprint: the take must not sound more like another actor of the same movie than like its own one
    (same margin as tools/speakers.py).
Failing takes move to archive/speaker_rejected/movie/. If every take of a line fails, the one closest to its own
actor stays, so pick.py always has something to choose from.
"""
import csv
import glob
import json
import os
import shutil
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from speakers import F0_HI, F0_LO, GOOD, OTHER, REF, Fingerprint, load_16k   # noqa: E402

CAND = os.path.join(ROOT, 'candidates', 'movie')
REJECT = os.path.join(ROOT, 'archive', 'speaker_rejected', 'movie')


def pyin_f0(y):
    import librosa
    f, v, p = librosa.pyin(y, fmin=60, fmax=600, sr=16000, frame_length=1024)
    f = f[v & (p > 0.5)]
    f = f[~np.isnan(f)]
    return float(np.median(f)) if len(f) > 5 else 0.0


def main(listing):
    assets = json.load(open(listing, encoding='utf-8'))
    with open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig') as f:
        rows = {r['asset']: r for r in csv.DictReader(f)}
    fallback = json.load(open(os.path.join(ROOT, 'work', 'speakers', 'fallback.json'), encoding='utf-8'))
    ov_path = os.path.join(ROOT, 'work', 'speakers', 'ref_override.json')
    override = json.load(open(ov_path, encoding='utf-8')) if os.path.exists(ov_path) else {}
    fp = Fingerprint()
    cache = {}

    def ref(a):
        if a not in cache:
            y = load_16k(os.path.join(REF, a + '.wav'))
            cache[a] = (fp(y), pyin_f0(y), len(y) / 16000)
        return cache[a]
    os.makedirs(REJECT, exist_ok=True)
    kept_total = dropped_total = 0
    for a in assets:
        own_id = override.get(a) or fallback.get(a, a)   # the reference the take was dubbed from
        own_emb, own_f0, _ = ref(own_id)
        movie = rows[a]['movie']
        mates = [b for b, r in rows.items() if r['movie'] == movie and r['games'] == rows[a]['games'] and b != own_id
                 and os.path.exists(os.path.join(REF, b + '.wav'))]
        others = [b for b in mates if ref(b)[2] >= GOOD and float(ref(b)[0] @ own_emb) < OTHER]
        takes = sorted(glob.glob(os.path.join(CAND, a + '_*.wav')))
        scored = []
        for t in takes:
            y = load_16k(t)
            e, f0 = fp(y), pyin_f0(y)
            s_own = float(e @ own_emb)
            s_other = max((float(e @ ref(b)[0]) for b in others), default=-1.0)
            pitch_ok = not (own_f0 > 0 and f0 > 0) or F0_LO <= f0 / own_f0 <= F0_HI
            ok = pitch_ok and s_other <= s_own + 0.05
            scored.append((ok, s_own - s_other, t, f0))
        good = [s for s in scored if s[0]]
        keep = good or [max(scored, key=lambda s: s[1])]
        for s in scored:
            if s not in keep:
                shutil.move(s[2], os.path.join(REJECT, os.path.basename(s[2])))
        kept_total += len(keep)
        dropped_total += len(scored) - len(keep)
        print(f'{a}: {len(good)}/{len(scored)} takes pass' + ('' if good else ' (none pass; kept the closest)'), flush=True)
    print(f'kept {kept_total}, moved {dropped_total} takes to {REJECT}')


if __name__ == '__main__':
    main(sys.argv[1])
