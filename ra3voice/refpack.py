"""EA RefPack (0x10FB) decompressor."""
import sys


def is_refpack(d):
    return len(d) >= 5 and (d[0] & 0x3E) == 0x10 and d[1] == 0xFB


def decompress(d):
    flags = d[0]
    p = 2
    nb = 4 if flags & 0x80 else 3
    size = int.from_bytes(d[p:p + nb], 'big'); p += nb
    if flags & 0x01:  # compressed-size field present
        p += nb
    out = bytearray()
    while p < len(d):
        b0 = d[p]
        if b0 < 0x80:
            b1 = d[p + 1]; p += 2
            lit = b0 & 3
            n = ((b0 & 0x1C) >> 2) + 3
            off = ((b0 & 0x60) << 3) + b1 + 1
        elif b0 < 0xC0:
            b1, b2 = d[p + 1], d[p + 2]; p += 3
            lit = b1 >> 6
            n = (b0 & 0x3F) + 4
            off = ((b1 & 0x3F) << 8) + b2 + 1
        elif b0 < 0xE0:
            b1, b2, b3 = d[p + 1], d[p + 2], d[p + 3]; p += 4
            lit = b0 & 3
            n = ((b0 & 0x0C) << 6) + b3 + 5
            off = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
        elif b0 < 0xFC:
            p += 1
            lit = ((b0 & 0x1F) << 2) + 4
            out += d[p:p + lit]; p += lit
            continue
        else:
            p += 1
            lit = b0 & 3
            out += d[p:p + lit]
            break
        out += d[p:p + lit]; p += lit
        start = len(out) - off
        for i in range(n):
            out.append(out[start + i])
    if len(out) != size:
        raise ValueError(f'size mismatch {len(out)} != {size}')
    return bytes(out)


def compress_literal(d):
    """Wrap data in a valid RefPack stream using literal runs only (no real compression)."""
    big = len(d) > 0xFFFFFF
    out = bytearray([0x90 if big else 0x10, 0xFB])
    out += len(d).to_bytes(4 if big else 3, 'big')
    p = 0
    while len(d) - p > 3:
        n = min(112, (len(d) - p) & ~3)
        out.append(0xE0 + (n - 4) // 4)
        out += d[p:p + n]
        p += n
    rest = len(d) - p
    out.append(0xFC + rest)
    out += d[p:]
    return bytes(out)


if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    open(sys.argv[2], 'wb').write(decompress(d) if is_refpack(d) else d)
