"""Compile a map's own asset stream (map.manifest / .bin / .relo / .imp) ourselves instead of copying a retail one.

  python -I -X utf8 experimental/campaign/mapxml.py <archive> <map path>    -> prints the map.xml it would compile

What a map stream holds (retail Heidelberg, 883 instances): the TerrainTextureAtlas (16.7 MB, the packed terrain
textures), the GameObjects the map places that the static streams do not have (campaign units, city props), the
GameMap (every placed object, 371 KB) and per-player GameScriptLists. WorldBuilder writes this as map.xml next to the
.map (the SDK's 360_DLC_TestMap shows the format: Includes of every object XML used, GameMap, TerrainTextureAtlas,
GameScriptList) and BinaryAssetBuilder compiles that; BAB does compile it here (2026-10-16).

The SDK has no terrain texture sources (no ART:Terrain/*.tga), so BAB cannot build a real atlas; the atlas instance
is taken from a retail map stream instead (append_instance), which is fine for maps that reuse a retail map's
terrain textures. A non-official map (map cache flags 0) takes terrain, objects and scripts from the .map itself
(our script edits in CampNew5/6 work while the stream still has retail Heidelberg's GameMap / GameScriptLists), so
this first compiler leaves GameMap and the script lists out: Includes + atlas only.
"""
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import splice_assets as sa                     # noqa: E402
from ra3voice import big, refpack              # noqa: E402

SDK = r'C:\RA3ModSDK'
SAGE = os.path.join(SDK, 'SageXML')
INDEX = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'work', 'sagexml_gameobjects.json')
GAME_ALL_TYPES_HASH = 1424942948


def _props(m, d, p):
    return {k: v for k, (t, v) in _typed_props(m, d, p).items()}


def _typed_props(m, d, p):
    """Property dictionary (objects, WorldInfo): u16 count, then u8 type, u24 key (name table index), value
    (0 bool u8, 1 int, 2 real, 3 ascii u16-prefixed, 4 unicode u16-prefixed UTF-16, 5 asset id 'Type:name')."""
    out, count = {}, struct.unpack_from('<H', d, p)[0]
    p += 2
    for _ in range(count):
        t, key = d[p], m.table.get(int.from_bytes(d[p + 1:p + 4], 'little'), '?')
        p += 4
        if t == 0:
            v, p = d[p], p + 1
        elif t in (1, 2):
            v, p = struct.unpack_from('<i' if t == 1 else '<f', d, p)[0], p + 4
        else:
            ln = struct.unpack_from('<H', d, p)[0] * (2 if t == 4 else 1)
            v = d[p + 2:p + 2 + ln].decode('utf-16-le' if t == 4 else 'latin-1')
            p += 2 + ln
        out[key] = (t, v)
    return out


def environment(m):
    """GameMap's EnvironmentData / WorldDict / PostEffect from the .map's EnvironmentData (v5: 2 x f32, macro,
    cloud and environment texture names), WorldInfo (a property dictionary) and PostEffectsChunk (v2: u32 count,
    effects of name + parameters; texture parameters become PostEffect entries). Without EnvironmentData the macro
    and cloud textures go unreferenced and the whole scene renders magenta (CampNew7 second run)."""
    rows = []
    node = {n.name: n for _, n in m.walk() if n.name in ('EnvironmentData', 'WorldInfo', 'PostEffectsChunk')}
    if 'EnvironmentData' in node:
        d, p, names = node['EnvironmentData'].head, 8, []
        for _ in range(3):
            ln = struct.unpack_from('<H', d, p)[0]
            names.append(d[p + 2:p + 2 + ln].decode('latin-1'))
            p += 2 + ln
        macro, cloud, env = names
        rows.append(f'\t\t<EnvironmentData Cloud="{_q(cloud)}" Environment="{_q(env)}" Macro="{_q(macro)}" />')
    if 'WorldInfo' in node:
        kind = {0: 'BoolProperty', 1: 'IntProperty', 2: 'RealProperty', 3: 'StringProperty',
                4: 'UnicodeStringProperty', 5: 'AssetIdProperty'}
        props = []
        for k, (t, v) in _typed_props(m, node['WorldInfo'].head, 0).items():
            v = ('true' if v else 'false') if t == 0 else v.split(':', 1)[-1] if t == 5 else v
            props.append(f'\t\t\t<{kind[t]} Key="{_q(k)}" Value="{_q(str(v))}" />')
        rows.append('\t\t<WorldDict>\n' + '\n'.join(props) + '\n\t\t</WorldDict>')
    if 'PostEffectsChunk' in node:
        d = node['PostEffectsChunk'].head

        def pstr(p):
            ln = struct.unpack_from('<H', d, p)[0]
            return d[p + 2:p + 2 + ln].decode('latin-1'), p + 2 + ln
        p = 4
        for _ in range(struct.unpack_from('<I', d, 0)[0]):
            _, p = pstr(p)
            n = struct.unpack_from('<I', d, p)[0]
            p += 4
            for _ in range(n):
                _, p = pstr(p)
                t, p = pstr(p)
                if t == 'Texture':
                    v, p = pstr(p)
                    rows.append(f'\t\t<PostEffect Effect="{_q(v)}" />')
                else:
                    p += {'Float': 4, 'Float2': 8, 'Float3': 12, 'Float4': 16, 'Int': 4}[t]
    return rows


def objects(m):
    """Every Object in the .map's ObjectsList (v3: x, y, z, angle f32, u32 flags, template, properties)."""
    out = []
    for _, n in m.walk():
        if n.name == 'Object':
            d = n.head
            x, y, z, angle, flags = struct.unpack_from('<ffffI', d, 0)
            ln = struct.unpack_from('<H', d, 20)[0]
            out.append(dict(x=x, y=y, z=z, angle=angle, flags=flags, template=d[22:22 + ln].decode('latin-1'),
                            props=_props(m, d, 22 + ln)))
    return out


def object_templates(m):
    return [o['template'] for o in objects(m)]


def sage_index():
    """GameObject id (lower case) -> {file: 'DATA:<path>', its GameObject tag attributes} over SageXML (cached)."""
    if os.path.exists(INDEX):
        with open(INDEX, encoding='utf-8') as f:
            return json.load(f)
    tag, attr = re.compile(rb'<GameObject\b([^>]*)>', re.S), re.compile(rb'(\w+)="([^"]*)"')
    out = {}
    for root, _, files in os.walk(SAGE):
        for fn in files:
            if fn.lower().endswith('.xml'):
                p = os.path.join(root, fn)
                with open(p, 'rb') as f:
                    data = f.read()
                for mm in tag.finditer(data):
                    a = {k.decode(): v.decode('latin-1') for k, v in attr.findall(mm.group(1))
                         if k in (b'id', b'inheritFrom', b'EditorSorting', b'KindOf')}
                    if 'id' in a:
                        a['file'] = 'DATA:' + os.path.relpath(p, SAGE).replace('\\', '/')
                        out.setdefault(a.pop('id').lower(), a)
    os.makedirs(os.path.dirname(INDEX), exist_ok=True)
    with open(INDEX, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=0, sort_keys=True)
    return out


def editor_sorting(index, template):
    t = template.lower()
    for _ in range(20):
        a = index.get(t)
        if a is None:
            return None
        if 'EditorSorting' in a:
            return a['EditorSorting']
        t = a.get('inheritFrom', '').lower()
    return None


# GameMap element per EditorSorting, as in the SDK's 360_DLC_TestMap (WorldBuilder export): AUDIO -> Audio,
# STRUCTURE -> Structure, *_PROPS -> Prop; units are 'Unit', anything else 'Unknown'
def element(index, template):
    s = editor_sorting(index, template) or ''
    if s == 'AUDIO':
        return 'Audio'
    if s == 'STRUCTURE':
        return 'Structure'
    if s.endswith('PROPS'):
        return 'Prop'
    if s in ('UNIT', 'INFANTRY', 'VEHICLE', 'AIRCRAFT', 'SHIP'):
        return 'Unit'
    return 'Unknown'


def stream_names(stem='static.12', archive=sa.DATA + r'\Core12.big'):
    """Lower-case asset names ('gameobject:foo') in a retail stream's table (the top stream sees the whole chain)."""
    name = f'data\\{stem}.manifest'
    m = big.read_files(archive, [name])[name]
    m = refpack.decompress(m) if refpack.is_refpack(m) else m
    h = struct.unpack_from(sa.HEADER, m, 0)
    o = 48 + 48 * h[5] + h[10] + h[11]
    return {s.decode('latin-1').lower() for s in m[o:o + h[12]].split(b'\0') if s}


def _q(s):
    return s.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')


def game_map(m, gid, index):
    """GameMap XML: every placed object (BAB only writes the included object XMLs that something in map.xml
    references, so this is what pulls the map's templates into the stream). Waypoints by name, roads (objects whose
    template is no GameObject) once each by road type, the rest by EditorSorting with team, health, angle."""
    rows, roads = [], set()
    for o in objects(m):
        t, p = o['template'], o['props']
        pos = f'<Position x="{o["x"]:.6f}" y="{o["y"]:.6f}" z="{o["z"]:.6f}" />'
        if t == '*Waypoints/Waypoint':
            rows.append(f'\t\t<Waypoint id="{_q(p.get("waypointName", ""))}">{pos}</Waypoint>')
        elif t.lower() not in index:
            roads.add(t)
        else:
            el = element(index, t)
            owner = p.get('originalOwner', '/team')
            usp = (f' Faction="{_q(owner)}" Team="{_q(owner.split("/")[0])}" Health="{p.get("objectInitialHealth", 100)}"'
                   f' EventList=""' if el in ('Structure', 'Unit', 'Prop') else '')
            rows.append(f'\t\t<{el} Angle="{o["angle"]:.6f}"{usp} ThingTemplate="{_q(t)}" id="{_q(t)}">{pos}</{el}>')
    rows += [f'\t\t<Road id="{_q(r)}" />' for r in sorted(roads)]
    order = ['Waypoint', 'Structure', 'Unit', 'Prop', 'Audio', 'Unknown', 'Road']    # the schema's sequence
    rows.sort(key=lambda r: order.index(r[3:].split(' ')[0].split('>')[0]))
    rows += environment(m)          # EnvironmentData, WorldDict, PostEffect follow in the schema
    return f'\t<GameMap id="{_q(gid)}">\n' + '\n'.join(rows) + '\n\t</GameMap>\n'


def map_xml(m, gid):
    """(map.xml text, [templates without a SageXML definition]): Includes of the object XMLs the map places that
    the static streams lack (reference includes resolve everything else against the retail streams) + GameMap."""
    index, static = sage_index(), stream_names()
    used = sorted(set(object_templates(m)), key=str.lower)
    need = [t for t in used if 'gameobject:' + t.lower() not in static]
    files = sorted({index[t.lower()]['file'] for t in need if t.lower() in index}, key=str.lower)
    unknown = [t for t in need if t.lower() not in index]
    inc = ['\t\t<Include type="reference" source="DATA:static.xml"/>',
           '\t\t<Include type="reference" source="DATA:global.xml"/>',
           '\t\t<Include type="reference" source="DATA:audio.xml"/>']
    inc += [f'\t\t<Include type="instance" source="{s}"/>' for s in files]
    text = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<AssetDeclaration xmlns="uri:ea.com:eala:asset" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            '\t<Tags/>\n\t<Includes>\n' + '\n'.join(inc) + '\n\t</Includes>\n' + game_map(m, gid, index)
            + '</AssetDeclaration>\n')
    return text, unknown


def read_stream(prefix, get):
    """parse() of the stream whose files are get(prefix + 'manifest') etc."""
    raw = []
    for x in ('manifest', 'bin', 'relo', 'imp'):
        v = get(prefix + x)
        raw.append(refpack.decompress(v) if refpack.is_refpack(v) else v)
    return sa.parse(*raw), raw


def write_stream(h, E, chunks, bufs, heads):
    h = list(h)
    h[5] = len(E)
    h[6] = sum(len(c[0]) for c in chunks)
    h[7] = max([0] + [len(c[0]) for c in chunks])
    h[8] = max([0] + [len(c[1]) for c in chunks])
    h[9] = max([0] + [len(c[2]) for c in chunks])
    h[10], h[11], h[12], h[13] = (len(x) for x in bufs)
    man = struct.pack(sa.HEADER, *h) + b''.join(struct.pack(sa.ENTRY, *e) for e in E) + b''.join(bufs)
    return [man] + [heads[n] + b''.join(c[n] for c in chunks) for n in range(3)]


def append_instance(stream, other, name):
    """Copy the instance called `name` (no references of its own, e.g. a TerrainTextureAtlas) from the parsed
    stream `other` to the end of `stream`; both are (parse() result, raw files)."""
    (h, E, chunks, bufs), raw = stream
    (_, oE, oC, oB), _ = other
    k = next(k for k, e in enumerate(oE) if sa.cstr(oB[2], e[6]).decode() == name)
    e = list(oE[k])
    assert e[5] == 0, f'{name} references other assets'
    bufs = list(bufs)
    e[4] = len(bufs[0])
    e[6] = len(bufs[2])
    bufs[2] = bufs[2] + name.encode('latin-1') + b'\0'
    e[7] = len(bufs[3])
    bufs[3] = bufs[3] + sa.cstr(oB[3], oE[k][7]) + b'\0'
    return write_stream(h, E + [e], chunks + [oC[k]], bufs, (raw[1][:4], raw[2][:4], raw[3][:4]))


# ------------------------------------------------------------------ linker
# BAB's GameObjects are no good for the game: the 1.11 patch changed the GameObject layout (type hash 3621320486 in
# the SDK and retail map.10 streams, 3415017856 in map.11 / static.12) and re-emitted every GameObject of every map
# stream. GameMap kept its layout (4100291602 everywhere). So our stream is linked: our GameMap (BAB) + every
# instance it needs that the static / global / audio streams lack, copied from retail streams at their newest layer
# (the 1.12 layout), closed over references; the game checks nothing else (append_instance probe CampNew7).
WB_LAYERS = [('WBData.big', 'data\\worldbuilder.'), ('Core5.big', 'data\\worldbuilder.5.'),
             ('Core9.big', 'data\\worldbuilder.9.'), ('Core10.big', 'data\\worldbuilder.10.'),
             ('Core11.big', 'data\\worldbuilder.11.')]
TOP_TABLES = [('Core12.big', 'data\\static.12.'), ('Core12.big', 'data\\global.12.'), ('EnglishAudio5.big', 'data\\audio.5.')]


class Inst:
    __slots__ = ('entry', 'chunks', 'refs', 'name', 'source', 'layer')

    def __init__(self, entry, chunks, refs, name, source, layer):
        self.entry, self.chunks, self.refs, self.name, self.source, self.layer = \
            entry, chunks, refs, name, source, layer


def _archive_get(archive):
    path = archive if os.path.isabs(archive) else os.path.join(sa.DATA, archive)
    cache = {}

    def get(name):
        if name not in cache:
            cache.update(big.read_files(path, [name]))
        return cache[name]
    return get


def layered(layers):
    """{(type id, instance id): Inst} over streams given bottom to top as (archive or getter, path prefix); each
    instance from the topmost layer that carries its data (patch layers keep 0-size entries pointing back)."""
    out = {}
    for src, prefix in layers:
        get = _archive_get(src) if isinstance(src, str) else src
        (h, E, chunks, bufs), _ = read_stream(prefix, get)
        for e, c in zip(E, chunks):
            if e[8]:
                out[(e[0], e[1])] = Inst(list(e), c, sa.refs(bufs, e), sa.cstr(bufs[2], e[6]), sa.cstr(bufs[3], e[7]),
                                         prefix)
            elif (e[0], e[1]) in out:
                # a 0-size patch entry still re-declares the type hash: 1.10 bumped SpecialPowerTemplate's hash
                # with the data unchanged in the base layer; the old hash crashes the game ("Type hash mismatch
                # for type 0x81d85efa ... DID YOU REMEMBER TO BUILD DATA???", CampNew7 first run)
                out[(e[0], e[1])].entry[2:4] = e[2:4]
    return out


def table(layers):
    """{(type id, instance id): type hash} of the top streams the map stream references."""
    out = {}
    for arc, prefix in layers:
        name = prefix + 'manifest'
        m = big.read_files(os.path.join(sa.DATA, arc), [name])[name]
        m = refpack.decompress(m) if refpack.is_refpack(m) else m
        h = struct.unpack_from(sa.HEADER, m, 0)
        for k in range(h[5]):
            e = struct.unpack_from(sa.ENTRY, m, 48 + 48 * k)
            out[(e[0], e[1])] = e[2]
    return out


def link(own, library, have, type_hash, header, heads, manifests):
    """Stream files (manifest, bin, relo, imp) holding `own` instances (ours, e.g. the GameMap) + everything they
    reference, transitively, that is not in `have` (the referenced streams), copied from `library`. Instances come
    in dependency order (references first); `type_hash` ({type id: hash} of the game's streams) flags instances in
    an older layout. Header fields other than counts and sizes come from `header` (BAB's), AllTypesHash the game's.
    Returns (files, missing references, names in an older layout)."""
    picked, missing, order = {}, set(), []
    # an untyped AssetIdProperty (WorldDict musicZone) compiles to a reference of a generic type (50c68ad4); point
    # such a reference at the one asset with that instance id
    by_id = {}
    for k in list(have) + list(library):
        by_id.setdefault(k[1], set()).add(k)
    for inst in own:
        inst.refs = [r if r in have or r in library or len(by_id.get(r[1], ())) != 1 else next(iter(by_id[r[1]]))
                     for r in inst.refs]

    def visit(key, inst):
        if key in picked:
            return
        picked[key] = inst
        for r in inst.refs:
            if r in have or r in picked:
                continue
            if r in library:
                visit(r, library[r])
            else:
                missing.add(r)
        order.append(key)
    for inst in own:
        visit((inst.entry[0], inst.entry[1]), inst)
    stale = [picked[k].name.decode() for k in order
             if type_hash.get(picked[k].entry[0], picked[k].entry[2]) != picked[k].entry[2]]
    E, chunks, bufs = [], [], [bytearray(), bytearray(manifests), bytearray(), bytearray()]
    for k in order:
        inst = picked[k]
        e = list(inst.entry)
        e[4], e[5] = len(bufs[0]), len(inst.refs)
        bufs[0] += b''.join(struct.pack('<II', *r) for r in inst.refs)
        e[6] = len(bufs[2])
        bufs[2] += inst.name + b'\0'
        e[7] = len(bufs[3])
        bufs[3] += inst.source + b'\0'
        e[8], e[9], e[10] = (len(x) for x in inst.chunks)
        E.append(e)
        chunks.append(inst.chunks)
    h = list(header)
    h[4] = GAME_ALL_TYPES_HASH
    return write_stream(h, E, chunks, [bytes(b) for b in bufs], heads), missing, stale


def main():
    from mapscript import MapFile
    arc = os.path.join(sa.DATA, sys.argv[1]) if not os.path.isabs(sys.argv[1]) else sys.argv[1]
    m = MapFile(big.read_files(arc, [sys.argv[2]])[sys.argv[2]])
    text, unknown = map_xml(m, os.path.splitext(os.path.basename(sys.argv[2]))[0])
    print(text)
    print('no SageXML definition:', unknown)


if __name__ == '__main__':
    main()
