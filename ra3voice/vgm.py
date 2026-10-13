"""Reference decoding through vgmstream (third_party/vgmstream) for codecs we do not decode ourselves:
EALayer3 mission dialogue (SNR header + SNS blocks) and EA SCHl movie audio."""
import os
import subprocess
import tempfile

import numpy as np
from scipy.io import wavfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, 'third_party', 'vgmstream', 'vgmstream-cli.exe')


def decode_file(path):
    """Any file vgmstream understands -> (int16 array [n] or [n, ch], sample_rate)."""
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'out.wav')
        r = subprocess.run([CLI, '-o', out, path], capture_output=True, text=True)
        if r.returncode or not os.path.exists(out):
            raise ValueError(f'vgmstream failed on {path}: {r.stdout[-300:]} {r.stderr[-300:]}')
        sr, x = wavfile.read(out)
    return x, sr


def decode_snr_sns(header, sns):
    """8-byte SNR header + SNS block data (not RefPack) -> (int16 array, sample_rate)."""
    with tempfile.TemporaryDirectory() as d:
        base = os.path.join(d, 'clip')
        with open(base + '.snr', 'wb') as f:
            f.write(header)
        with open(base + '.sns', 'wb') as f:
            f.write(sns)
        return decode_file(base + '.snr')


def to_mono(x):
    if x.ndim == 1:
        return x
    return np.round(x.astype(np.float64).mean(axis=1)).astype(np.int16)
