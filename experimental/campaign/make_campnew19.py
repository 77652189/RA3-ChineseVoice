"""A rigged, animated unit of our own (CampNew19): CampNew18's generated island plus CNV_Tank, the Guardian tank's
logic on a model built here -- hull, turret, barrel and a radar dish on their own bones (Bone_Turret,
Bone_Turret_Pitch, BONE_GUN_MUZZLE / FXBone_Muzzle ... named as the Guardian's XML expects), plus a looping
keyframe animation of ours that spins the radar.

  python -I -X utf8 experimental/campaign/make_campnew19.py   -> Documents\\Red Alert 3\\Mods\\CampNew19

Test scene: the tank faces east, a Soviet Hammer tank waits due north of it. Turret turned north while the hull
points east = the game drives our bones; the radar at a different angle between two frames = our animation runs.
"""
import math
import re
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew18 as c18                    # noqa: E402
import newmap                                   # noqa: E402
import w3x                                      # noqa: E402

c7, c6, c4, c2 = c18.c7, c18.c6, c18.c4, c18.c2
NAME = 'CampNew19'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
UNIT, MODEL, ANIM = 'CNV_Tank', 'CNTank', 'CNTank_SPIN'
if os.environ.get('CNV_TANK_MODEL') == 'saucer':        # bisect: the Guardian's logic on CampNew17's saucer + spin
    MODEL, ANIM = 'CNSaucer', 'CNSaucer_SPIN'
UNIT_FILE = os.path.join(c2.SDK, 'Mods', 'CNVUnits', 'Data', UNIT + '.xml')
c7.EXTRA_TEMPLATES[UNIT] = {'file': 'DATA:CNVUnits/Data/' + UNIT + '.xml', 'EditorSorting': 'UNIT'}
c4.c3.STRINGS['Name:' + UNIT] = 'CNV 坦克'
TANK_AT = (c18.START[0] + 120, c18.START[1] + 230)     # in the opening camera view
ENEMY_AT = (TANK_AT[0], TANK_AT[1] + 230)

# pivots after ROOTTRANSFORM (index 0): name, parent, offset from the parent
PIVOTS = [('Bone_Turret', 0, (0.0, 0.0, 9.0)),            # 1
          ('Bone_Turret_Pitch', 1, (2.0, 0.0, 3.0)),      # 2
          ('BONE_GUN_MUZZLE', 2, (21.0, 0.0, 0.0)),       # 3
          ('FXBone_Muzzle', 2, (22.0, 0.0, 0.0)),         # 4
          ('FX_Laser', 1, (4.0, 0.0, 5.0)),               # 5
          ('FX_Damage01', 0, (-6.0, 0.0, 9.0)),           # 6
          ('FXTracksL', 0, (-14.0, 10.5, 0.0)),           # 7
          ('FXTracksR', 0, (-14.0, -10.5, 0.0)),          # 8
          ('Bone_Tread_Front_Left', 0, (8.0, 10.5, 3.0)), ('Bone_Tread_Front_Right', 0, (8.0, -10.5, 3.0)),
          ('Bone_Tread_Rear_Left', 0, (-8.0, 10.5, 3.0)), ('Bone_Tread_Rear_Right', 0, (-8.0, -10.5, 3.0)),
          ('Bone_Tracks_Front_Left', 0, (8.0, 10.5, 3.0)), ('Bone_Tracks_Front_Right', 0, (8.0, -10.5, 3.0)),
          ('Bone_Tracks_Rear_Left', 0, (-8.0, 10.5, 3.0)), ('Bone_Tracks_Rear_Right', 0, (-8.0, -10.5, 3.0)),
          ('RADAR', 1, (-5.0, 3.5, 6.0))]                 # 17
RADAR = 17


def geometry():
    hull = w3x.merge(w3x.box(-15, -8.5, 2, 15, 8.5, 9, top_shrink=2.0, uv=(0, 0.5, 1, 1)),
                     w3x.box(-16, 8.5, 0, 16, 12, 6, uv=(0, 0, 1, 0.25)),            # tracks
                     w3x.box(-16, -12, 0, 16, -8.5, 6, uv=(0, 0, 1, 0.25)))
    turret = w3x.box(-7, -6.5, 0, 7, 6.5, 6, top_shrink=1.5, uv=(0, 0.25, 1, 0.5))
    barrel = w3x.merge(w3x.box(0, -1.0, -1.0, 21, 1.0, 1.0, uv=(0, 0.25, 1, 0.3)),
                       w3x.box(17, -1.6, -1.6, 21, 1.6, 1.6, uv=(0, 0.25, 1, 0.3)))
    radar = w3x.merge(w3x.box(-0.4, -0.4, 0, 0.4, 0.4, 3, uv=(0, 0, 0.1, 0.1)),        # mast
                      w3x.box(-0.6, -4.5, 3, 0.6, 4.5, 6, uv=(0, 0.25, 1, 0.3)))     # dish plate
    return [('HULL', 0, hull), ('TURRET', 1, turret), ('BARREL', 2, barrel), ('RADAR', RADAR, radar)]


def textures():
    size = 256

    def diffuse(x, y):
        v = y / size
        if v < 0.25:                                                     # tracks
            return (40, 40, 42, 255) if (x // 8) % 2 else (60, 60, 62, 255)
        panel = x % 64 < 2 or y % 32 < 2
        base = (115, 125, 120) if v < 0.5 else (135, 145, 140)
        return tuple(c - 35 for c in base) + (255,) if panel else base + (255,)

    def spec(x, y):
        v = y / size
        team = 255 if 0.62 < v < 0.72 else 0                               # team-colour stripe on the hull
        return 90, 0, team, 255

    w3x.write_texture(MODEL, size, size, diffuse)
    w3x.write_texture(MODEL + '_NRM', 16, 16, lambda x, y: (128, 128, 255, 255))
    w3x.write_texture(MODEL + '_SPM', size, size, spec)


def unit_xml():
    src = open(os.path.join(c2.SDK, 'SageXML', 'Allied', 'Units', 'AlliedAntiVehicleVehicleTech1.xml'),
               encoding='utf-8').read()
    x = src.replace('id="AlliedAntiVehicleVehicleTech1"', f'id="{UNIT}"')
    x = x.replace('EditorName="AlliedAntiVehicleVehicleTech1"', f'EditorName="{UNIT}"')
    # bisect switches: CNV_TANK_MODEL=retail keeps the Guardian's model, CNV_TANK_ANIM=0 its animations
    if os.environ.get('CNV_TANK_MODEL') != 'retail':
        x = x.replace('Name="AUAntiVehicleVehicleTech1_SKN"', f'Name="{MODEL.upper()}"')
    which = os.environ.get('CNV_TANK_ANIM', 'both')      # bisect: 0 / default / moving / both
    anim = which in ('both', 'default')
    if which in ('both', 'moving'):
        # every animation of the draw must belong to our hierarchy: a Guardian animation left in one state next
        # to ours crashed the mission at load (CampNew19 bisect, 2026-10-16)
        x = re.sub(r'AnimationName="[^"]*"', f'AnimationName="{ANIM.upper()}"', x)
    x = x if not anim else x.replace('''<AnimationState
					ParseCondStateType="PARSE_DEFAULT">
				</AnimationState>''', f'''<AnimationState
					ParseCondStateType="PARSE_DEFAULT">
					<Animation AnimationName="{ANIM.upper()}" AnimationMode="LOOP" />
				</AnimationState>''')
    assert not anim or f'AnimationName="{ANIM.upper()}" AnimationMode="LOOP" />' in x, 'default animation state'
    x = x.replace('>Name:AlliedAntiVehicleVehicleTech1<', f'>Name:{UNIT}<')
    # tread scrolling needs tread *meshes* named Bone_Tread_*; with bones only the mission crashed while loading
    # (0xc0000005 at RA3_1.13.game+0xcee55, first CampNew19 run)
    x, n = re.subn(r'\s*<TreadScrollingMap\b[^>]*/>', '', x)
    assert n == 2, n
    # with TruckDraw any animation of ours crashed the mission at load (even a still one-frame one); the same
    # animation runs on a ScriptedModelDraw (CampNew17 saucer, CNV_SAUCER_SPIN=1), so the tank draws with that
    strip = os.environ.get('CNV_TANK_STRIP', 'laser,texture,recoil').split(',')     # bisect
    if 'laser' in strip:
        x, n = re.subn(r'\s*<LaserDraw\b.*?</LaserDraw>', '', x, flags=re.S)
        assert n == 1, n
    if 'texture' in strip:
        x = re.sub(r'\s*<Texture\s+Original="[^"]*"\s+New="[^"]*"\s*/>', '', x)
    if 'recoil' in strip:
        x = re.sub(r'\s*<WeaponRecoilBone\b[^>]*/>', '', x)
    if os.environ.get('CNV_TANK_DRAW') != 'truck':
        x = x.replace('<TruckDraw', '<ScriptedModelDraw').replace('</TruckDraw>', '</ScriptedModelDraw>')
        x = re.sub(r'\s(?:Left|Right)(?:Front|Rear)TireBone="[^"]*"|\sTireRotationMultiplier="[^"]*"'
                   r'|\sTrackMarks\w*="[^"]*"', '', x)
        x = re.sub(r'\s*<TreadTerrainParticles>[^<]*</TreadTerrainParticles>', '', x)
    x = x.replace('<Includes>', f'<Includes>\n\t\t<Include type="all" source="ART:{MODEL}.w3x" />'
                                f'\n\t\t<Include type="all" source="ART:{ANIM}.w3x" />', 1)
    os.makedirs(os.path.dirname(UNIT_FILE), exist_ok=True)
    with open(UNIT_FILE, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(x.replace('\r\n', '\n'))


_generate = c6.edit


def generate(m):
    _generate(m)
    if MODEL == 'CNTank':           # (the saucer bisect uses CampNew17's files as they are)
        textures()
        w3x.write_model(MODEL, w3x.rig_model(MODEL, PIVOTS, geometry(), (MODEL, MODEL + '_NRM', MODEL + '_SPM')))
        frames = int(os.environ.get('CNV_SPIN_FRAMES', '60'))      # bisect: 1 = a still one-frame animation
        pivot = int(os.environ.get('CNV_SPIN_PIVOT', RADAR))       # bisect: which pivot the animation turns
        still = [int(s) for s in os.environ.get('CNV_SPIN_STILL', '').split(',') if s]   # bisect: identity channels
        w3x.write_model(ANIM, w3x.spin_animation(ANIM, MODEL, pivot, frames=frames,
                                                 turns=1.0 if frames > 1 else 0.0, still=still))
    unit_xml()
    objs = next(n for _, n in m.walk() if n.name == 'ObjectsList')
    p1 = next(k for k in objs.kids if b'AlliedAntiVehicleVehicleTech1' in k.head[:60])
    s1 = next(k for k in objs.kids if b'SovietAntiVehicleVehicleTech1' in k.head[:60])
    placed = [(p1, UNIT, TANK_AT, 0.0), (s1, 'SovietAntiVehicleVehicleTech1', ENEMY_AT, -math.pi / 2)]
    if os.environ.get('CNV_NO_ENEMY') == '1':           # bisect: no fight next to the tank
        placed = placed[:1]
    for src, template, (x, y), angle in placed:
        pr, flags = newmap.typed_props_of(m, src)
        objs.kids.append(newmap.object_node(m, pr, flags, template, x, y, angle=angle,
                                            uniqueID=f'{template} {len(objs.kids)}'))
    print(f'{UNIT} at {TANK_AT} facing east, enemy at {ENEMY_AT}')


c6.edit = generate

if __name__ == '__main__':
    c4.main()
