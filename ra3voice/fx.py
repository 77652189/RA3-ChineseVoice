"""Mechanical voice effects. Pitch shifting needs librosa (run under the IndexTTS venv)."""
import numpy as np
from scipy.signal import butter, lfilter, sosfilt


def pitch(x, sr, semitones):
    if not semitones:
        return x
    import librosa
    return librosa.effects.pitch_shift(x.astype(np.float32), sr=sr, n_steps=semitones, res_type='soxr_hq')


def comb(x, sr, delay_ms, feedback, mix):
    """Feedback comb filter: metallic, hollow resonance."""
    d = max(1, int(sr * delay_ms / 1000))
    a = np.zeros(d + 1); a[0] = 1; a[d] = -feedback
    wet = lfilter([1 - feedback], a, x)
    return (1 - mix) * x + mix * wet


def ring(x, sr, carrier_hz, mix):
    """Ring modulation: electronic, inharmonic buzz."""
    t = np.arange(len(x)) / sr
    return (1 - mix) * x + mix * x * np.sin(2 * np.pi * carrier_hz * t) * np.sqrt(2)


def flange(x, sr, base_ms, depth_ms, rate_hz, feedback, mix):
    """Slowly swept short delay: synthetic, 'phasey' machine sheen."""
    n = len(x)
    t = np.arange(n) / sr
    delay = (base_ms + depth_ms * 0.5 * (1 + np.sin(2 * np.pi * rate_hz * t))) * sr / 1000
    y = np.zeros(n)
    for i in range(n):
        j = i - delay[i]
        k = int(j)
        v = 0.0
        if k >= 1:
            fr = j - k
            v = (1 - fr) * y[k] + fr * y[k + 1] if k + 1 < i else y[k]
        y[i] = x[i] + feedback * v
    y *= (1 - feedback)
    return (1 - mix) * x + mix * y


def crush(x, sr, bits, down):
    """Bit depth / sample-and-hold reduction: digital grit."""
    q = 2 ** (bits - 1)
    y = np.round(x * q) / q
    if down > 1:
        y = np.repeat(y[::down], down)[:len(x)]
        sos = butter(6, sr / down * 0.45, fs=sr, output='sos')
        y = sosfilt(sos, y)
    return y


STEPS = {'pitch': pitch, 'comb': comb, 'ring': ring, 'flange': flange, 'crush': crush}


def apply_chain(x, sr, chain):
    """chain: list of [step_name, {params}]"""
    peak_in = float(np.max(np.abs(x))) or 1.0
    for name, params in chain:
        x = STEPS[name](x, sr, **params)
    peak = float(np.max(np.abs(x))) or 1.0
    return x * min(peak_in / peak, 0.98 / peak)
