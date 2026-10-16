"""EA SCHl movie audio (EnglishMovieAudio.big *.snd): EA-XA v2 ADPCM, blocked layout.

File = SCHl (header, kept as is) + SCCl (block count) + SCDl blocks + SCEl. Block ids and sizes are
LE; everything inside an SCDl block is BE:
  +0x08 num_samples, +0x0C one offset per channel (relative to the end of the offset table),
  then each channel's frames, each channel area padded to an even size.
Frame: first byte 0xEE = PCM frame (BE int16 hist1, hist2, then 28 BE samples; 61 bytes);
otherwise 15-byte ADPCM frame: byte0 = coef index << 4 | shift code, 14 bytes of nibbles
(high nibble first), 28 samples. Decoding as in vgmstream's decode_ea_xa_v2.

We replace one channel (the dialogue: the centre channel of 6-channel movies, or the downmix of
stereo talking heads) and keep the other channels' bytes untouched. Every rewritten channel area
starts with a PCM frame, so no prediction history crosses a block boundary.
"""
import struct

import numpy as np

FRAME_SAMPLES = 28
ADPCM_BYTES = 15
PCM_BYTES = 61
COEF1 = np.array([0, 240, 460, 392], dtype=np.int64)
COEF2 = np.array([0, 0, -208, -220], dtype=np.int64)


def blocks(data):
    """[(tag, offset, size)] for the whole file."""
    out, i = [], 0
    while i + 8 <= len(data):
        tag, size = data[i:i + 4], struct.unpack_from('<I', data, i + 4)[0]
        out.append((tag, i, size))
        if size == 0 or tag == b'SCEl':
            break
        i += size
    return out


def header_tags(data):
    """PT tags of the SCHl header: {tag: int}. 0x80 version, 0x82 channels, 0x84 sample rate,
    0x85 total samples (BE values)."""
    tag, off, size = blocks(data)[0]
    assert tag == b'SCHl'
    h = data[off + 8:off + size]
    p = h.index(0xFD) + 1
    tags = {}
    while p < len(h) and h[p] != 0xFF:
        t, n = h[p], h[p + 1]
        tags[t] = int.from_bytes(h[p + 2:p + 2 + n], 'big')
        p += 2 + n
    return tags


def channels(data):
    return header_tags(data).get(0x82, 1)


def _split(data, off, size, nch):
    ns = struct.unpack_from('>I', data, off + 8)[0]
    base = off + 0x0C + 4 * nch
    offs = [struct.unpack_from('>I', data, off + 0x0C + 4 * c)[0] for c in range(nch)] + [off + size - base]
    return ns, [data[base + offs[c]:base + offs[c + 1]] for c in range(nch)]


def decode_channel_area(area, num_samples, hist=(0, 0)):
    """-> (int16 samples, (hist1, hist2)); prediction history carries over from the previous block."""
    out = np.zeros(num_samples, dtype=np.int16)
    h1, h2 = hist
    p = n = 0
    while n < num_samples and p < len(area):
        if area[p] == 0xEE:
            h1, h2 = struct.unpack_from('>hh', area, p + 1)
            k = min(FRAME_SAMPLES, num_samples - n)
            out[n:n + k] = struct.unpack_from(f'>{k}h', area, p + 5)
            p += PCM_BYTES
        else:
            info = area[p]
            c1, c2 = int(COEF1[info >> 4]), int(COEF2[info >> 4])
            shift = (info & 0x0F) + 8
            k = min(FRAME_SAMPLES, num_samples - n)
            for i in range(k):
                b = area[p + 1 + i // 2]
                nib = (b >> 4) if i % 2 == 0 else (b & 0x0F)
                s = ((nib << 28) - ((nib & 8) << 29)) >> shift          # sign-extend the nibble
                s = (s + c1 * h1 + c2 * h2) >> 8
                s = max(-32768, min(32767, s))
                out[n + i] = s
                h2, h1 = h1, s
            p += ADPCM_BYTES
        n += FRAME_SAMPLES
    return out, (h1, h2)


def decode(data):
    """Whole file -> int16 array [n, channels] (our own decoder; vgmstream is the reference)."""
    nch = channels(data)
    parts, hist = [], [(0, 0)] * nch
    for tag, off, size in blocks(data):
        if tag == b'SCDl':
            ns, areas = _split(data, off, size, nch)
            cols = []
            for c, a in enumerate(areas):
                y, hist[c] = decode_channel_area(a, ns, hist[c])
                cols.append(y)
            parts.append(np.stack(cols, axis=1))
    return np.concatenate(parts) if parts else np.zeros((0, nch), dtype=np.int16)


def encode_channel_area(pcm):
    """int16 samples of one block -> channel area bytes (PCM frame first, then ADPCM, even size)."""
    pcm = np.asarray(pcm, dtype=np.int64)
    n = len(pcm)
    nf = (n + FRAME_SAMPLES - 1) // FRAME_SAMPLES
    x = np.zeros(nf * FRAME_SAMPLES, dtype=np.int64)
    x[:n] = pcm
    out = bytearray()
    first = x[:FRAME_SAMPLES]
    out += b'\xEE' + struct.pack('>hh', 0, 0) + struct.pack(f'>{FRAME_SAMPLES}h', *first.tolist())
    h1, h2 = int(first[-1]), int(first[-2])
    ks, codes = np.meshgrid(np.arange(4), np.arange(13), indexing='ij')
    ks, codes = ks.ravel(), codes.ravel()
    c1, c2 = COEF1[ks], COEF2[ks]
    step = np.left_shift(1, 20 - codes)          # nibble * step == (nibble << 28) >> (code + 8)
    for f in range(1, nf):
        seg = x[f * FRAME_SAMPLES:(f + 1) * FRAME_SAMPLES]
        a1 = np.full(len(ks), h1, dtype=np.int64)
        a2 = np.full(len(ks), h2, dtype=np.int64)
        err = np.zeros(len(ks))
        nibs = np.zeros((len(ks), FRAME_SAMPLES), dtype=np.int64)
        for i in range(FRAME_SAMPLES):
            pred = c1 * a1 + c2 * a2
            q = np.clip(np.round((seg[i] * 256 - pred) / step), -8, 7).astype(np.int64)
            v = np.clip((q * step + pred) >> 8, -32768, 32767)
            err += (v - seg[i]) ** 2
            nibs[:, i] = q
            a2, a1 = a1, v
        m = int(np.argmin(err))
        q = nibs[m] & 0x0F
        out.append(int(ks[m]) << 4 | int(codes[m]))
        out += bytes((q[0::2] << 4 | q[1::2]).astype(np.uint8).tolist())
        h1, h2 = int(a1[m]), int(a2[m])
    if len(out) % 2:
        out.append(0)
    return bytes(out)


BATCH_ROWS = 2048       # blocks encoded side by side; bounds the (rows x 52 candidates x 28) work arrays


def encode_channel_areas(pieces):
    """encode_channel_area for many blocks at once, byte for byte the same. Every block starts from its own PCM
    frame, so blocks (and channels) are independent and only the frames inside a block run in order: blocks with
    the same frame count are encoded together, each step vectorised over block x predictor x shift."""
    pieces = [np.asarray(p, dtype=np.int64) for p in pieces]
    out = [None] * len(pieces)
    nfs = [(len(p) + FRAME_SAMPLES - 1) // FRAME_SAMPLES for p in pieces]
    ks, codes = np.meshgrid(np.arange(4), np.arange(13), indexing='ij')
    ks, codes = ks.ravel(), codes.ravel()
    c1, c2 = COEF1[ks][None, :], COEF2[ks][None, :]
    step = np.left_shift(1, 20 - codes)[None, :]
    by_nf = {}
    for i, nf in enumerate(nfs):
        by_nf.setdefault(nf, []).append(i)
    for nf, idx in by_nf.items():
        for b0 in range(0, len(idx), BATCH_ROWS):
            rows = idx[b0:b0 + BATCH_ROWS]
            g = len(rows)
            x = np.zeros((g, max(nf, 1) * FRAME_SAMPLES), dtype=np.int64)
            for r, i in enumerate(rows):
                x[r, :len(pieces[i])] = pieces[i]
            heads = [bytearray(b'\xEE' + struct.pack('>hh', 0, 0) + struct.pack(f'>{FRAME_SAMPLES}h', *x[r, :FRAME_SAMPLES].tolist()))
                     for r in range(g)]
            h1 = x[:, FRAME_SAMPLES - 1].copy()
            h2 = x[:, FRAME_SAMPLES - 2].copy()
            frames = []
            for f in range(1, nf):
                seg = x[:, f * FRAME_SAMPLES:(f + 1) * FRAME_SAMPLES]
                a1 = np.repeat(h1[:, None], len(ks), axis=1)
                a2 = np.repeat(h2[:, None], len(ks), axis=1)
                err = np.zeros((g, len(ks)))
                nibs = np.zeros((g, len(ks), FRAME_SAMPLES), dtype=np.int64)
                for i in range(FRAME_SAMPLES):
                    s = seg[:, i:i + 1]
                    pred = c1 * a1 + c2 * a2
                    q = np.clip(np.round((s * 256 - pred) / step), -8, 7).astype(np.int64)
                    v = np.clip((q * step + pred) >> 8, -32768, 32767)
                    err += (v - s) ** 2
                    nibs[:, :, i] = q
                    a2, a1 = a1, v
                m = np.argmin(err, axis=1)
                pick = np.arange(g)
                q = nibs[pick, m] & 0x0F
                head = (ks[m] << 4 | codes[m]).astype(np.uint8)
                body = (q[:, 0::2] << 4 | q[:, 1::2]).astype(np.uint8)
                frames.append(np.concatenate([head[:, None], body], axis=1))
                h1, h2 = a1[pick, m], a2[pick, m]
            tail = np.concatenate(frames, axis=1) if frames else np.zeros((g, 0), dtype=np.uint8)
            for r, i in enumerate(rows):
                b = heads[r] + tail[r].tobytes()
                if len(b) % 2:
                    b.append(0)
                out[i] = bytes(b)
    return out


def replace_channel(data, ch, pcm):
    return replace_channels(data, {ch: pcm})


def replace_channels(data, new):
    """Return a new .snd with the channels in `new` ({channel: int16 array}) replaced (each padded or cut
    to the original length). Other channels keep their bytes. Channels given the same array object
    share one encoding (stereo talking heads carry the same dub on both sides)."""
    nch = channels(data)
    total = sum(struct.unpack_from('>I', data, off + 8)[0] for tag, off, _ in blocks(data) if tag == b'SCDl')
    tracks = {}
    for c, pcm in new.items():
        if id(pcm) not in tracks:
            x = np.zeros(total, dtype=np.int64)
            p = np.asarray(pcm, dtype=np.int64)[:total]
            x[:len(p)] = p
            tracks[id(pcm)] = x
    # every (block, track) area first, encoded in one batch
    jobs, pos = [], 0
    for tag, off, size in blocks(data):
        if tag == b'SCDl':
            ns = struct.unpack_from('>I', data, off + 8)[0]
            jobs += [(pos, ns, key) for key in tracks]
            pos += ns
    encoded = dict(zip(jobs, encode_channel_areas([tracks[k][p:p + n] for p, n, k in jobs])))
    out = bytearray()
    pos = 0
    for tag, off, size in blocks(data):
        if tag != b'SCDl':
            out += data[off:off + size]
            continue
        ns, areas = _split(data, off, size, nch)
        for c, pcm in new.items():
            areas[c] = encoded[(pos, ns, id(pcm))]
        pos += ns
        offs, acc = [], 0
        for a in areas:
            offs.append(acc)
            acc += len(a)
        body = struct.pack('>I', ns) + struct.pack(f'>{nch}I', *offs) + b''.join(areas)
        out += b'SCDl' + struct.pack('<I', 8 + len(body)) + body
    return bytes(out)
