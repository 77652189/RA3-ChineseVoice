"""Per-line measurements of a movie dub against the actor's own line (original/movie_clean: the separated vocals
from where the actor starts to the next line's onset), for the automatic judge.

  venv=third_party/index-tts/.venv/Scripts/python.exe
  $venv -I -X utf8 tools/qa_features.py [--assets A B ...] [--voices DIR] [--out work/qa/features.csv]

Columns (dub vs actor):
  dur_ratio     speech length                     (< 1: rushed, > 1: dragged)
  f0_ratio      median pitch, log2                (voice register / gender)
  spread_ratio  pitch spread (10-90 % semitones)  (< 1: flatter than the actor)
  swing_ratio   loudness swing                    (< 1: less dynamic)
  effort_diff   high-band share, dB               (< 0: softer / less shouted than the actor)
  end_slope_*   pitch slope of the last 30 % in semitones/s, for both (question intonation)
  spk_sim       CAMPPlus similarity to the actor's line
"""
import argparse
import csv
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ra3voice import audio_io  # noqa: E402

SR = 16000
HOP = 320  # 20 ms


def trim(y, floor_db=35):
    n = len(y) // HOP
    if n < 2:
        return y
    rms = np.sqrt(np.mean(y[:n * HOP].reshape(n, HOP) ** 2, axis=1)) + 1e-9
    on = np.where(20 * np.log10(rms / rms.max()) > -floor_db)[0]
    return y[on[0] * HOP:(on[-1] + 1) * HOP] if len(on) else y


def f0_db(y):
    """20 ms frames: F0 (0 = unvoiced) by autocorrelation, level in dB."""
    n = 640
    peak = np.abs(y).max() + 1e-9
    f0, db = [], []
    for a in range(0, len(y) - n, HOP):
        fr = y[a:a + n].astype(np.float64)
        lvl = np.sqrt(np.mean(fr ** 2))
        db.append(20 * np.log10(lvl / peak + 1e-9))
        fr = fr - fr.mean()
        if lvl < peak * 0.08:
            f0.append(0.0)
            continue
        ac = np.correlate(fr, fr, 'full')[n - 1:]
        lo, hi = SR // 500, SR // 65
        k = lo + int(np.argmax(ac[lo:hi]))
        f0.append(SR / k if ac[k] > 0.4 * ac[0] else 0.0)
    return np.array(f0), np.array(db)


def measure(y):
    y = trim(y)
    f0, db = f0_db(y)
    v = f0[f0 > 0]
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2 if len(y) > 64 else np.ones(2)
    freqs = np.fft.rfftfreq(len(y), 1 / SR) if len(y) > 64 else np.array([0, 1])
    hi = spec[(freqs > 2000) & (freqs < 6000)].sum() / (spec[(freqs > 80) & (freqs < 6000)].sum() + 1e-12)
    out = {'sec': len(y) / SR, 'effort': 10 * np.log10(hi + 1e-9)}
    if len(v) >= 5:
        st = 12 * np.log2(v / np.median(v))
        out.update(f0=float(np.median(v)), spread=float(np.percentile(st, 90) - np.percentile(st, 10)))
        idx = np.where(f0 > 0)[0]
        tail = idx[idx >= idx[0] + 0.7 * (idx[-1] - idx[0])]
        if len(tail) >= 3:
            t = tail * HOP / SR
            out['end_slope'] = float(np.polyfit(t, 12 * np.log2(f0[tail] / np.median(v)), 1)[0])
    loud = db[db > db.max() - 30]
    out['swing'] = float(np.std(loud)) if len(loud) > 3 else 0.0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--assets', nargs='*')
    ap.add_argument('--voices', default=os.path.join(ROOT, 'voices', 'movie'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'work', 'qa', 'features.csv'))
    a = ap.parse_args()
    rows = [r for r in csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig'))
            if r['zh'].strip() and os.path.exists(os.path.join(a.voices, r['asset'] + '.wav'))]
    if a.assets:
        rows = [r for r in rows if r['asset'] in set(a.assets)]
    import torch
    from ra3voice import throttle
    throttle.setup(torch)
    from speakers import Fingerprint
    fp = Fingerprint()
    res = []
    for i, r in enumerate(rows):
        ref = os.path.join(ROOT, 'original', 'movie_clean', r['asset'] + '.wav')
        if not os.path.exists(ref):
            continue
        x = audio_io.load_mono(os.path.join(a.voices, r['asset'] + '.wav'), SR).astype(np.float32)
        o = audio_io.load_mono(ref, SR).astype(np.float32)
        mx, mo = measure(x), measure(o)
        with throttle.work():
            sim = float(fp(trim(x)) @ fp(trim(o)))
        row = {'asset': r['asset'], 'zh': r['zh'], 'chars': len(r['zh']), 'question': int(r['zh'].rstrip().endswith(('？', '?'))),
               'actor_s': round(mo['sec'], 2), 'dub_s': round(mx['sec'], 2), 'dur_ratio': round(mx['sec'] / max(mo['sec'], 0.2), 3),
               'f0_ratio': round(float(np.log2(mx['f0'] / mo['f0'])), 3) if 'f0' in mx and 'f0' in mo else '',
               'spread_ratio': round(mx['spread'] / max(mo['spread'], 1.0), 3) if 'spread' in mx and 'spread' in mo else '',
               'swing_ratio': round(mx['swing'] / max(mo['swing'], 1.0), 3),
               'effort_diff': round(mx['effort'] - mo['effort'], 2),
               'end_slope_dub': round(mx.get('end_slope', 0.0), 2), 'end_slope_actor': round(mo.get('end_slope', 0.0), 2),
               'spk_sim': round(sim, 3)}
        res.append(row)
        if i % 200 == 0:
            print(i, len(rows), flush=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(res[0]))
        w.writeheader()
        w.writerows(res)
    print('->', a.out, len(res))


if __name__ == '__main__':
    main()
