"""A real RefPack (0x10FB) compressor: greedy LZ77 with hash chains, checked by ra3voice.refpack.decompress.

  python -I -X utf8 experimental/campaign/refpack_lz.py selftest     # round trip + ratio on retail campaign maps

ra3voice.refpack.compress_literal only wraps data in literal runs, so maps written by mapscript are as big as the
uncompressed chunk file (a relit pack of the 27 campaign maps: 154 MB). Command forms (as decompress reads them):
  short   2 bytes: length 3..10,   offset 1..1024,   0..3 literals first
  medium  3 bytes: length 4..67,   offset 1..16384
  long    4 bytes: length 5..1028, offset 1..131072
  literal 1 byte + 4..112 bytes (multiple of 4); end 0xFC + 0..3 literals
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from ra3voice import refpack                    # noqa: E402

WINDOW = 131072
MAX_LEN = 1028
CHAIN = 16


def _copy(out, lit, n, off):
    """Append pending literals `lit` (< 4 left after literal runs) and a copy command."""
    k = len(lit)
    o = off - 1
    if n <= 10 and off <= 1024:
        out += bytes([((o >> 3) & 0x60) | ((n - 3) << 2) | k, o & 0xFF])
    elif n <= 67 and off <= 16384:
        out += bytes([0x80 | (n - 4), (k << 6) | (o >> 8), o & 0xFF])
    else:
        out += bytes([0xC0 | ((o >> 16) & 1) << 4 | ((n - 5) >> 8) << 2 | k, (o >> 8) & 0xFF, o & 0xFF, (n - 5) & 0xFF])
    out += lit


def _flush(out, lit):
    """Emit literal runs of multiples of 4 (max 112); return the 0..3 bytes left over."""
    p = 0
    while len(lit) - p >= 4:
        n = min(112, (len(lit) - p) & ~3)
        out.append(0xE0 + (n - 4) // 4)
        out += lit[p:p + n]
        p += n
    return lit[p:]


def compress(d):
    d = bytes(d)
    size = len(d)
    big = size > 0xFFFFFF
    out = bytearray([0x90 if big else 0x10, 0xFB]) + size.to_bytes(4 if big else 3, 'big')
    heads, prev = {}, [0] * size
    lit_start, p = 0, 0
    while p + 3 <= size:
        key = d[p:p + 3]
        best_n, best_off = 0, 0
        q = heads.get(key, -1)
        steps = 0
        limit = min(MAX_LEN, size - p)
        while q >= 0 and p - q <= WINDOW and steps < CHAIN:
            if d[q + best_n:q + best_n + 1] == d[p + best_n:p + best_n + 1]:
                n = 3
                while n < limit and d[q + n] == d[p + n]:
                    n += 1
                off = p - q
                ok = n >= 5 or (n >= 4 and off <= 16384) or (off <= 1024)
                if ok and n > best_n:
                    best_n, best_off = n, off
                    if n == limit:
                        break
            q = prev[q] if q else -1
            steps += 1
        if best_n:
            lit = _flush(out, d[lit_start:p])
            _copy(out, lit, best_n, best_off)
            end = p + best_n
            while p < end:
                if p + 3 <= size:
                    k = d[p:p + 3]
                    prev[p] = heads.get(k, -1)
                    heads[k] = p
                p += 1
            lit_start = p
        else:
            prev[p] = heads.get(key, -1)
            heads[key] = p
            p += 1
    lit = _flush(out, d[lit_start:])
    out.append(0xFC + len(lit))
    out += lit
    return bytes(out)


def selftest():
    import time
    import mapscript
    from ra3voice import big
    arc, maps = mapscript.campaign_maps()
    for n in maps[:3]:
        m = mapscript.MapFile(big.read_files(arc, [n])[n])
        raw = m.chunk_file()
        t = time.time()
        c = compress(raw)
        assert refpack.decompress(c) == raw
        print(f'{n.split(chr(92))[-1]}: {len(raw)} -> {len(c)} ({len(c) / len(raw):.0%}), {time.time() - t:.0f} s')


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    selftest()
