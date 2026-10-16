"""Splice SDK-compiled asset instances into the retail RA3 static streams (a full replacement that -modConfig loads).

  python -I -X utf8 experimental/campaign/splice_assets.py <built mod data dir> <out.big> [type:id ...]

<built mod data dir> is BinaryAssetBuilder output (C:\\RA3ModSDK\\BuiltMods\\mods\\<mod>\\data, holding
mod.{manifest,bin,relo,imp}). Every instance in it that also exists in the retail stream (same type id and
instance id) replaces the retail one -- or only those listed as hex type:id. Instance data, relocation and import
chunks are all taken from the mod build (their offsets belong to the new layout); the retail entry keeps its
referenced-asset list, so a replacement must reference the same number of assets (checked).

Why a full stream: SDK mod.manifest overrides with the same asset id have no effect in game (probe A, 2026-10-14),
while a mod BIG carrying the whole retail data\\static.* with instances spliced in does (HD texture probe B).
The 1.10-1.12 patch streams (static.NN.*) carry no data for these instances, they point back at the base stream.
The LOD streams static_l / static_m carry data only for ~100 instances and point back at static for the
rest; a stream is written only where something was replaced.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from ra3voice import big, refpack                       # noqa: E402

GAME = r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\StaticStream.big'
HEADER = '<BBHIIIIIIIIIII'          # 48 bytes; [5] instance count, [6] total instance bytes, [7] largest instance
ENTRY = '<12I'                      # [0] type id [1] instance id [4] refs offset [5] refs count [8] data [9] relo [10] imp


def parse(m, b, r, i):
    h = list(struct.unpack_from(HEADER, m, 0))
    E = [list(struct.unpack_from(ENTRY, m, 48 + k * 48)) for k in range(h[5])]
    pb = pr = pi = 4
    chunks = []
    for e in E:
        chunks.append([b[pb:pb + e[8]], r[pr:pr + e[9]], i[pi:pi + e[10]]])
        pb, pr, pi = pb + e[8], pr + e[9], pi + e[10]
    assert pb == len(b) and pr == len(r) and pi == len(i), (pb, len(b), pr, len(r), pi, len(i))
    return h, E, chunks


def splice(stem, mod, only):
    names = [f'data\\{stem}.{x}' for x in ('manifest', 'bin', 'relo', 'imp')]
    f = big.read_files(GAME, names)
    m, b, r, i = (refpack.decompress(v) if refpack.is_refpack(v) else v for v in (f[n] for n in names))
    h, E, chunks = parse(m, b, r, i)
    m = bytearray(m)
    done = []
    for k, e in enumerate(E):
        key = (e[0], e[1])
        if key not in mod or (only and key not in only) or not e[8]:
            continue            # e[8] == 0: this stream points back at the base one (LOD and patch streams)
        me, mc = mod[key]
        assert me[5] == e[5], f'{key}: references {me[5]} assets, retail {e[5]} (not supported)'
        chunks[k] = mc
        e[8], e[9], e[10] = (len(x) for x in mc)
        struct.pack_into(ENTRY, m, 48 + k * 48, *e)
        done.append(key)
    h[6] = sum(len(c[0]) for c in chunks)
    h[7] = max(h[7], max(len(c[0]) for c in chunks))
    struct.pack_into(HEADER, m, 0, *h)
    head = (b[:4], r[:4], i[:4])
    return done, [(names[0], bytes(m))] + [(names[n + 1], head[n] + b''.join(c[n] for c in chunks)) for n in range(3)]


def main():
    src, out = sys.argv[1:3]
    only = {tuple(int(x, 16) for x in a.split(':')) for a in sys.argv[3:]}
    mh, mE, mC = parse(*(open(os.path.join(src, f'mod.{x}'), 'rb').read() for x in ('manifest', 'bin', 'relo', 'imp')))
    mod = {(e[0], e[1]): (e, c) for e, c in zip(mE, mC)}
    files = []
    for stem in ('static', 'static_l', 'static_m'):
        done, fs = splice(stem, mod, only)
        print(stem, 'replaced', len(done), [f'{t:08x}:{n:08x}' for t, n in done])
        if done:            # an untouched stream stays the retail one
            files += fs
    big.write(out, files)
    print('->', out, f'{os.path.getsize(out) / 1e6:.0f} MB')


if __name__ == '__main__':
    main()
