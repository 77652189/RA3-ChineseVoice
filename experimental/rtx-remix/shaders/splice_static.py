"""splice_static.py <mod.big with BAB-compiled Texture assets> <out.big>
Retail RA3 static stream with every Texture instance found in the mod's data\\mod.* spliced in (same asset id),
written as data\\static.{manifest,bin,relo,imp}. Proven to load through -modConfig (probe B, 2026-10-14)."""
import struct, sys
sys.path.insert(0, r'C:\Users\63097\Desktop\RA3-ChineseVoice')
from ra3voice import big, refpack

src, out = sys.argv[1:3]
GAME = r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\StaticStream.big'
ONE_POINTER = bytes.fromhex('04000000ffffffff')


def instances(m, binf):
    h = list(struct.unpack_from('<BBHIIIIIIIIIII', m, 0))
    E = [list(struct.unpack_from('<12I', m, 48 + i * 48)) for i in range(h[5])]
    pos, inst = 4, []
    for e in E:
        inst.append(binf[pos:pos + e[8]])
        pos += e[8]
    assert pos == len(binf)
    return h, E, inst


f = big.read_files(src, ['data\\mod.manifest', 'data\\mod.bin'])
_, mE, mI = instances(f['data\\mod.manifest'], f['data\\mod.bin'])
TEXTURE = 0x21e727da
repl = {(e[0], e[1]): d for e, d in zip(mE, mI) if e[0] == TEXTURE}

st = big.read_files(GAME, ['data\\static.' + x for x in ('manifest', 'bin', 'relo', 'imp')])
st = {k: (refpack.decompress(v) if refpack.is_refpack(v) else v) for k, v in st.items()}
m = bytearray(st['data\\static.manifest'])
h, E, inst = instances(m, st['data\\static.bin'])
ro, relo, done = 4, st['data\\static.relo'], 0
for i, e in enumerate(E):
    if (e[0], e[1]) in repl:
        assert relo[ro:ro + e[9]] == ONE_POINTER
        inst[i] = repl[(e[0], e[1])]
        e[8] = len(inst[i])
        struct.pack_into('<12I', m, 48 + i * 48, *e)
        done += 1
    ro += e[9]
assert done == len(repl), (done, len(repl))
h[6] = sum(len(x) for x in inst)
h[7] = max(h[7], max(len(x) for x in inst))
struct.pack_into('<BBHIIIIIIIIIII', m, 0, *h)
big.write(out, [('data\\static.manifest', bytes(m)), ('data\\static.bin', st['data\\static.bin'][:4] + b''.join(inst)),
                ('data\\static.relo', st['data\\static.relo']), ('data\\static.imp', st['data\\static.imp'])])
print('replaced', done, 'textures ->', out)
