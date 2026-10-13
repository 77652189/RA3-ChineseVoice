"""WAV in/out and level matching for replacement voices."""
import wave
import numpy as np
from math import gcd
from scipy.io import wavfile
from scipy.signal import resample_poly


def load_mono(path, target_sr):
    """Load PCM16/PCM32/float WAV, mix to mono, resample to target_sr. Returns float32 in [-1, 1]."""
    sr, x = wavfile.read(path)
    if x.dtype == np.int16:
        x = x.astype(np.float32) / 32768
    elif x.dtype == np.int32:
        x = x.astype(np.float32) / 2147483648
    elif x.dtype == np.uint8:
        x = (x.astype(np.float32) - 128) / 128
    else:
        x = x.astype(np.float32)
    if x.ndim == 2:
        x = x.mean(axis=1)
    if sr != target_sr:
        g = gcd(sr, target_sr)
        x = resample_poly(x, target_sr // g, sr // g).astype(np.float32)
    return x


def rms(x):
    x = np.asarray(x, dtype=np.float64)
    return float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0


def match_level(x, ref_int16, ceiling=0.98):
    """Scale float signal x so its RMS matches the original clip, limited by a peak ceiling."""
    target = rms(ref_int16.astype(np.float64) / 32768)
    cur = rms(x)
    if cur > 0 and target > 0:
        x = x * (target / cur)
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak > ceiling:
        x = x * (ceiling / peak)
    return x


def to_int16(x):
    return np.clip(np.round(np.asarray(x) * 32767), -32768, 32767).astype(np.int16)


def save_wav(path, pcm16, sr):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.asarray(pcm16, dtype=np.int16).tobytes())
