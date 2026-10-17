"""CNV light tank in game (CampNew23): the Blender-built model (experimental/units/cnv_lighttank.py -> work/units/
lighttank) converted by units/to_w3x.py, on the Guardian's logic, on CampNew18's generated island; facing east
with a Soviet tank due north, so the turret has something to turn to.

  python -I -X utf8 experimental/campaign/make_campnew23.py   -> Documents\\Red Alert 3\\Mods\\CampNew23
"""
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'units'))
import make_campnew18 as c18                    # noqa: E402
import newmap                                   # noqa: E402
import to_w3x                                   # noqa: E402

c7, c6, c4, c2 = c18.c7, c18.c6, c18.c4, c18.c2
NAME = 'CampNew23'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
UNIT, MODEL = 'CNV_LightTank', 'CNTankL'
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'work', 'units', 'lighttank')
UNIT_FILE = os.path.join(c2.SDK, 'Mods', 'CNVUnits', 'Data', UNIT + '.xml')
c7.EXTRA_TEMPLATES[UNIT] = {'file': 'DATA:CNVUnits/Data/' + UNIT + '.xml', 'EditorSorting': 'UNIT'}
c4.c3.STRINGS['Name:' + UNIT] = 'CNV 轻型坦克'
TANK_AT = (c18.START[0] + 120, c18.START[1] + 230)
ENEMY_AT = (TANK_AT[0], TANK_AT[1] + 230)
# bones the Guardian's XML names (turret, pitch, muzzle, laser, damage smoke, track marks, treads), placed on
# the Blender model (cnv_lighttank.py TURRET_AT / PITCH_AT and part sizes)
PIVOTS = [('BODY', None, (0, 0, 0)),
          ('Bone_Turret', None, (0.5, 0, 9.0)), ('Bone_Turret_Pitch', 'Bone_Turret', (7.4, 0, 2.6)),
          ('BONE_GUN_MUZZLE', 'Bone_Turret_Pitch', (17.9, 0, 0.1)), ('FXBone_Muzzle', 'Bone_Turret_Pitch', (18.6, 0, 0.1)),
          ('FX_Laser', 'Bone_Turret', (-3.0, -2.8, 6.2)), ('FX_Damage01', None, (-8, 0, 9.5)),
          ('FXTracksL', None, (-17, 10.4, 0)), ('FXTracksR', None, (-17, -10.4, 0))] + \
         [(f'Bone_{kind}_{fr}_{side}', None, (9 if fr == 'Front' else -9, 10.4 if side == 'Left' else -10.4, 2.4))
          for kind in ('Tread', 'Tracks') for fr in ('Front', 'Rear') for side in ('Left', 'Right')]
SCALE = 1.35                     # to the Guardian's on-screen size
PARTS = {'HULL': 'BODY', 'TREADS': 'BODY', 'TURRET': 'Bone_Turret', 'BARREL': 'Bone_Turret_Pitch'}


def unit_xml():
    src = open(os.path.join(c2.SDK, 'SageXML', 'Allied', 'Units', 'AlliedAntiVehicleVehicleTech1.xml'),
               encoding='utf-8').read()
    x = src.replace('id="AlliedAntiVehicleVehicleTech1"', f'id="{UNIT}"')
    x = x.replace('EditorName="AlliedAntiVehicleVehicleTech1"', f'EditorName="{UNIT}"')
    x = re.sub(r'(<Model\s+Name=")[^"]*(")', lambda m: m.group(1) + MODEL.upper() + m.group(2), x)
    x = re.sub(r'AnimationName="[^"]*"', f'AnimationName="{MODEL.upper()}_IDLE"', x)
    x = re.sub(r'\s*<TreadScrollingMap\b[^>]*/>', '', x)       # needs tread meshes named Bone_Tread_*
    x = x.replace('>Name:AlliedAntiVehicleVehicleTech1<', f'>Name:{UNIT}<')
    x = x.replace('<Includes>', f'<Includes>\n\t\t<Include type="all" source="ART:{MODEL}.w3x" />'
                                f'\n\t\t<Include type="all" source="ART:{MODEL}_IDLE.w3x" />', 1)
    os.makedirs(os.path.dirname(UNIT_FILE), exist_ok=True)
    with open(UNIT_FILE, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(x.replace('\r\n', '\n'))


_generate = c6.edit


def generate(m):
    _generate(m)
    print('model', MODEL, to_w3x.convert(SRC, MODEL, PIVOTS, PARTS, scale=SCALE), 'triangles')
    unit_xml()
    objs = next(n for _, n in m.walk() if n.name == 'ObjectsList')
    p1 = next(k for k in objs.kids if b'AlliedAntiVehicleVehicleTech1' in k.head[:60])
    s1 = next(k for k in objs.kids if b'SovietAntiVehicleVehicleTech1' in k.head[:60])
    for src, template, (x, y), angle in ((p1, UNIT, TANK_AT, 0.0),
                                         (s1, 'SovietAntiVehicleVehicleTech1', ENEMY_AT, -math.pi / 2)):
        pr, flags = newmap.typed_props_of(m, src)
        objs.kids.append(newmap.object_node(m, pr, flags, template, x, y, angle=angle,
                                            uniqueID=f'{template} {len(objs.kids)}'))


c6.edit = generate

def game_running():
    import subprocess
    out = subprocess.run(['tasklist'], capture_output=True, text=True, errors='replace').stdout.lower()
    return 'ra3_1.' in out or 'ra3.exe' in out


if __name__ == '__main__':
    if game_running():      # never write into the Mods folder while the user plays: stage it, move it later
        c2.OUT = c4.OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'work', 'staging', NAME)
        print('RA3 is running -> staging at', c4.OUT)
    c4.main()
