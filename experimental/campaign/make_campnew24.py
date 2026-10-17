"""Two light tanks side by side (CampNew24): the parametric Blender one (CampNew23, CNV_LightTank / CNTankL) and
the AI-shaped one (experimental/units/ai_lighttank.py + ai_lighttank_blend.py -> work/units/lighttank_ai/blend,
CNV_LightTankAI / CNTankA), both on the Guardian's logic and the same bake, facing east, Soviet tank due north.

  python -I -X utf8 experimental/campaign/make_campnew24.py   -> Documents\\Red Alert 3\\Mods\\CampNew24
"""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew23 as c23                    # noqa: E402

c18, c7, c6, c4, c2 = c23.c18, c23.c7, c23.c6, c23.c4, c23.c2
newmap, to_w3x = c23.newmap, c23.to_w3x
NAME = 'CampNew24'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
AI_UNIT, AI_MODEL = 'CNV_LightTankAI', 'CNTankA'
AI_SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'work', 'units', 'lighttank_ai', 'blend')
c7.EXTRA_TEMPLATES[AI_UNIT] = {'file': 'DATA:CNVUnits/Data/' + AI_UNIT + '.xml', 'EditorSorting': 'UNIT'}
c4.c3.STRINGS['Name:' + AI_UNIT] = 'CNV 轻型坦克（AI）'
AI_AT = (c23.TANK_AT[0], c23.TANK_AT[1] - 45)          # just south of the parametric tank
AI_PARTS = {'HULL': 'BODY', 'TURRET': 'Bone_Turret'}


def ai_pivots():
    """Guardian bone names placed on the AI shape from ai_lighttank_blend.py's '_pivots' and the hull's size."""
    with open(os.path.join(AI_SRC, 'parts.json'), encoding='utf-8') as f:
        parts = json.load(f)
    pv = parts['_pivots']
    hull = parts['HULL']['vertices']
    x0, x1 = min(v[0] for v in hull), max(v[0] for v in hull)
    y1 = max(abs(v[1]) for v in hull)
    z1 = max(v[2] for v in hull)
    t, p, m = pv['turret'], pv['pitch'], pv['muzzle']
    ty = 0.9 * y1                                     # tread line, just inside the hull side
    return [('BODY', None, (0, 0, 0)),
            ('Bone_Turret', None, tuple(t)), ('Bone_Turret_Pitch', 'Bone_Turret', tuple(p)),
            ('BONE_GUN_MUZZLE', 'Bone_Turret_Pitch', tuple(m)),
            ('FXBone_Muzzle', 'Bone_Turret_Pitch', (m[0] + 0.7, m[1], m[2])),
            ('FX_Laser', 'Bone_Turret', (0, 0, 3.0)), ('FX_Damage01', None, (0.4 * x0, 0, z1)),
            ('FXTracksL', None, (x0, ty, 0)), ('FXTracksR', None, (x0, -ty, 0))] + \
        [(f'Bone_{kind}_{fr}_{side}', None, (0.5 * (x1 if fr == 'Front' else x0), ty if side == 'Left' else -ty, 2.4))
         for kind in ('Tread', 'Tracks') for fr in ('Front', 'Rear') for side in ('Left', 'Right')]


def unit_xml(unit, model):
    src = open(os.path.join(c2.SDK, 'SageXML', 'Allied', 'Units', 'AlliedAntiVehicleVehicleTech1.xml'),
               encoding='utf-8').read()
    x = src.replace('id="AlliedAntiVehicleVehicleTech1"', f'id="{unit}"')
    x = x.replace('EditorName="AlliedAntiVehicleVehicleTech1"', f'EditorName="{unit}"')
    x = re.sub(r'(<Model\s+Name=")[^"]*(")', lambda mm: mm.group(1) + model.upper() + mm.group(2), x)
    x = re.sub(r'AnimationName="[^"]*"', f'AnimationName="{model.upper()}_IDLE"', x)
    x = re.sub(r'\s*<TreadScrollingMap\b[^>]*/>', '', x)
    x = x.replace('>Name:AlliedAntiVehicleVehicleTech1<', f'>Name:{unit}<')
    x = x.replace('<Includes>', f'<Includes>\n\t\t<Include type="all" source="ART:{model}.w3x" />'
                                f'\n\t\t<Include type="all" source="ART:{model}_IDLE.w3x" />', 1)
    path = os.path.join(c2.SDK, 'Mods', 'CNVUnits', 'Data', unit + '.xml')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(x.replace('\r\n', '\n'))


def generate(m):
    c23._generate(m)
    print('model', c23.MODEL, to_w3x.convert(c23.SRC, c23.MODEL, c23.PIVOTS, c23.PARTS, scale=c23.SCALE), 'triangles')
    print('model', AI_MODEL, to_w3x.convert(AI_SRC, AI_MODEL, ai_pivots(), AI_PARTS,
                                            src_name='CNTankL', scale=c23.SCALE), 'triangles')
    unit_xml(c23.UNIT, c23.MODEL)
    unit_xml(AI_UNIT, AI_MODEL)
    objs = next(n for _, n in m.walk() if n.name == 'ObjectsList')
    p1 = next(k for k in objs.kids if b'AlliedAntiVehicleVehicleTech1' in k.head[:60])
    s1 = next(k for k in objs.kids if b'SovietAntiVehicleVehicleTech1' in k.head[:60])
    for src, template, (x, y), angle in ((p1, c23.UNIT, c23.TANK_AT, 0.0), (p1, AI_UNIT, AI_AT, 0.0),
                                         (s1, 'SovietAntiVehicleVehicleTech1', c23.ENEMY_AT, -math.pi / 2)):
        pr, flags = newmap.typed_props_of(m, src)
        objs.kids.append(newmap.object_node(m, pr, flags, template, x, y, angle=angle,
                                            uniqueID=f'{template} {len(objs.kids)}'))


c6.edit = generate

if __name__ == '__main__':
    if c23.game_running():
        c2.OUT = c4.OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'work', 'staging', NAME)
        print('RA3 is running -> staging at', c4.OUT)
    c4.main()
