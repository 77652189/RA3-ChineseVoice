"""Map lighting and post effects as editable values (GlobalLighting / PostEffectsChunk of a .map, via mapscript).

GlobalLighting v11 (RA3 campaign maps, 452 bytes): u32 time of day, 12 lights of 9 floats (ambient rgb, colour rgb,
direction xyz) = two blocks of six (sun / accent 1 / accent 2 for terrain, then for objects ... as the floats read:
light 0 has the terrain ambient, light 3 the object ambient), then 16 bytes kept raw (not all floats: Brighton Beach has a NaN-pattern word that a float
round trip would change).
PostEffectsChunk v2: u32 count, effects (name, u32 parameter count, parameters of name, type, value) with types
Float / Float2 / Float3 / Float4 / Int (4-16 bytes) and Texture (a name); e.g. Heidelberg: Distortion, LookupTable
(BlendFactor, LookupTexture LUSaturateColors_Vol), Bloom (Intensity).
"""
import struct

LIGHTS = 12
SIZES = {'Float': 4, 'Float2': 8, 'Float3': 12, 'Float4': 16, 'Int': 4}


def _node(m, name):
    return next(n for _, n in m.walk() if n.name == name)


def lighting(m):
    d = _node(m, 'GlobalLighting').head
    tod = struct.unpack_from('<I', d, 0)[0]
    fl = list(struct.unpack_from(f'<{9 * LIGHTS}f', d, 4))
    lights = [dict(ambient=fl[9 * k:9 * k + 3], color=fl[9 * k + 3:9 * k + 6], dir=fl[9 * k + 6:9 * k + 9])
              for k in range(LIGHTS)]
    return dict(time_of_day=tod, lights=lights, rest=d[4 + 36 * LIGHTS:])


def set_lighting(m, lt):
    fl = []
    for x in lt['lights']:
        fl += list(x['ambient']) + list(x['color']) + list(x['dir'])
    _node(m, 'GlobalLighting').head = (struct.pack('<I', lt['time_of_day']) + struct.pack(f'<{len(fl)}f', *fl)
                                       + lt['rest'])


def _pstr(s):
    raw = s.encode('latin-1')
    return struct.pack('<H', len(raw)) + raw


def post_effects(m):
    """[(effect name, [(param name, type, value)])]; value: tuple of floats / int / texture name."""
    d = _node(m, 'PostEffectsChunk').head

    def pstr(p):
        ln = struct.unpack_from('<H', d, p)[0]
        return d[p + 2:p + 2 + ln].decode('latin-1'), p + 2 + ln
    out, p = [], 4
    for _ in range(struct.unpack_from('<I', d, 0)[0]):
        name, p = pstr(p)
        params = []
        n = struct.unpack_from('<I', d, p)[0]
        p += 4
        for _ in range(n):
            pn, p = pstr(p)
            t, p = pstr(p)
            if t == 'Texture':
                v, p = pstr(p)
            elif t == 'Int':
                v, p = struct.unpack_from('<i', d, p)[0], p + 4
            else:
                v = struct.unpack_from(f'<{SIZES[t] // 4}f', d, p)
                p += SIZES[t]
            params.append((pn, t, v))
        out.append((name, params))
    assert p == len(d), 'PostEffectsChunk: trailing bytes'
    return out


def set_post_effects(m, effects):
    body = struct.pack('<I', len(effects))
    for name, params in effects:
        body += _pstr(name) + struct.pack('<I', len(params))
        for pn, t, v in params:
            body += _pstr(pn) + _pstr(t)
            if t == 'Texture':
                body += _pstr(v)
            elif t == 'Int':
                body += struct.pack('<i', v)
            else:
                body += struct.pack(f'<{len(v)}f', *v)
    _node(m, 'PostEffectsChunk').head = body


def selftest():
    """Decode + encode reproduces both chunks of every retail campaign map."""
    import mapscript
    from ra3voice import big
    arc, maps = mapscript.campaign_maps()
    ok = 0
    for n in maps:
        m = mapscript.MapFile(big.read_files(arc, [n])[n])
        a, b = _node(m, 'GlobalLighting').head, _node(m, 'PostEffectsChunk').head
        good = len(a) == 452
        if good:
            set_lighting(m, lighting(m))
        set_post_effects(m, post_effects(m))
        good = good and _node(m, 'GlobalLighting').head == a and _node(m, 'PostEffectsChunk').head == b
        print('OK ' if good else 'BAD', n.split('\\')[-1], [e for e, _ in post_effects(m)])
        ok += good
    print(f'{ok}/{len(maps)}')


if __name__ == '__main__':
    selftest()
