"""Showcase (CampNew15): CampNew14 (new mission, own scripts, new unit, raised and painted island) with the crisp
lighting preset of make_lightmod on top -- everything the campaign tooling does, in one mod.

  python -I -X utf8 experimental/campaign/make_campnew15.py   -> Documents\\Red Alert 3\\Mods\\CampNew15
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew14 as c14                    # noqa: E402
import make_lightmod                            # noqa: E402

c7, c6, c4, c2 = c14.c7, c14.c6, c14.c4, c14.c2
NAME = 'CampNew15'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
PRESET = os.environ.get('CNV_LIGHT_PRESET', 'crisp')

_edit = c6.edit


def edit(m):
    _edit(m)
    print('lighting preset', PRESET, 'time of day', make_lightmod.relight(m, make_lightmod.PRESETS[PRESET]))


c6.edit = edit

if __name__ == '__main__':
    c4.main()
