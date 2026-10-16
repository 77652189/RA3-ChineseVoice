"""CampNew4 + a script edit made with our own tool (mapscript.py): the opening video call of the new mission is the
Soviet S01TH01 instead of Heidelberg's A03TH03.

  python -I -X utf8 experimental/campaign/make_campnew5.py   -> Documents\\Red Alert 3\\Mods\\CampNew5

If the bench run shows the Soviet call (and its subtitle) where Eva's A03TH03 played before, maps written by
mapscript.py load and their script changes take effect -- the base for our own editor.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew4 as c4                      # noqa: E402
from mapscript import MapFile                   # noqa: E402

NAME = 'CampNew5'
c4.NAME = c4.c2.NAME = NAME
c4.c2.SRC_DIR = os.path.join(c4.c2.SDK, 'Mods', NAME, 'data')
c4.c2.BUILT = os.path.join(c4.c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c4.c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
EDITS = [('MOVIE_PLAY_RADAR', 'A03TH03', 'S01TH01'), ('HAS_FINISHED_VIDEO', 'A03TH03', 'S01TH01')]
# isolating the load hang of the first run (stuck at ~60 % for minutes):
#   CNV_EDITS=0      write the map back through mapscript.py unchanged (is it our writer?)
#   CNV_CACHE_CRC=0  register the map with CRC 0, as Arsenal does (is it the cache CRC no longer matching?)
if os.environ.get('CNV_EDITS') == '0':
    EDITS = []
if os.environ.get('CNV_CACHE_CRC') == '0':
    _entry = c4.cache_entry
    c4.cache_entry = lambda: dict(_entry(), crc=0)

_map_files = c4.c2.map_files


def edited_map_files():
    out = []
    for path, data in _map_files():
        if path.lower().endswith('.map'):
            m = MapFile(data)
            for content, old, new in EDITS:
                print(f'edit {content}: {old} -> {new}: {m.set_string_args(content, old, new)} changed')
            data = m.map_file()
            assert MapFile(data).chunk_file() == m.chunk_file()
        out.append((path, data))
    return out


c4.c2.map_files = edited_map_files

if __name__ == '__main__':
    c4.main()
