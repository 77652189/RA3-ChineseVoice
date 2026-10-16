"""Dubs in someone else's voice (run with the IndexTTS venv python; CPU).

  third_party/index-tts/.venv/Scripts/python -I -X utf8 tools/voice_audit.py   -> work/voice_audit/report.csv

speakers.py compared each movie dub with its own reference clip, so a reference that itself held the wrong voice
(R_afs07_08: cut at the subtitle time, which runs ~1.3 s ahead of the actor in full-screen movies, so it was
mostly the general's tail) passed. Here the comparison is against what the actor really said:
  movie lines  the separated vocal from the measured onset (work/align/report.csv) to the next line's onset;
  mission      the original clip (studio lines, one actor each).
A dub is listed when its pitch is far from that voice (male/female swap) or its CAMPPlus fingerprint is clearly
closer to another actor of the same movie / mission group than to its own.
"""
import csv
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from speakers import Fingerprint, median_f0  # noqa: E402
from ra3voice import audio_io, movie  # noqa: E402

OUT = os.path.join(ROOT, 'work', 'voice_audit')
F0_LO, F0_HI = 0.72, 1.39          # as speakers.py: about 5.7 semitones either way
MARGIN = 0.08                       # another actor this much closer than the own voice


def to16(x, sr):
    from math import gcd
    from scipy.signal import resample_poly
    q = gcd(sr, 16000)
    return resample_poly(np.asarray(x, dtype=np.float32), 16000 // q, sr // q).astype(np.float32)


def movie_refs():
    """{asset: 16 kHz clip of the actor's own English line} from the separated vocals and measured onsets."""
    rep = {r['asset']: r for r in csv.DictReader(open(os.path.join(ROOT, 'work', 'align', 'report.csv'), encoding='utf-8-sig'))}
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig')))
    by = {}
    for r in rows:
        by.setdefault((r['games'], r['movie']), []).append(r)
    out, group = {}, {}
    for (game, mv), rs in by.items():
        p = os.path.join(ROOT, 'work', 'sep', game, mv + '.npy')
        if not os.path.exists(p):
            continue
        voc = np.load(p, mmap_mode='r')
        v = voc[:, movie.dialogue_channels(voc.shape[1])].astype(np.float32).mean(axis=1) / 32768
        on = [(r, float(rep[r['asset']]['onset'])) for r in rs if rep.get(r['asset'], {}).get('onset')]
        on.sort(key=lambda t: t[1])
        for i, (r, t) in enumerate(on):
            end = t + float(r['dur']) + 1.0
            if i + 1 < len(on):
                end = min(end, on[i + 1][1] - 0.05)
            seg = movie.trim(v[int(t * movie.SR):int(end * movie.SR)].astype(np.float64), thresh_db=-35)
            if len(seg) >= movie.SR * 0.6:
                out[r['asset']] = to16(seg, movie.SR)
                group[r['asset']] = (game, mv)
    return out, group


def main():
    os.makedirs(OUT, exist_ok=True)
    fp = Fingerprint()
    refs, group = movie_refs()
    with open(os.path.join(ROOT, 'lines', 'mission.csv'), encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            p = os.path.join(ROOT, 'original', 'mission', r['asset'] + '.wav')
            if r['zh'].strip() and os.path.exists(p) and float(r['seconds'] or 0) >= 0.8:
                refs[r['asset']] = audio_io.load_mono(p, 16000).astype(np.float32)
                group[r['asset']] = ('mission', r['group'])
    info = {}
    for k, (a, y) in enumerate(refs.items()):
        batch = 'movie' if group[a][0] != 'mission' else 'mission'
        q = os.path.join(ROOT, 'voices', batch, a + '.wav')
        if not os.path.exists(q):
            continue
        z = audio_io.load_mono(q, 16000).astype(np.float32)
        info[a] = {'emb': fp(y), 'f0': median_f0(y), 'dub_emb': fp(z), 'dub_f0': median_f0(z)}
        if k % 500 == 0:
            print(f'PROGRESS {k}/{len(refs)}', flush=True)
    by = {}
    for a in info:
        by.setdefault(group[a], []).append(a)
    rows = []
    for g, assets in by.items():
        for a in assets:
            d = info[a]
            own = float(d['dub_emb'] @ d['emb'])
            reasons = []
            ratio = d['dub_f0'] / d['f0'] if d['f0'] > 0 and d['dub_f0'] > 0 else 1.0
            if not F0_LO <= ratio <= F0_HI:
                reasons.append(f'pitch {d["f0"]:.0f}->{d["dub_f0"]:.0f} Hz')
            others = [b for b in assets if b != a and float(info[b]['emb'] @ d['emb']) < 0.45]   # other actors
            best, s_other = None, -1.0
            for b in others:
                s = float(d['dub_emb'] @ info[b]['emb'])
                if s > s_other:
                    best, s_other = b, s
            if best and s_other > own + MARGIN:
                reasons.append(f'closer to {best} ({s_other:.2f} vs own {own:.2f})')
            if reasons:
                rows.append({'asset': a, 'batch': 'mission' if g[0] == 'mission' else 'movie', 'group': g[1],
                             'own_sim': round(own, 3), 'pitch_ratio': round(ratio, 2), 'why': '; '.join(reasons),
                             'both': int(len(reasons) == 2)})
    rows.sort(key=lambda r: (-r['both'], r['own_sim']))
    with open(os.path.join(OUT, 'report.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['asset', 'batch', 'group', 'own_sim', 'pitch_ratio', 'why', 'both'])
        w.writeheader()
        w.writerows(rows)
    print(f'{len(info)} dubs checked; {len(rows)} listed ({sum(r["both"] for r in rows)} with both pitch and fingerprint)')
    for r in rows[:30]:
        print('  ', r['asset'], r['why'])


if __name__ == '__main__':
    main()
