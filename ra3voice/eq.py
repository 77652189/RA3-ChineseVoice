"""Matching EQ: make new clips share the long-term spectrum of the originals."""
import numpy as np
from scipy.signal import firwin2, fftconvolve, welch

NPERSEG = 2048
MAX_DB = 12.0


def ltas(clips, sr):
    """Long-term average power spectrum over a list of float arrays."""
    acc, n = None, 0
    for x in clips:
        if len(x) < NPERSEG:
            continue
        f, p = welch(x, sr, nperseg=NPERSEG)
        acc = p * len(x) if acc is None else acc + p * len(x)
        n += len(x)
    return f, acc / n


def _smooth_octave(f, db, frac=3):
    out = np.empty_like(db)
    for i, fc in enumerate(f):
        if fc <= 0:
            out[i] = db[i]
            continue
        lo, hi = fc * 2 ** (-0.5 / frac), fc * 2 ** (0.5 / frac)
        out[i] = db[(f >= lo) & (f <= hi)].mean()
    return out


def design(orig_clips, new_clips, sr, numtaps=1023):
    f, po = ltas(orig_clips, sr)
    _, pn = ltas(new_clips, sr)
    db = 10 * np.log10((po + 1e-12) / (pn + 1e-12))
    db = _smooth_octave(f, db)
    db -= np.median(db[(f > 300) & (f < 3000)])  # keep overall level; match_level handles loudness
    db = np.clip(db, -MAX_DB, MAX_DB)
    gain = 10 ** (db / 20)
    return firwin2(numtaps, f / (sr / 2), gain)


def apply(x, taps):
    y = fftconvolve(x, taps, mode='full')
    d = (len(taps) - 1) // 2
    return y[d:d + len(x)]
