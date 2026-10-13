"""EA-XAS v1 ADPCM (SNR codec 4) mono decode / encode.

Frame = 76 bytes = 128 samples, split into 4 independent groups of 32 samples.
Group g header (4 bytes at 4*g): two LE int16 words.
  word0: upper 12 bits = sample 0, low nibble = coefficient index
  word1: upper 12 bits = sample 1, low nibble = shift code (shift = 20 - code)
Then 15 rows of 4 bytes; byte (row, g) carries samples 2+2*row (high nibble) and 3+2*row (low nibble).
Nibble layout as in vgmstream's decode_ea_xas_v1; integer prediction as in FFmpeg.
"""
import numpy as np

FRAME_BYTES = 76
FRAME_SAMPLES = 128
C0 = np.array([0, 240, 460, 392], dtype=np.int64)
C1 = np.array([0, 0, -208, -220], dtype=np.int64)


def _s16(v):
    return v - 0x10000 if v & 0x8000 else v


def _clip16(v):
    return np.clip(v, -32768, 32767)


def decode(data, num_samples):
    nframes = len(data) // FRAME_BYTES
    out = np.zeros(nframes * FRAME_SAMPLES, dtype=np.int16)
    for fi in range(nframes):
        fr = data[fi * FRAME_BYTES:(fi + 1) * FRAME_BYTES]
        for g in range(4):
            w0 = _s16(fr[4 * g] | fr[4 * g + 1] << 8)
            w1 = _s16(fr[4 * g + 2] | fr[4 * g + 3] << 8)
            k = w0 & 0xF
            shift = 20 - (w1 & 0xF)
            c0, c1 = int(C0[k]), int(C1[k])
            s = [w0 & ~0xF, w1 & ~0xF]
            for row in range(15):
                b = fr[16 + row * 4 + g]
                for nib in (b >> 4, b & 0xF):
                    lvl = (nib - 16 if nib & 8 else nib) << shift
                    v = (lvl + s[-1] * c0 + s[-2] * c1 + 0x80) >> 8
                    s.append(max(-32768, min(32767, v)))
            base = fi * FRAME_SAMPLES + g * 32
            out[base:base + 32] = s
    return out[:num_samples]


def encode(pcm):
    """pcm: int16 mono array. Returns bytes (whole frames, zero padded)."""
    pcm = np.asarray(pcm, dtype=np.int64)
    nframes = (len(pcm) + FRAME_SAMPLES - 1) // FRAME_SAMPLES
    x = np.zeros(nframes * FRAME_SAMPLES, dtype=np.int64)
    x[:len(pcm)] = pcm
    groups = x.reshape(nframes * 4, 32)          # independent groups
    G = groups.shape[0]

    # candidate (coef index, shift code) pairs
    ks, codes = np.meshgrid(np.arange(4), np.arange(13), indexing='ij')
    ks, codes = ks.ravel(), codes.ravel()
    M = len(ks)
    c0, c1 = C0[ks][None, :], C1[ks][None, :]
    shift = (20 - codes)[None, :]

    def q12(v):  # quantize header sample to upper 12 bits
        return np.clip(((v + 8) >> 4) << 4, -32768, 32752)

    h2 = np.repeat(q12(groups[:, 0])[:, None], M, axis=1)
    h1 = np.repeat(q12(groups[:, 1])[:, None], M, axis=1)
    err = np.zeros((G, M), dtype=np.float64)
    nibs = np.zeros((G, M, 30), dtype=np.int64)
    step = (1 << shift)
    for i in range(30):
        target = groups[:, 2 + i][:, None]
        pred = h1 * c0 + h2 * c1
        n = np.round((target * 256 - pred) / step).astype(np.int64)
        n = np.clip(n, -8, 7)
        v = _clip16((n * step + pred + 0x80) >> 8)
        err += (v - target).astype(np.float64) ** 2
        nibs[:, :, i] = n
        h2, h1 = h1, v
    best = np.argmin(err, axis=1)

    out = bytearray(nframes * FRAME_BYTES)
    s0 = q12(groups[:, 0])
    s1 = q12(groups[:, 1])
    for gi in range(G):
        fi, g = divmod(gi, 4)
        m = best[gi]
        base = fi * FRAME_BYTES
        w0 = (int(s0[gi]) & 0xFFF0) | int(ks[m])
        w1 = (int(s1[gi]) & 0xFFF0) | int(codes[m])
        out[base + 4 * g:base + 4 * g + 4] = bytes((w0 & 0xFF, w0 >> 8, w1 & 0xFF, w1 >> 8))
        nb = nibs[gi, m] & 0xF
        for row in range(15):
            out[base + 16 + row * 4 + g] = (int(nb[2 * row]) << 4) | int(nb[2 * row + 1])
    return bytes(out)
