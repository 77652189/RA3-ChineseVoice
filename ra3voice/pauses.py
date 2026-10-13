"""Mid-sentence pause detection for dubbed lines.

A gap is a run of 10 ms frames at least MIN_GAP long whose RMS stays below REL_DB relative to the
loudest frame, between the first and last voiced frame. Each punctuation mark inside the sentence
(not the trailing one) allows one gap; any gap beyond that is an "extra" pause — the kind that makes
关键建筑损失 sound like 关键，建筑损失.
Long lines (mission narration, movies) breathe: the minimum gap grows with the line's length, from
MIN_GAP for short barks up to MAX_GAP for lines of LONG_LINE seconds and more.
"""
import re

import numpy as np

MIN_GAP = 0.12
MAX_GAP = 0.30
SHORT_LINE, LONG_LINE = 1.5, 6.0
REL_DB = -32
INNER_PUNCT = re.compile(r'[，、；：,;:…—。！？!?.]')
TRAILING = '。！？!?.…～~ '


def gaps(x, sr, min_gap=MIN_GAP, rel_db=REL_DB):
    """[(start_s, length_s)] of internal silences."""
    hop = int(0.01 * sr)
    n = len(x) // hop
    if n < 3:
        return []
    e = np.sqrt(np.mean(np.asarray(x[:n * hop], dtype=np.float64).reshape(n, hop) ** 2, axis=1))
    on = e > e.max() * 10 ** (rel_db / 20)
    idx = np.where(on)[0]
    if len(idx) < 2:
        return []
    out, start = [], None
    for i in range(idx[0], idx[-1] + 1):
        if not on[i]:
            if start is None:
                start = i
        elif start is not None:
            if (i - start) * 0.01 >= min_gap:
                out.append((start * 0.01, (i - start) * 0.01))
            start = None
    return out


def allowed(text):
    """How many pauses the punctuation inside the sentence allows."""
    return len(INNER_PUNCT.findall(text.strip().rstrip(TRAILING)))


def min_gap_for(seconds):
    t = min(max((seconds - SHORT_LINE) / (LONG_LINE - SHORT_LINE), 0.0), 1.0)
    return MIN_GAP + t * (MAX_GAP - MIN_GAP)


def extra(x, sr, text):
    """(number of unexplained pauses, longest gap in seconds)."""
    g = gaps(x, sr, min_gap=min_gap_for(len(x) / sr))
    return max(0, len(g) - allowed(text)), max((b for _, b in g), default=0.0)
