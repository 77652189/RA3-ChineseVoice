"""Dialogue removal for movie audio with Demucs (htdemucs): the English voices are mixed into every
channel of the 5.1 movies (not only the centre), so each speaker pair is split into vocals / rest.

vocals(x, sr) -> int16 vocals of a [n, 2] (or [n]) int16 signal; the rest is x - vocals.
"""
from functools import lru_cache

import numpy as np
from scipy.signal import resample_poly

MODEL = 'htdemucs'


@lru_cache(maxsize=1)
def _model():
    import torch
    from demucs.pretrained import get_model
    from . import throttle
    throttle.setup(torch)
    m = get_model(MODEL)
    m.eval()
    return m.cuda() if torch.cuda.is_available() else m


def vocals(x, sr):
    import torch
    from demucs.apply import apply_model
    from . import throttle
    m = _model()
    mono = x.ndim == 1
    st = np.stack([x, x], axis=1) if mono else x
    y = st.astype(np.float32).T / 32768                                   # [2, n]
    msr = m.samplerate
    if sr != msr:
        g = np.gcd(sr, msr)
        y = resample_poly(y, msr // g, sr // g, axis=1).astype(np.float32)
    with throttle.work(), torch.no_grad():
        out = apply_model(m, torch.from_numpy(y)[None].to(next(m.parameters()).device),
                          split=True, overlap=0.25, progress=False)[0]
    v = out[m.sources.index('vocals')].cpu().numpy()                      # [2, n']
    if sr != msr:
        v = resample_poly(v, sr // g, msr // g, axis=1)
    v = v[:, :len(x)]
    if v.shape[1] < len(x):
        v = np.pad(v, ((0, 0), (0, len(x) - v.shape[1])))
    v = np.round(np.clip(v.T * 32768, -32768, 32767)).astype(np.int16)
    return v.mean(axis=1).astype(np.int16) if mono else v
