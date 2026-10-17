"""Ground textures outside the base map's set (CampNew22): CampNew18's generated island with its grass replaced by
snow textures Heidelberg never had (Snow_Solvang01 / 02), appended to the map's texture list and compiled into
our own terrain atlas (SDK v3 ART:Terrain sources, mapxml.atlas_xml, CNV_OWN_ATLAS).

  python -I -X utf8 experimental/campaign/make_campnew22.py   -> Documents\\Red Alert 3\\Mods\\CampNew22

A snow-covered island on the bench = ground textures are free now: any of SDK v3's 744 terrain sources.
"""
import os
import sys

os.environ['CNV_OWN_ATLAS'] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew18 as c18                    # noqa: E402
import newmap                                   # noqa: E402

c7, c6, c4, c2 = c18.c7, c18.c6, c18.c4, c18.c2
NAME = 'CampNew22'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
SWAP = {'Grass_Heidelberg01': 'Snow_Solvang01', 'Grass_Heidelberg02': 'Snow_Solvang02'}

_texture_for = newmap.texture_for
newmap.texture_for = lambda *a: SWAP.get(_texture_for(*a), _texture_for(*a))
newmap.RANK[:] = [SWAP.get(t, t) for t in newmap.RANK]
newmap.COLORS.update({'Snow_Solvang01': (225, 230, 235), 'Snow_Solvang02': (210, 215, 225)})
_paint = newmap.paint_terrain


def paint_terrain(m, hm, tiles, *a, **k):
    for t in SWAP.values():
        tiles.add_texture(t)
    return _paint(m, hm, tiles, *a, **k)


newmap.paint_terrain = paint_terrain

if __name__ == '__main__':
    c4.main()
