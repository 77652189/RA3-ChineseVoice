"""Bring the recorded gameplay's movie audio up to the current build without recording again.

  python -I -X utf8 docs/article/patch_gameplay_audio.py OLD_MOVIE_BIG NEW_MOVIE_BIG [movie ...]

The recording (tools/make_demo.GAMEPLAY) holds the game's mix of the old CNVoice_movie.big. For each P2 cut and
each movie that changed between the two packs: find where the movie sits in the cut (cross-correlation), fit how the
game mixed its channels into the recording's stereo (least squares on the old track), and add that mix of
(new - old). Only what changed is touched; the battle sounds stay. Writes work/demo/p2_XX.wav for make_demo.
"""
import os
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import make_demo as md                                      # noqa: E402
from ra3voice import big, movie                             # noqa: E402

SR = movie.SR


def rec_audio(start, length):
    r = subprocess.run([md.FF, '-v', 'error', '-ss', str(start), '-t', str(length), '-i', md.GAMEPLAY, '-ac', '2',
                        '-ar', str(SR), '-f', 's16le', '-'], capture_output=True, check=True)
    return np.frombuffer(r.stdout, '<i2').reshape(-1, 2).astype(np.float64)


def track(pack, name):
    entry = 'data\\movies\\' + name + '.snd'
    return movie.decode(big.read_files(pack, [entry])[entry]).astype(np.float64)


def locate(rec, old):
    """Offset (samples) of movie time 0 in the cut, and the normalised correlation there."""
    a, b = rec.mean(1), old.mean(1)
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    c = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    lags = np.r_[np.arange(0, len(a)), np.arange(-len(b) + 1, 0)]
    vals = np.r_[c[:len(a)], c[n - len(b) + 1:]]
    k = int(np.argmax(np.abs(vals)))
    lag = int(lags[k])
    i0, i1 = max(0, lag), min(len(a), lag + len(b))
    if i1 - i0 < SR // 2:
        return lag, 0.0
    x, y = a[i0:i1], b[i0 - lag:i1 - lag]
    return lag, float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9))


def main():
    old_pack, new_pack = sys.argv[1], sys.argv[2]
    names = sys.argv[3:]
    for i, (start, length) in enumerate(md.PLAY_CUTS):
        rec = rec_audio(start, length)
        out = rec.copy()
        for name in names:
            old, new = track(old_pack, name), track(new_pack, name)
            d = new - old
            if not np.any(d):
                continue
            lag, corr = locate(rec, old)
            if corr < 0.5:
                continue
            i0, i1 = max(0, lag), min(len(rec), lag + len(old))
            seg_old, seg_d = old[i0 - lag:i1 - lag], d[i0 - lag:i1 - lag]
            if not np.any(seg_d):
                continue
            fixed = []
            for ch in range(2):
                coef, *_ = np.linalg.lstsq(seg_old, rec[i0:i1, ch], rcond=None)
                out[i0:i1, ch] += seg_d @ coef
                before = rec[i0:i1, ch] - seg_old @ coef
                fixed.append(f'{20 * np.log10(np.linalg.norm(before) / (np.linalg.norm(rec[i0:i1, ch]) + 1e-9)):.1f}')
            print(f'p2_{i:02d}: {name} at {lag / SR:+.2f}s corr {corr:.2f}, '
                  f'{np.abs(seg_d).max() / 32768:.3f} peak change, fit residual {"/".join(fixed)} dB')
        path = os.path.join(md.OUT, f'p2_{i:02d}.wav')
        y = np.round(np.clip(out, -32768, 32767)).astype('<i2')
        import wave
        with wave.open(path, 'wb') as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(y.tobytes())


if __name__ == '__main__':
    main()
