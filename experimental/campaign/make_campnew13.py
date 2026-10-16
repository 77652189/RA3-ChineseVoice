"""New unit + new map object (CampNew13): CampNew7 with a GameObject of our own placed in the map.

  python -I -X utf8 experimental/campaign/make_campnew13.py   -> Documents\\Red Alert 3\\Mods\\CampNew13

CNV_TestShip = the hydrofoil (SageXML AlliedAntiAirShip.xml) with its own id, the aircraft carrier's model
(AUAntiStructureShip_SKN, so it is unmistakable on a bench frame), ten times the health and a Chinese name. It is
placed with mapxml.place_object next to 'UNIT - Hydrofoil 01' (copying owner, team and flags) as
'UNIT - CNV Test Ship', and mapscript.duplicate_contents gives it every action the hydrofoil gets (follow the
intro path, hand over to Player_1, ...), so it should sail in with the convoy. BAB compiles the template (SDK
GameObjects work, CampNew12); the linker takes it from BAB's output since no retail stream has it.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew7 as c7                      # noqa: E402
import mapxml                                   # noqa: E402

c6, c4, c2 = c7.c6, c7.c4, c7.c2
NAME = 'CampNew13'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
UNIT, UNIT_NAME, LIKE = 'CNV_TestShip', 'UNIT - CNV Test Ship', 'UNIT - Hydrofoil 01'
UNIT_FILE = os.path.join(c2.SDK, 'Mods', 'CNVUnits', 'Data', UNIT + '.xml')
c7.EXTRA_TEMPLATES[UNIT] = {'file': 'DATA:CNVUnits/Data/' + UNIT + '.xml', 'EditorSorting': 'UNIT'}
c4.c3.STRINGS['Name:' + UNIT] = 'CNV 测试舰'


def unit_xml():
    src = open(os.path.join(c2.SDK, 'SageXML', 'Allied', 'Units', 'AlliedAntiAirShip.xml'), encoding='utf-8').read()
    x = src.replace('id="AlliedAntiAirShip"', f'id="{UNIT}"').replace('EditorName="AlliedAntiAirShip"',
                                                                      f'EditorName="{UNIT}"')
    x = x.replace('Name="AUAntiAirShip_SKN"', 'Name="AUAntiStructureShip_SKN"')
    x = x.replace('>Name:AlliedAntiAirShip<', f'>Name:{UNIT}<')
    x, n = re.subn(r'MaxHealth="400"', 'MaxHealth="4000"', x)
    assert n == 1 and x.count(f'id="{UNIT}"') == 1, n
    os.makedirs(os.path.dirname(UNIT_FILE), exist_ok=True)
    with open(UNIT_FILE, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(x.replace('\r\n', '\n'))


_edit = c6.edit


def edit(m):
    _edit(m)
    unit_xml()
    hydro = next(o for o in mapxml.objects(m) if o['props'].get('objectName') == LIKE)
    mapxml.place_object(m, LIKE, UNIT, hydro['x'] + 60, hydro['y'] - 60, name=UNIT_NAME)
    print(f'placed {UNIT} as {UNIT_NAME!r}; actions copied from {LIKE!r}:', m.duplicate_contents(LIKE, UNIT_NAME))


c6.edit = edit

if __name__ == '__main__':
    c4.main()
