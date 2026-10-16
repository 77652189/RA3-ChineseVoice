"""Read RA3 .map files (first step towards our own map / script tooling).

  python -I -X utf8 experimental/campaign/mapfile.py [archive] [map path]   -> chunk tree summary

Layers seen in retail maps: RefPack -> 'EAR\\0' + u32 size + RefPack -> SAGE chunk file:
  'CkMp', u32 name count, names (u8 len + text, u32 id) -- the chunk-name table
  chunks: u32 id, u16 version, u32 data size, data; container chunks hold further chunks.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from ra3voice import big, refpack           # noqa: E402

DATA = r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3\Data'


def unwrap(d):
    """Peel RefPack / EAR layers until the chunk file ('CkMp')."""
    for _ in range(4):
        if d[:4] == b'CkMp':
            return d
        if refpack.is_refpack(d):
            d = refpack.decompress(d)
        elif d[:4] == b'EAR\0':
            d = d[8:]
        else:
            raise ValueError(f'unknown layer {d[:8]!r}')
    raise ValueError('no CkMp found')


def names(d):
    n = struct.unpack_from('<I', d, 4)[0]
    p, out = 8, {}
    for _ in range(n):
        ln = d[p]
        name = d[p + 1:p + 1 + ln].decode('latin-1')
        cid = struct.unpack_from('<I', d, p + 1 + ln)[0]
        out[cid] = name
        p += 1 + ln + 4
    return out, p


def chunks(d, start, end, table, depth=0, out=None, limit=4):
    """Walk [start, end) as a chunk sequence; descend where the payload itself parses as chunks."""
    out = [] if out is None else out
    p = start
    while p + 10 <= end:
        cid, ver, size = struct.unpack_from('<IHI', d, p)
        if cid not in table or p + 10 + size > end:
            return out, False
        out.append((depth, table[cid], ver, size, p + 10))
        if depth < limit:
            sub, ok = chunks(d, p + 10, p + 10 + size, table, depth + 1, [], limit)
            if ok and sub:
                out.extend(sub)
        p += 10 + size
    return out, p == end


def load(archive, path):
    d = big.read_files(os.path.join(DATA, archive), [path])[path]
    return unwrap(d)


def main():
    arc = sys.argv[1] if len(sys.argv) > 1 else 'MapsCampaign.big'
    path = sys.argv[2] if len(sys.argv) > 2 else \
        'data\\maps\\official\\camp_a03_heidelberg_smith\\camp_a03_heidelberg_smith.map'
    d = load(arc, path)
    table, p = names(d)
    print(f'{len(d)} bytes, {len(table)} chunk names')
    tree, ok = chunks(d, p, len(d), table)
    print('top level parses cleanly:', ok)
    from collections import Counter
    top = Counter(name for depth, name, *_ in tree if depth == 0)
    print('top-level chunks:', dict(top))
    for depth, name, ver, size, at in tree:
        if depth <= 1 or 'Script' in name:
            if depth <= 2:
                print('  ' * depth + f'{name} v{ver} {size} bytes')
    print('script-related chunk names:', sorted(n for n in table.values() if 'cript' in n or 'Condition' in n or 'Action' in n))


if __name__ == '__main__':
    main()
