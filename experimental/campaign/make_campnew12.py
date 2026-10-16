"""Do SDK-compiled GameObjects work in game 1.12/1.13? (CampNew12)

  python -I -X utf8 experimental/campaign/make_campnew12.py   -> Documents\\Red Alert 3\\Mods\\CampNew12

CampNew7 links the retail 1.12 GameObjects because BAB's carry another type hash (SDK 3621320486, static.12
3415017856), inferred to be an older layout but never tried. Corona runs on 1.12 with many new units, so this
probe is CampNew7 with every GameObject BAB compiled for the map (168, the props and campaign units) taken from
BAB instead. A "Type hash mismatch" box or crash -> the inference holds for this SDK; a normal mission -> SDK
GameObjects are fine and new units can be compiled.

Result (bench, 2026-10-16): a normal mission (bridge, props, MCVs, hydrofoils, our caption, the Twinblade hint),
no type hash box. First run had invisible props: BAB refers to models by the generic BaseRenderAssetType
(b22f87c9); mapxml.link now retypes those to the W3DContainer of that name.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew7 as c7                      # noqa: E402

c4, c2 = c7.c4, c7.c2
NAME = 'CampNew12'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
c7.SDK_OBJECTS = True

if __name__ == '__main__':
    c4.main()
