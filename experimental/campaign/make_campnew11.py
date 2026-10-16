"""Lighting probe (CampNew11): CampNew7 with the map's GlobalLighting tinted warm, nothing else changed.

  python -I -X utf8 experimental/campaign/make_campnew11.py   -> Documents\\Red Alert 3\\Mods\\CampNew11

Prompted by the Remix mod's brighter maps (B站 BV1LJ4m1g7nT): if this .map chunk drives the in-game light, map
lighting is something our own tools can retune per mission. GlobalLighting v11 (Heidelberg: 452 bytes) = u32 time
of day, then lights of 9 floats (ambient rgb, color rgb, direction xyz) in blocks of six (terrain sun / accent 1 /
accent 2, object sun / accent 1 / accent 2), plus 4 trailing floats. Every light colour is scaled by TINT; a bench
frame next to CampNew7's at the same second shows whether it took effect.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew7 as c7                      # noqa: E402

c6, c4, c2 = c7.c6, c7.c4, c7.c2
NAME = 'CampNew11'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
TINT = (1.35, 1.1, 0.8)

_edit = c6.edit


def edit(m):
    _edit(m)
    node = next(n for _, n in m.walk() if n.name == 'GlobalLighting')
    d = bytearray(node.head)
    lights = (len(d) - 4 - 16) // 36
    for k in range(lights):
        at = 4 + 36 * k + 12            # the colour triple of light k
        rgb = struct.unpack_from('<3f', d, at)
        struct.pack_into('<3f', d, at, *(c * t for c, t in zip(rgb, TINT)))
    node.head = bytes(d)
    print('GlobalLighting:', lights, 'light colours scaled by', TINT)


c6.edit = edit

if __name__ == '__main__':
    c4.main()
