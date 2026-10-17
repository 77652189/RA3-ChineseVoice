"""游隼 battle test (CampNew28): two 游隼 and a Cryocopter against three Soviet Hammer tanks, driven from the test
bench (run_bench.ps1 -Actions: box select, toggle 规避近战, move away, order the Cryocopter to freeze).

On CampNew27's 游隼 (gameplay, evade-melee toggle): CampNew25's v1, every Soviet tank and CampNew27's ore collectors
are left out; the Hammers stand ~610 north at the top of the bench view, the two 游隼 and the Cryocopter at the bottom;
the bench orders evade on, an advance to evade range, the freeze, and a pull-back.

  python -I -X utf8 experimental/campaign/make_campnew28.py   -> Documents\\Red Alert 3\\Mods\\CampNew28
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew27 as c27                    # noqa: E402

c26, c23 = c27.c26, c27.c23
c7, c6, c4, c2 = c23.c7, c23.c6, c23.c4, c23.c2
newmap = c23.newmap
NAME = 'CampNew28'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
# the bench camera sees ~1.1 px per unit; 游隼 at screen ~(560, 570), the Hammers 460 north at the top edge, so
# nothing meets before the bench can give orders (at 260 apart the fight started during the intro and the two
# 游隼 brawled in normal mode and lost)
G = c27.GROUP_A
A = (G[0] - 190, G[1] - 310)                     # first 游隼 (screen ~(560, 570); 460 south of the Hammers)
SECOND = (A[0] + 45, A[1])
CRYO = (A[0] - 70, A[1] - 10)
HAMMERS = [(A[0] + dx, A[1] + 460) for dx in (-60, 0, 60)]


def generate(m):
    c27._generate(m)                             # CampNew26 chain: factory, power plant, both tanks, unit XMLs
    objs = next(n for _, n in m.walk() if n.name == 'ObjectsList')
    head = lambda k: k.head[:60]                 # noqa: E731
    p1 = next(k for k in objs.kids if b'AlliedAntiVehicleVehicleTech1' in head(k))
    s1 = next(k for k in objs.kids if b'SovietAntiVehicleVehicleTech1' in head(k))
    objs.kids[:] = [k for k in objs.kids if b'SovietAntiVehicleVehicleTech1' not in head(k)
                    and not (b'CNV_LightTank' in head(k) and b'CNV_LightTank2' not in head(k))]
    objs.kids[:] = [k for k in objs.kids if b'CNV_LightTank2' not in head(k)]       # re-placed at A below
    for src, template, (x, y), angle in ([(p1, c26.UNIT, at, math.pi / 2) for at in (A, SECOND)] +
                                         [(p1, 'AlliedSupportAircraft', CRYO, 0.0)]
                                         + [(s1, 'SovietAntiVehicleVehicleTech1', at, -math.pi / 2) for at in HAMMERS]):
        pr, flags = newmap.typed_props_of(m, src)
        objs.kids.append(newmap.object_node(m, pr, flags, template, x, y, angle=angle,
                                            uniqueID=f'{template} {len(objs.kids)}'))


c6.edit = generate

if __name__ == '__main__':
    if c23.game_running():
        c2.OUT = c4.OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'work', 'staging', NAME)
        print('RA3 is running -> staging at', c4.OUT)
    c4.main()
