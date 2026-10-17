"""Animation control probe (CampNew20): CampNew16's SDK gunship with an EA-made SDK animation (AUGUNSHIP_DEPLOY,
100 frames) looping in its default animation state.

  python -I -X utf8 experimental/campaign/make_campnew20.py   -> Documents\\Red Alert 3\\Mods\\CampNew20

CampNew19 crashes as soon as the tank's default state plays our animation (even a one-frame one); without it the
tank loads. If this EA-authored, SDK-compiled animation crashes the same way, the fault is in how SDK animations
reach the game (compile / link), not in the W3X our w3x.py writes.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew16 as c16                    # noqa: E402

c7, c6, c4, c2 = c16.c7, c16.c6, c16.c4, c16.c2
NAME = 'CampNew20'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
ANIM = os.environ.get('CNV_GUNSHIP_ANIM', 'AUGunship_DEPLOY')
COPY = os.path.join(c2.SDK, 'Mods', 'CNVUnits', 'Data', 'AlliedGunshipAircraft_Anim.xml')

_wrapper = c16.wrapper


def wrapper():
    src = open(os.path.join(c2.SDK, 'Mods', 'SampleMod', 'data', 'AlliedGunshipAircraft.xml'), encoding='utf-8-sig').read()
    x = src.replace('<Includes>', f'<Includes>\n\t\t<Include type="all" source="ART:{ANIM}.w3x" />', 1)
    x, n = re.subn(r'(</ScriptedModelDraw>)', f'\t<AnimationState ParseCondStateType="PARSE_DEFAULT">\n'
                   f'\t\t\t\t\t<Animation AnimationName="{ANIM.upper()}" AnimationMode="LOOP" />\n'
                   f'\t\t\t\t</AnimationState>\n\t\t\t\\1', x, count=1)
    assert n == 1
    with open(COPY, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(x.replace('\r\n', '\n'))
    k = _wrapper()
    w = open(c16.WRAPPER, encoding='utf-8').read().replace('DATA:SampleMod/Data/AlliedGunshipAircraft.xml',
                                                           'DATA:CNVUnits/Data/AlliedGunshipAircraft_Anim.xml')
    with open(c16.WRAPPER, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(w.replace('\r\n', '\n'))
    return k


c16.wrapper = wrapper

if __name__ == '__main__':
    c4.main()
