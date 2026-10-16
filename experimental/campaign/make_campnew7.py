"""CampNew6 with a map stream compiled by us (mapxml.py + BinaryAssetBuilder) in place of retail Heidelberg's
map.* / map.10.* / map.11.* (CampNew7).

  python -I -X utf8 experimental/campaign/make_campnew7.py   -> Documents\\Red Alert 3\\Mods\\CampNew7

The stream (mapxml.link): our GameMap, compiled by BAB from the map.xml generated out of the edited .map, plus
every instance it references that the static / global / audio streams lack, copied at their newest (1.12 layout)
layer from the worldbuilder stream and retail Heidelberg's own layers, plus Heidelberg's atlas and campaign
overrides. No GameScriptLists (the scripts come from the .map). A bench run that looks like CampNew6 (textured
terrain, city props, the CNV caption) means our linked stream works.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew6 as c6                      # noqa: E402
import mapxml                                   # noqa: E402
from mapscript import MapFile                   # noqa: E402

c4, c2 = c6.c4, c6.c4.c2
NAME = 'CampNew7'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
MAP_MOD = NAME + 'Map'          # separate SDK mod folder for the map compile
GAME_MAP_ID = 'CAMP_A03_Heidelberg_Smith'      # same id as the retail stream had (atlas lookup unknown yet)

_edited = c4.c2.map_files       # make_campnew6's edited_map_files


def compile_map(m):
    text, unknown = mapxml.map_xml(m, GAME_MAP_ID)
    print('map.xml:', text.count('type="instance"'), 'object files; no definition (roads, waypoints):', unknown)
    rel = os.path.join('data', 'maps', 'official', c2.NEW_STEM)
    src = os.path.join(c2.SDK, 'Mods', MAP_MOD, rel)
    os.makedirs(src, exist_ok=True)
    with open(os.path.join(src, 'map.xml'), 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(text)
    log = os.path.join(c2.SDK, f'_build_{MAP_MOD}.log')
    with open(log, 'w') as f:
        subprocess.run([os.path.join(c2.SDK, 'tools', 'BinaryAssetBuilder.exe'), os.path.join(src, 'map.xml'),
                        r'/od:C:\RA3ModSDK\BuiltMods', r'/iod:C:\RA3ModSDK\BuiltMods', '/ls:true', '/gui:false',
                        '/pc:true', '/vf:false', '/el:0'], cwd=c2.SDK, stdout=f, stderr=subprocess.STDOUT, check=True)
    out = os.path.join(c2.SDK, 'BuiltMods', 'mods', MAP_MOD.lower(), rel)
    return lambda name: open(os.path.join(out, name), 'rb').read()


def map_files():
    files = dict(_edited())
    the_map = next(p for p in files if p.lower().endswith('.map'))
    (bh, bE, bC, bB), braw = mapxml.read_stream('map.', compile_map(MapFile(files[the_map])))
    gm = next(k for k, e in enumerate(bE) if mapxml.sa.cstr(bB[2], e[6]).startswith(b'GameMap:'))
    own = [mapxml.Inst(list(bE[gm]), bC[gm], mapxml.sa.refs(bB, bE[gm]), mapxml.sa.cstr(bB[2], bE[gm][6]),
                       mapxml.sa.cstr(bB[3], bE[gm][7]), 'ours')]
    # retail Heidelberg's own layers (as shipped in the mod: map, map.10, map.11) on top of the worldbuilder stream
    get = files.__getitem__
    base = mapxml.layered([(get, c2.NEW_DIR + s) for s in ('map.', 'map.10.', 'map.11.')])
    library = mapxml.layered(mapxml.WB_LAYERS)
    library.update(base)
    # the base map's own instances besides GameMap / script lists come along: its atlas and its campaign
    # overrides of static objects (AlliedMCV ...), which no reference from the GameMap would pull in
    own += [x for x in base.values() if not x.name.startswith((b'GameMap:', b'GameScriptList:'))]
    have = mapxml.table(mapxml.TOP_TABLES)
    type_hash = {k[0]: v for k, v in have.items()}
    (man, b, r, i), missing, stale = mapxml.link(own, library, have, type_hash, bh, (braw[1][:4], braw[2][:4],
                                                 braw[3][:4]), bB[1])
    (h, E, _, bufs), _ = mapxml.read_stream('', {'manifest': man, 'bin': b, 'relo': r, 'imp': i}.__getitem__)
    names = [mapxml.sa.cstr(bufs[2], e[6]).decode() for e in E]
    count = {}
    for n in names:
        count[n.split(':')[0]] = count.get(n.split(':')[0], 0) + 1
    print('linked stream:', len(E), 'instances', count)
    print('  unresolved references:', [f'{t:08x}:{i:08x}' for t, i in missing], '; older layout:', stale[:10])
    keep = {p: v for p, v in files.items() if not p.split('\\')[-1].lower().startswith('map.')}
    for x, v in zip(('manifest', 'bin', 'relo', 'imp'), (man, b, r, i)):
        keep[c2.NEW_DIR + 'map.' + x] = v
    return sorted(keep.items())


c4.c2.map_files = map_files

if __name__ == '__main__':
    c4.main()
