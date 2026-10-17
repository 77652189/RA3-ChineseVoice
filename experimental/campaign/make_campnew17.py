"""A unit with a model of our own (CampNew17): a procedurally built flying saucer (w3x.lathe -> W3X, textures
painted in code) on the hydrofoil's logic, placed and scripted like CampNew13's ship.

  python -I -X utf8 experimental/campaign/make_campnew17.py   -> Documents\\Red Alert 3\\Mods\\CampNew17

Nothing of the model comes from EA: geometry, normals, UVs and the three textures (diffuse, flat normal map,
spec map with a team-colour band in blue) are generated here and compiled by BinaryAssetBuilder from
C:\\RA3ModSDK\\Art\\CN\\. Seen on the bench = we can make units from scratch; a modelled / AI-generated mesh is
then only a different input to w3x.model.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew7 as c7                      # noqa: E402
import mapxml                                   # noqa: E402
import w3x                                      # noqa: E402

c6, c4, c2 = c7.c6, c7.c4, c7.c2
NAME = 'CampNew17'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
UNIT, UNIT_NAME, LIKE = 'CNV_Saucer', 'UNIT - CNV Saucer', 'UNIT - Hydrofoil 01'
MODEL = 'CNSaucer'
UNIT_FILE = os.path.join(c2.SDK, 'Mods', 'CNVUnits', 'Data', UNIT + '.xml')
c7.EXTRA_TEMPLATES[UNIT] = {'file': 'DATA:CNVUnits/Data/' + UNIT + '.xml', 'EditorSorting': 'UNIT'}
c4.c3.STRINGS['Name:' + UNIT] = 'CNV 飞碟'
# (radius, height) from the top of the dome down to the keel
PROFILE = [(0.0, 15.0), (3.5, 14.6), (6.5, 13.2), (8.8, 11.0), (10.0, 8.5), (11.0, 7.6), (18.0, 6.6),
           (26.0, 5.2), (31.0, 3.8), (32.0, 2.6), (31.0, 1.6), (26.0, 0.6), (18.0, -0.6), (10.0, -2.2),
           (5.0, -3.2), (0.0, -3.6)]
DOME_END, RIM = 4 / 15, (7 / 15, 10 / 15)       # texture rows (v) of the dome and the rim band


def textures():
    size = 256

    def diffuse(x, y):
        v = y / size
        if v < DOME_END:                                            # glass dome
            g = 0.55 + 0.45 * (1 - v / DOME_END)
            return int(90 * g), int(200 * g), int(230 * g), 255
        if RIM[0] <= v <= RIM[1]:                                   # rim with a row of lights
            light = (x // 8) % 4 == 0 and abs(v - sum(RIM) / 2) < 0.03
            return (255, 230, 140, 255) if light else (70, 74, 82, 255)
        panel = (x % 32 == 0) or (int(v * 64) % 8 == 0)              # hull plates
        base = 150 + int(20 * math.sin(x / size * 2 * math.pi * 3))
        return (base - 40, base - 35, base - 25, 255) if panel else (base, base + 4, base + 12, 255)

    def spec(x, y):
        v = y / size
        team = 255 if RIM[0] - 0.06 <= v < RIM[0] else 0                # team-colour band above the rim
        return 200 if v < DOME_END else 110, 0, team, 255

    w3x.write_texture(MODEL, size, size, diffuse)
    w3x.write_texture(MODEL + '_NRM', 16, 16, lambda x, y: (128, 128, 255, 255))
    w3x.write_texture(MODEL + '_SPM', size, size, spec)


def unit_xml():
    src = open(os.path.join(c2.SDK, 'SageXML', 'Allied', 'Units', 'AlliedAntiAirShip.xml'), encoding='utf-8').read()
    x = src.replace('id="AlliedAntiAirShip"', f'id="{UNIT}"').replace('EditorName="AlliedAntiAirShip"',
                                                                      f'EditorName="{UNIT}"')
    x = x.replace('Name="AUAntiAirShip_SKN"', f'Name="{MODEL.upper()}"')
    x = x.replace('>Name:AlliedAntiAirShip<', f'>Name:{UNIT}<')
    x = x.replace('<Includes>', f'<Includes>\n\t\t<Include type="all" source="ART:{MODEL}.w3x" />', 1)
    os.makedirs(os.path.dirname(UNIT_FILE), exist_ok=True)
    with open(UNIT_FILE, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(x.replace('\r\n', '\n'))


_edit = c6.edit


def edit(m):
    _edit(m)
    textures()
    verts, normals, uvs, tris = w3x.lathe(PROFILE, segments=40)
    w3x.write_model(MODEL, w3x.model(MODEL, verts, normals, uvs, tris, MODEL, MODEL + '_NRM', MODEL + '_SPM'))
    print(f'model {MODEL}: {len(verts)} vertices, {len(tris)} triangles')
    unit_xml()
    like = next(o for o in mapxml.objects(m) if o['props'].get('objectName') == LIKE)
    mapxml.place_object(m, LIKE, UNIT, like['x'] + 60, like['y'] - 60, name=UNIT_NAME)
    print(f'placed {UNIT}; actions copied from {LIKE!r}:', m.duplicate_contents(LIKE, UNIT_NAME))


c6.edit = edit

if __name__ == '__main__':
    c4.main()
