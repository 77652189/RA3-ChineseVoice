"""Splice SDK-compiled asset instances into the retail RA3 static streams (a full replacement that -modConfig loads).

  python -I -X utf8 experimental/campaign/splice_assets.py <built mod data dir> <out.big> [type:id ...]

<built mod data dir> is BinaryAssetBuilder output (C:\\RA3ModSDK\\BuiltMods\\mods\\<mod>\\data, holding
mod.{manifest,bin,relo,imp}). Every instance in it that also exists in the retail stream (same type id and
instance id) replaces the retail one -- or only those listed as hex type:id. Instances the retail streams do not
have are added to the top patch stream static.12 (the one the game opens; it links static.11 -> ... -> static and
an asset missing from its table does not exist: added to the base stream only, the game stops while loading),
right before the first instance that references them (the manifest is in dependency order, not sorted). Instance data, relocation and import chunks come from the mod build; a changed
list of referenced assets is appended to the reference buffer; new names go to the name buffer.

Manifest layout (as OpenSAGE reads it): 48-byte header (IsBigEndian, IsLinked, Version, StreamChecksum,
AllTypesHash, AssetCount, TotalInstanceDataSize, MaxInstanceChunkSize, MaxRelocationChunkSize,
MaxImportsChunkSize, AssetReferenceBufferSize, ReferencedManifestNameBufferSize, AssetNameBufferSize,
SourceFileNameBufferSize), AssetCount 48-byte entries (TypeId, InstanceId, TypeHash, InstanceHash,
AssetReferenceOffset, AssetReferenceCount, NameOffset, SourceFileNameOffset, InstanceDataSize,
RelocationDataSize, ImportsDataSize, -), then the four buffers in that order. References are (TypeId, InstanceId).

Why a full stream: SDK mod.manifest overrides with the same asset id have no effect in game (probe A, 2026-10-14),
while a mod BIG carrying the whole retail data\\static.* with instances spliced in does (HD texture probe B;
CampSplice1 put the Cannes map on Allied mission 1, 2026-10-15). The 1.10-1.12 patch streams (static.NN.*) and
the LOD streams static_l / static_m carry no data for these instances, they point back at the base stream; a
stream is written only where something changed.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from ra3voice import big, refpack                       # noqa: E402

DATA = r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3\Data'
GAME = DATA + r'\StaticStream.big'
# the streams the game opens (one per LOD setting): static.12 links static.11 -> ... -> static, likewise
# static_l.12 / static_m.12; an asset must be in the opened stream's table to exist
TOPS = [(s, DATA + r'\Core12.big') for s in ('static.12', 'static_l.12', 'static_m.12')]
HEADER = '<BBHIIIIIIIIIII'
ENTRY = '<12I'


def parse(m, b, r, i):
    """-> header, entries, [data, relo, imp] per entry, (refs, manifest names, names, source names) buffers."""
    h = list(struct.unpack_from(HEADER, m, 0))
    E = [list(struct.unpack_from(ENTRY, m, 48 + k * 48)) for k in range(h[5])]
    pb = pr = pi = 4
    chunks = []
    for e in E:
        chunks.append([b[pb:pb + e[8]], r[pr:pr + e[9]], i[pi:pi + e[10]]])
        pb, pr, pi = pb + e[8], pr + e[9], pi + e[10]
    assert pb == len(b) and pr == len(r) and pi == len(i), (pb, len(b), pr, len(r), pi, len(i))
    o = 48 + 48 * h[5]
    bufs = []
    for size in h[10:14]:
        bufs.append(bytes(m[o:o + size]))
        o += size
    assert o == len(m), (o, len(m))
    return h, E, chunks, bufs


def refs(bufs, e):
    return [struct.unpack_from('<II', bufs[0], e[4] + 8 * n) for n in range(e[5])]


def cstr(buf, off):
    return buf[off:buf.index(b'\0', off)]


def splice(stem, mod, only, archive=GAME, add_new=False):
    names = [f'data\\{stem}.{x}' for x in ('manifest', 'bin', 'relo', 'imp')]
    f = big.read_files(archive, names)
    m, b, r, i = (refpack.decompress(v) if refpack.is_refpack(v) else v for v in (f[n] for n in names))
    h, E, chunks, bufs = parse(m, b, r, i)
    refbuf, namebuf = bytearray(bufs[0]), bytearray(bufs[2])

    def set_refs(e, lst):
        if refs(bufs, e) != lst or e[4] + 8 * len(lst) > len(bufs[0]):
            e[4] = len(refbuf)
            refbuf.extend(b''.join(struct.pack('<II', *x) for x in lst))
        e[5] = len(lst)

    have = {(e[0], e[1]): k for k, e in enumerate(E)}
    done = []
    for k, e in enumerate(E):
        key = (e[0], e[1])
        if key not in mod or (only and key not in only):
            continue
        if not e[8]:            # this stream points back at the base one for the data (LOD and patch streams) ...
            if add_new and refs([refbuf], e) != mod[key][2]:
                set_refs(e, mod[key][2])    # ... but its own table still says what the asset references
                done.append(key)
            continue
        me, mc, mrefs, _ = mod[key]
        chunks[k] = mc
        e[8], e[9], e[10] = (len(x) for x in mc)
        set_refs(e, mrefs)
        done.append(key)
    added = []
    if add_new:                 # new instances go to the top patch stream, with their own data
        new = [key for key in mod if key not in have and (not only or key in only)]
        for key in new:
            me, mc, mrefs, mname = mod[key]
            users = [k for k, e in enumerate(E) if key in refs([refbuf], e)]     # refs as they are now (replacements included)
            at = min(users) if users else len(E)
            e = list(me)
            e[4] = len(refbuf)
            refbuf.extend(b''.join(struct.pack('<II', *x) for x in mrefs))
            e[5] = len(mrefs)
            e[6] = len(namebuf)
            namebuf.extend(mname + b'\0')
            e[7] = E[at][7] if at < len(E) else E[-1][7]       # the source file of the asset that uses it
            e[8], e[9], e[10] = (len(x) for x in mc)
            E.insert(at, e)
            chunks.insert(at, mc)
            added.append(key)
    if not done and not added:
        return done, added, []
    h[5] = len(E)
    h[6] = sum(len(c[0]) for c in chunks)
    h[7] = max(h[7], max(len(c[0]) for c in chunks))
    h[8] = max(h[8], max(len(c[1]) for c in chunks))
    h[9] = max(h[9], max(len(c[2]) for c in chunks))
    h[10], h[12] = len(refbuf), len(namebuf)
    man = (struct.pack(HEADER, *h) + b''.join(struct.pack(ENTRY, *e) for e in E)
           + bytes(refbuf) + bufs[1] + bytes(namebuf) + bufs[3])
    head = (b[:4], r[:4], i[:4])
    return done, added, [(names[0], man)] + [(names[n + 1], head[n] + b''.join(c[n] for c in chunks)) for n in range(3)]


def spliced_files(src, only=()):
    """[(path in the mod BIG, bytes)] of every static stream the built mod in <src> changes."""
    mh, mE, mC, mB = parse(*(open(os.path.join(src, f'mod.{x}'), 'rb').read() for x in ('manifest', 'bin', 'relo', 'imp')))
    mod = {(e[0], e[1]): (e, c, refs(mB, e), cstr(mB[2], e[6])) for e, c in zip(mE, mC)}
    for key, (e, c, rl, name) in mod.items():
        print(f'  mod {key[0]:08x}:{key[1]:08x} {name.decode()}: {len(c[0])} bytes, {len(rl)} refs')
    files = []
    for stem, archive, add_new in [('static', GAME, False), ('static_l', GAME, False), ('static_m', GAME, False)] + \
            [(s, a, True) for s, a in TOPS]:
        done, added, fs = splice(stem, mod, only, archive, add_new)
        print(stem, 'replaced', [f'{t:08x}:{n:08x}' for t, n in done], 'added', [f'{t:08x}:{n:08x}' for t, n in added])
        files += fs
    return files


def main():
    src, out = sys.argv[1:3]
    only = {tuple(int(x, 16) for x in a.split(':')) for a in sys.argv[3:]}
    big.write(out, spliced_files(src, only))
    print('->', out, f'{os.path.getsize(out) / 1e6:.0f} MB')


if __name__ == '__main__':
    main()
