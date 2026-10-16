"""Read / write RA3's map cache (MapMetaData:TheMapCache in data\\mapmetadata.*) and add maps to it.

The game finds every map through this cache; a map folder that is not in it crashes when the mission loads.
Effective stream: data\\mapmetadata.manifest from Maps12.big with .bin / .relo / .imp from Maps11.big (one asset,
links nothing). Instance layout (all pointers are offsets from the instance start, listed in the relocation chunk):
  u32 0, u32 count, u32 -> entries
  entry, 60 bytes: u32 id hash, u32 len + ptr Description, u32 len + ptr DisplayName, u32 NumPlayers, u32 CRC,
    u32 len + ptr FileName, u32 Width, u32 Height, u32 BorderSize, u32 n + ptr StartPositions, u32 flags
    (byte 0 IsMultiplayer, byte 1 IsOfficial)
  start position, 20 bytes: u32 len + ptr Name, f32 x, y, z
  after the entries, per entry: Description, DisplayName, FileName (NUL-terminated, 4-aligned), its start
  positions, then their names. Relocations: the entries pointer, every entry's 4 pointers, then the start names.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from ra3voice import big, refpack                 # noqa: E402

DATA = r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3\Data'
STREAM = [('data\\mapmetadata.manifest', 'Maps12.big'), ('data\\mapmetadata.bin', 'Maps11.big'),
          ('data\\mapmetadata.relo', 'Maps11.big'), ('data\\mapmetadata.imp', 'Maps11.big')]


def _cstr(d, o):
    return d[o:d.index(b'\0', o)].decode('latin-1')


def decode(d):
    _, count, arr = struct.unpack_from('<III', d, 0)
    maps = []
    for k in range(count):
        w = struct.unpack_from('<15I', d, arr + 60 * k)
        starts = []
        for j in range(w[12]):
            n, p, x, y, z = struct.unpack_from('<IIfff', d, w[13] + 20 * j)
            starts.append((_cstr(d, p), x, y, z))
        maps.append(dict(id=w[0], description=_cstr(d, w[2]), display=_cstr(d, w[4]), players=w[5], crc=w[6],
                         file=_cstr(d, w[8]), width=w[9], height=w[10], border=w[11], starts=starts, flags=w[14]))
    return maps


def encode(maps):
    """-> (instance data, relocation chunk)"""
    n = len(maps)
    body = bytearray(12 + 60 * n)
    struct.pack_into('<III', body, 0, 0, n, 12)
    entry_ptrs, name_ptrs = [8], []

    def put(b):
        while len(body) % 4:
            body.append(0)
        at = len(body)
        body.extend(b)
        return at

    for k, m in enumerate(maps):
        e = 12 + 60 * k
        desc = put(m['description'].encode('latin-1') + b'\0')
        disp = put(m['display'].encode('latin-1') + b'\0')
        fn = put(m['file'].encode('latin-1') + b'\0')
        st = put(bytes(20 * len(m['starts'])))
        for j, (name, x, y, z) in enumerate(m['starts']):
            p = put(name.encode('latin-1') + b'\0')
            struct.pack_into('<IIfff', body, st + 20 * j, len(name), p, x, y, z)
            name_ptrs.append(st + 20 * j + 4)
        struct.pack_into('<15I', body, e, m['id'], len(m['description']), desc, len(m['display']), disp, m['players'],
                         m['crc'], len(m['file']), fn, m['width'], m['height'], m['border'], len(m['starts']), st, m['flags'])
        entry_ptrs += [e + 8, e + 16, e + 32, e + 52]
    while len(body) % 4:
        body.append(0)
    relo = b''.join(struct.pack('<I', p) for p in entry_ptrs + name_ptrs) + b'\xff\xff\xff\xff'
    return bytes(body), relo


def retail():
    """[(path, raw bytes)] of the effective retail map cache stream."""
    out = []
    for path, arc in STREAM:
        v = big.read_files(os.path.join(DATA, arc), [path])[path]
        out.append((path, refpack.decompress(v) if refpack.is_refpack(v) else v))
    return out


def with_maps(extra):
    """The retail stream with `extra` map dicts appended to TheMapCache -> [(path, bytes)] for a mod BIG."""
    (mp, man), (bp, binf), (rp, relof), (ip, impf) = retail()
    h = list(struct.unpack_from('<BBHIIIIIIIIIII', man, 0))
    e = list(struct.unpack_from('<12I', man, 48))
    assert h[5] == 1 and e[8] == len(binf) - 4, 'expected a one-asset map cache stream'
    maps = decode(binf[4:]) + list(extra)
    data, relo = encode(maps)
    e[8], e[9] = len(data), len(relo)
    h[6] = h[7] = len(data)
    h[8] = max(h[8], len(relo))
    man = bytearray(man)
    struct.pack_into('<BBHIIIIIIIIIII', man, 0, *h)
    struct.pack_into('<12I', man, 48, *e)
    return [(mp, bytes(man)), (bp, binf[:4] + data), (rp, relof[:4] + relo), (ip, impf)]


def selftest():
    (_, man), (_, binf), (_, relof), _ = retail()
    maps = decode(binf[4:])
    data, relo = encode(maps)
    print(f'{len(maps)} maps; re-encoded instance identical: {data == binf[4:]}, relocations identical: {relo == relof[4:]}')
    return data == binf[4:] and relo == relof[4:]


if __name__ == '__main__':
    sys.exit(0 if selftest() else 1)
