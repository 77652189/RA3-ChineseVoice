"""A unit with all-new art (CampNew16): the SDK SampleMod's Harbinger gunship (AlliedGunshipAircraft, not in RA3:
own w3x model, skeleton, animations, collision boxes and textures under C:\\RA3ModSDK\\Art\\AU) in CampNew7's mission.

  python -I -X utf8 experimental/campaign/make_campnew16.py   -> Documents\\Red Alert 3\\Mods\\CampNew16

The gunship's XMLs (unit, dying / collapse objects, projectile, light, proton FX) are included through one wrapper
file; it is placed like 'UNIT - Hydrofoil 02' and gets that hydrofoil's script actions, so it should fly in with
the convoy. Seen on the bench = units with new models compile and run in 1.13; the next step is a model of ours.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew7 as c7                      # noqa: E402
import mapxml                                   # noqa: E402

c6, c4, c2 = c7.c6, c7.c4, c7.c2
NAME = 'CampNew16'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
UNIT, UNIT_NAME, LIKE = 'AlliedGunshipAircraft', 'UNIT - CNV Gunship', 'UNIT - Hydrofoil 02'
WRAPPER = os.path.join(c2.SDK, 'Mods', 'CNVUnits', 'Data', 'SampleGunship.xml')
c7.EXTRA_TEMPLATES[UNIT] = {'file': 'DATA:CNVUnits/Data/SampleGunship.xml', 'EditorSorting': 'UNIT'}


def wrapper():
    """SampleMod's mod.xml includes minus the reference ones and the barracks edit."""
    mod = open(os.path.join(c2.SDK, 'Mods', 'SampleMod', 'data', 'mod.xml'), encoding='utf-8-sig').read()
    inc = [s for s in re.findall(r'source="(DATA:SampleMod/Data/[^"]+)"', mod) if 'Barracks' not in s]
    os.makedirs(os.path.dirname(WRAPPER), exist_ok=True)
    with open(WRAPPER, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<AssetDeclaration xmlns="uri:ea.com:eala:asset">\n'
                '\t<Includes>\n' + ''.join(f'\t\t<Include type="all" source="{s}" />\n' for s in inc)
                + '\t</Includes>\n</AssetDeclaration>\n')
    return len(inc)


_edit = c6.edit


def edit(m):
    _edit(m)
    print('gunship wrapper includes', wrapper(), 'SampleMod files')
    like = next(o for o in mapxml.objects(m) if o['props'].get('objectName') == LIKE)
    mapxml.place_object(m, LIKE, UNIT, like['x'] - 60, like['y'] - 60, name=UNIT_NAME)
    print(f'placed {UNIT} as {UNIT_NAME!r}; actions copied from {LIKE!r}:', m.duplicate_contents(LIKE, UNIT_NAME))


c6.edit = edit

if __name__ == '__main__':
    c4.main()
