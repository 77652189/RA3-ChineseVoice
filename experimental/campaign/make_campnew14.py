"""Terrain edit (CampNew14): CampNew13 plus an island raised out of the river next to the convoy's route.

  python -I -X utf8 experimental/campaign/make_campnew14.py   -> Documents\\Red Alert 3\\Mods\\CampNew14

mapterrain.HeightMap.raise_hill lifts the sea floor at ISLAND to TOP world units (water level 200), 150 units
east of the hydrofoils' last path waypoint (2906, 358), so the ships pass it without being blocked. A bench
frame with an island next to the convoy means terrain edits in the .map reach the game (and its pathing copes).

Result (bench, 2026-10-16): a sandy island (sea-floor texture) sits among the convoy, the ships stop around it.
A first try (radius 90, top 260, 250 units east) showed nothing in frame; this one is radius 200, top 350.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew13 as c13                    # noqa: E402
from mapterrain import HeightMap                # noqa: E402

c7, c6, c4, c2 = c13.c7, c13.c6, c13.c4, c13.c2
NAME = 'CampNew14'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
ISLAND, TOP, RADIUS = (3056.0, 358.0), 350.0, 200.0

_edit = c6.edit


def edit(m):
    _edit(m)
    hm = HeightMap(m)
    i, j = hm.cell(*ISLAND)
    print(f'island at {ISLAND} (cell {i},{j}, floor {hm.get(i, j):.0f}):', hm.raise_hill(*ISLAND, TOP, RADIUS),
          'cells raised')
    hm.store()


c6.edit = edit

if __name__ == '__main__':
    c4.main()
