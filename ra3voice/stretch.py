"""Pitch-preserving time stretch for speech (WSOLA), used to fit movie lines into their time slot."""
import numpy as np


def wsola(x, rate, sr, frame_ms=30, search_ms=10):
    """Speed speech up by `rate` (> 1 = shorter) keeping the pitch. x: float array."""
    if abs(rate - 1) < 1e-3 or len(x) < sr // 10:
        return x.astype(np.float64)
    n = int(sr * frame_ms / 1000)
    hop_out = n // 2
    hop_in = hop_out * rate
    tol = int(sr * search_ms / 1000)
    win = np.hanning(n)
    out_len = int(len(x) / rate) + n
    y = np.zeros(out_len)
    norm = np.zeros(out_len)
    xp = np.concatenate([np.zeros(tol), x.astype(np.float64), np.zeros(n + tol + int(hop_in) + 1)])
    prev = None
    k = 0
    while True:
        pos_out = k * hop_out
        centre = int(round(k * hop_in)) + tol
        if centre - tol >= len(x) or pos_out + n > out_len:
            break
        if prev is None:
            best = centre
        else:
            # pick the input frame that best continues the previous one (max cross-correlation)
            target = prev
            lo, hi = centre - tol, centre + tol
            seg = xp[lo:hi + n]
            corr = np.correlate(seg, target, mode='valid')
            best = lo + int(np.argmax(corr))
        frame = xp[best:best + n]
        y[pos_out:pos_out + n] += frame * win
        norm[pos_out:pos_out + n] += win
        prev = xp[best + hop_out:best + hop_out + n]
        k += 1
    norm[norm < 1e-6] = 1
    y = y / norm
    return y[:int(len(x) / rate)]
