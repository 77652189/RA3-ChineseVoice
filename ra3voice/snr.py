"""EA SNR+SNS audio container as used in RA3 AudioFile cdata (codec 4 = EA-XAS v1).

Multi-channel payloads interleave whole 76-byte frames: [frame0 ch0][frame0 ch1][frame1 ch0]...
"""
import struct
import numpy as np
from . import refpack, xas

CODEC_XAS1 = 4


def parse(data):
    """Return dict(codec, channels, sample_rate, num_samples, payload) for a cdata blob."""
    if refpack.is_refpack(data):
        data = refpack.decompress(data)
    h0, h1 = struct.unpack('>II', data[:8])
    info = dict(version=h0 >> 28, codec=(h0 >> 24) & 0xF, channels=((h0 >> 18) & 0x3F) + 1,
                sample_rate=h0 & 0x3FFFF, flags=h1 >> 30, num_samples=h1 & 0x3FFFFFFF)
    payload, p = bytearray(), 8
    while p < len(data):
        bh, _ = struct.unpack('>II', data[p:p + 8])
        size = bh & 0xFFFFFF
        payload += data[p + 8:p + size]
        p += size
        if bh >> 24 == 0x80:
            break
    info['payload'] = bytes(payload)
    return info


def decode(data):
    """cdata blob -> (int16 mono numpy array, sample_rate). Multi-channel clips are downmixed."""
    info = parse(data)
    if info['codec'] != CODEC_XAS1:
        raise ValueError(f"unsupported codec={info['codec']} channels={info['channels']}")
    ch, n, pay = info['channels'], info['num_samples'], info['payload']
    if ch == 1:
        return xas.decode(pay, n), info['sample_rate']
    fb = xas.FRAME_BYTES
    nf = len(pay) // (fb * ch)
    chans = [xas.decode(b''.join(pay[(f * ch + c) * fb:(f * ch + c + 1) * fb] for f in range(nf)), n)
             for c in range(ch)]
    mix = np.mean(np.stack(chans).astype(np.float64), axis=0)
    return np.round(mix).astype(np.int16), info['sample_rate']


def build(pcm, sample_rate=48000, channels=1, block_samples=None):
    """int16 mono numpy array -> cdata blob (single SNS block, same layout as the game's unit voices).
    For channels > 1 the same mono signal is written to every channel (the EVA clips are dual mono).
    block_samples (a multiple of 128) splits the data into many SNS blocks, the last one flagged 0x80,
    the way streamed mission dialogue is laid out."""
    n = len(pcm)
    fb = xas.FRAME_BYTES
    body = xas.encode(pcm)
    if channels > 1:
        body = b''.join(body[i:i + fb] * channels for i in range(0, len(body), fb))
    h = struct.pack('>II', (CODEC_XAS1 << 24) | ((channels - 1) << 18) | sample_rate, n)
    if not block_samples:
        return h + struct.pack('>II', 8 + len(body), n) + body
    assert block_samples % xas.FRAME_SAMPLES == 0
    step = block_samples // xas.FRAME_SAMPLES * fb * channels
    out = [h]
    for start in range(0, len(body), step):
        chunk = body[start:start + step]
        last = start + step >= len(body)
        ns = n - start // step * block_samples if last else block_samples
        out.append(struct.pack('>II', (0x80 << 24 if last else 0) | (8 + len(chunk)), ns) + chunk)
    return b''.join(out)
