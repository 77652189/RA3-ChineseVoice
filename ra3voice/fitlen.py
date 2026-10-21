"""Make a dubbed line exactly as long as the original clip.

RA3 campaign scripts wait for some lines to finish (map condition HAS_FINISHED_AUDIO) before the mission moves on.
Each player's game reads that length from its own audio.bin, so in online co-op a player with the dub and one
without (or with another patch) reach the next script step on different frames and the game desyncs. Lines on
that list (sync_lock.json) keep the original length: shorter ones get silence at the end, longer ones lose their
quiet head and tail first and are then sped up (pitch kept)."""
import numpy as np

from . import stretch

TRIM_DB = -45        # quieter than this (relative to the line's peak) counts as silence at the head / tail
MARGIN_S = 0.03      # keep this much of it before and after the speech


def trim(x, sr):
    """x without its quiet head and tail (MARGIN_S kept on each side)."""
    if not len(x):
        return x
    hop = max(1, sr // 100)
    frames = np.abs(x[:len(x) // hop * hop]).reshape(-1, hop).max(axis=1) if len(x) >= hop else np.abs(x)
    peak = float(frames.max()) if len(frames) else 0.0
    if peak <= 0:
        return x[:0]
    loud = np.flatnonzero(frames >= peak * 10 ** (TRIM_DB / 20))
    m = int(MARGIN_S * sr)
    return x[max(0, loud[0] * hop - m):min(len(x), (loud[-1] + 1) * hop + m)]


def fit(x, n, sr):
    """float signal x -> exactly n samples. Returns (y, rate): rate > 1 when it had to be sped up."""
    x = np.asarray(x, dtype=np.float64)
    rate = 1.0
    if len(x) > n:
        x = trim(x, sr)
    if len(x) > n:
        rate = len(x) / n
        x = stretch.wsola(x, rate, sr)
    y = np.zeros(n)
    y[:min(n, len(x))] = x[:n]
    return y, rate
