"""Rigged, animated unit of ours on a choosable retail logic (CampNew21) -- the CampNew19 follow-up.

  CNV_TANK_BASE=AlliedAntiInfantryVehicle python -I -X utf8 experimental/campaign/make_campnew21.py
      -> Documents\\Red Alert 3\\Mods\\CampNew21

CampNew19 (our tank model on the Guardian's XML) crashes at mission load whenever the Guardian's draw references
an animation of ours -- heap corruption (crash inside the allocator, RA3_1.13.game+0x607873), with any of our
animations and even with CampNew17's saucer model, while the same saucer + spin animation on the hydrofoil's XML
runs and visibly spins. So the hierarchy here is built from whatever bones the chosen base XML names
(TurretNameKey / TurretPitch / BoneName / ExtraPublicBone / track bones), hull / turret / barrel / radar meshes
go on the matching bones, every AnimationName becomes our radar spin and the default state plays it.
"""
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew18 as c18                    # noqa: E402
import newmap                                   # noqa: E402
import w3x                                      # noqa: E402

c7, c6, c4, c2 = c18.c7, c18.c6, c18.c4, c18.c2
NAME = 'CampNew21'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
BASE = os.environ.get('CNV_TANK_BASE', 'AlliedAntiInfantryVehicle')
UNIT, MODEL, ANIM = 'CNV_Tank2', 'CNTank2', 'CNTank2_SPIN'
UNIT_FILE = os.path.join(c2.SDK, 'Mods', 'CNVUnits', 'Data', UNIT + '.xml')
c7.EXTRA_TEMPLATES[UNIT] = {'file': 'DATA:CNVUnits/Data/' + UNIT + '.xml', 'EditorSorting': 'UNIT'}
c4.c3.STRINGS['Name:' + UNIT] = 'CNV 坦克'
TANK_AT = (c18.START[0] + 120, c18.START[1] + 230)
ENEMY_AT = (TANK_AT[0], TANK_AT[1] + 230)


def base_xml():
    root = os.path.join(c2.SDK, 'SageXML')
    for d, _, fs in os.walk(root):
        for fn in fs:
            if fn.lower() == BASE.lower() + '.xml':
                return open(os.path.join(d, fn), encoding='utf-8').read()
    raise FileNotFoundError(BASE)


def bones_of(x):
    turret = re.search(r'TurretNameKey="([^"]+)"', x)
    pitch = re.search(r'TurretPitch="([^"]+)"', x)
    names = set()
    for v in re.findall(r'(?:BoneName|ExtraPublicBone|LeftTrack|RightTrack|\w+TireBone|TrackMarks\w+Bone)="([^"]+)"', x):
        names.update(v.split())
    names -= {'NONE', 'None', 'none'}
    return (turret.group(1) if turret else None), (pitch.group(1) if pitch else None), sorted(names, key=str.lower)


def rig(x):
    """(pivots, parts, radar index) for the base XML's bone names."""
    turret, pitch, others = bones_of(x)
    pivots = []

    def add(name, parent, at):
        pivots.append((name, parent, at))
        return len(pivots)              # index (ROOTTRANSFORM is 0)
    # the hull gets a bone of its own: every crashing build had a rigid mesh on ROOTTRANSFORM (bone 0), the
    # working saucer's mesh sits on bone 1 and EA puts only skinned meshes on the root
    body = add('BODY', 0, (0.0, 0.0, 0.0)) if os.environ.get('CNV_HULL_ON_ROOT') != '1' else 0
    t = add(turret or 'TURRET', 0, (0.0, 0.0, 9.0))
    p = add(pitch, t, (2.0, 0.0, 3.0)) if pitch else t
    for n in others:
        if n.upper() in {(turret or '').upper(), (pitch or '').upper()}:
            continue
        low = n.lower()
        if any(k in low for k in ('weapon', 'muzzle', 'gun', 'laser')):
            add(n, p, (21.0, 0.0, 0.0))
        else:
            add(n, 0, (0.0, 0.0, 4.0))
    radar = add('RADAR', t, (-5.0, 3.5, 6.0))
    hull = w3x.merge(w3x.box(-15, -8.5, 2, 15, 8.5, 9, top_shrink=2.0, uv=(0, 0.5, 1, 1)),
                     w3x.box(-16, 8.5, 0, 16, 12, 6, uv=(0, 0, 1, 0.25)),
                     w3x.box(-16, -12, 0, 16, -8.5, 6, uv=(0, 0, 1, 0.25)))
    turret_g = w3x.box(-7, -6.5, 0, 7, 6.5, 6, top_shrink=1.5, uv=(0, 0.25, 1, 0.5))
    barrel = w3x.merge(w3x.box(0, -1.0, -1.0, 21, 1.0, 1.0, uv=(0, 0.25, 1, 0.3)),
                       w3x.box(17, -1.6, -1.6, 21, 1.6, 1.6, uv=(0, 0.25, 1, 0.3)))
    radar_g = w3x.merge(w3x.box(-0.4, -0.4, 0, 0.4, 0.4, 3, uv=(0, 0, 0.1, 0.1)),
                        w3x.box(-0.6, -4.5, 3, 0.6, 4.5, 6, uv=(0, 0.25, 1, 0.3)))
    parts = [('HULL', body, hull), ('TURRETMESH', t, turret_g), ('BARREL', p, barrel), ('RADARMESH', radar, radar_g)]
    if os.environ.get('CNV_RIG_MIN') == '1':        # bisect: the saucer's structure (one mesh on bone 1)
        if os.environ.get('CNV_RIG_LATHE') == '1':  # ... and the saucer's geometry, under our names / textures
            import make_campnew17
            hull = w3x.lathe(make_campnew17.PROFILE, segments=40)
        return [('BODY', 0, (0.0, 0.0, 0.0))], [('HULL', 1, hull)], 1
    return pivots, parts, radar


def unit_xml(x):
    # keep only the base GameObject: amphibious units define _Ground / _Naval variants inheriting from it in
    # the same file, which would then inherit from an id that no longer exists (BAB stops)
    for m in reversed(list(re.finditer(r'\s*<GameObject\b.*?</GameObject>', x, re.S))):
        if f'id="{BASE}"' not in m.group(0)[:200]:
            x = x[:m.start()] + x[m.end():]
    x = x.replace(f'id="{BASE}"', f'id="{UNIT}"', 1).replace(f'EditorName="{BASE}"', f'EditorName="{UNIT}"')
    x = re.sub(r'(<Model\s+Name=")[^"]*(")', lambda m: m.group(1) + MODEL.upper() + m.group(2), x)
    x = re.sub(r'AnimationName="[^"]*"', f'AnimationName="{ANIM.upper()}"', x)
    x = re.sub(r'\s*<TreadScrollingMap\b[^>]*/>', '', x)
    play = f'\n\t\t\t\t\t<Animation AnimationName="{ANIM.upper()}" AnimationMode="LOOP" />'
    if os.environ.get('CNV_NO_ANIM') == '1':        # bisect baseline: the same unit with no animation played
        play = ''
    m = re.search(r'<AnimationState\b[^>]*"PARSE_DEFAULT"[^>]*>', x)
    if m:
        x = x[:m.end()] + play + x[m.end():]
    else:                               # no default state: add one at the end of the first draw module
        m = re.search(r'</(TruckDraw|ScriptedModelDraw|TankDraw)>', x)
        x = x[:m.start()] + f'\t<AnimationState ParseCondStateType="PARSE_DEFAULT">{play}\n\t\t\t\t</AnimationState>\n\t\t\t' + x[m.start():]
    x = x.replace('<Includes>', f'<Includes>\n\t\t<Include type="all" source="ART:{MODEL}.w3x" />'
                                f'\n\t\t<Include type="all" source="ART:{ANIM}.w3x" />', 1)
    x = re.sub(r'(<DisplayName[^>]*>)[^<]*(</DisplayName>)', lambda mm: mm.group(1) + f'Name:{UNIT}' + mm.group(2), x, 1)
    os.makedirs(os.path.dirname(UNIT_FILE), exist_ok=True)
    with open(UNIT_FILE, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(x.replace('\r\n', '\n'))


def textures():
    size = 256

    def diffuse(x, y):
        v = y / size
        if v < 0.25:
            return (40, 40, 42, 255) if (x // 8) % 2 else (60, 60, 62, 255)
        panel = x % 64 < 2 or y % 32 < 2
        base = (115, 125, 120) if v < 0.5 else (135, 145, 140)
        return tuple(c - 35 for c in base) + (255,) if panel else base + (255,)
    w3x.write_texture(MODEL, size, size, diffuse)
    w3x.write_texture(MODEL + '_NRM', 16, 16, lambda x, y: (128, 128, 255, 255))
    w3x.write_texture(MODEL + '_SPM', size, size, lambda x, y: (90, 0, 255 if 0.62 < y / size < 0.72 else 0, 255))


_generate = c6.edit


def generate(m):
    _generate(m)
    global MODEL, ANIM
    x = base_xml()
    if os.environ.get('CNV_USE_SAUCER') == '1':     # bisect: CampNew17's saucer + spin as they are (they work there)
        MODEL, ANIM = 'CNSaucer', 'CNSaucer_SPIN'
        unit_xml(x)
    else:
        pivots, parts, radar = rig(x)
        textures()
        w3x.write_model(MODEL, w3x.rig_model(MODEL, pivots, parts, (MODEL, MODEL + '_NRM', MODEL + '_SPM')))
        spin = int(os.environ.get('CNV_SPIN_PIVOT', radar))     # bisect: which pivot turns
        frames = int(os.environ.get('CNV_SPIN_FRAMES', '90'))  # bisect: 60 and 1 crashed, the saucer's 90 runs
        w3x.write_model(ANIM, w3x.spin_animation(ANIM, MODEL, spin, frames=frames))
        unit_xml(x)
    print(f'{UNIT} on {BASE}, model {MODEL}, animation {ANIM}')
    objs = next(n for _, n in m.walk() if n.name == 'ObjectsList')
    p1 = next(k for k in objs.kids if b'AlliedAntiVehicleVehicleTech1' in k.head[:60])
    s1 = next(k for k in objs.kids if b'SovietAntiVehicleVehicleTech1' in k.head[:60])
    for src, template, (px, py), angle in ((p1, UNIT, TANK_AT, 0.0),
                                           (s1, 'SovietAntiVehicleVehicleTech1', ENEMY_AT, -math.pi / 2)):
        pr, flags = newmap.typed_props_of(m, src)
        objs.kids.append(newmap.object_node(m, pr, flags, template, px, py, angle=angle,
                                            uniqueID=f'{template} {len(objs.kids)}'))


c6.edit = generate

if __name__ == '__main__':
    c4.main()
