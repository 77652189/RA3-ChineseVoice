"""Minimal complete new mission, built from the parts that work (CampNew4).

  python -I -X utf8 experimental/campaign/make_campnew4.py   -> Documents\\Red Alert 3\\Mods\\CampNew4

  - campaign: static-stream splice (make_campnew2: Allies_New + Allies campaign of 10, all LOD top streams)
  - map: renamed bare .map + pictures in data\\maps\\official\\camp_cnv01_probe\\
  - map cache: the retail data\\mapmetadata stream with an entry for that map appended (mapcache.py; the crash on
    load in CampNew2 was the map missing from the cache). Not official (flags 0), so the game reads the .map at
    run time like a user map instead of looking for precompiled map streams.
  - strings: gamestrings.csf = installed CNVoice table + the new labels (mod.str shows Chinese as Latin-1)
"""
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew2 as c2                          # noqa: E402
import make_campnew3 as c3                          # noqa: E402
import mapcache                                     # noqa: E402
import splice_assets                                # noqa: E402
from ra3voice import big                            # noqa: E402

NAME = 'CampNew4'
c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
NEW_MAP = c2.NEW_DIR + c2.NEW_STEM + '.map'
# bare .map (first run, 2026-10-16 03:20): loads and plays, but the terrain is black and the city props are gone,
# they live in the map's compiled streams; so ship those too (CampNew2 crashed with them because the cache entry
# was missing, not because of the streams). CNV_MAP_STREAMS=0 goes back to the bare map.
c2.SHIP_STREAMS = os.environ.get('CNV_MAP_STREAMS', '1') != '0'
assert c3.STRINGS and NEW_MAP == c3.NEW_DIR + c3.NEW_STEM + '.map'


def cache_entry():
    base = next(m for m in mapcache.decode(mapcache.retail()[1][1][4:]) if 'camp_a03_heidelberg' in m['file'].lower())
    m = dict(base)
    m.update(file=NEW_MAP, id=zlib.crc32(NEW_MAP.lower().encode()), flags=0)
    return m


def main():
    c2.sources()
    c2.compile_mod()
    files = splice_assets.spliced_files(c2.BUILT)
    entry = cache_entry()
    print('map cache entry:', {k: v for k, v in entry.items() if k != 'starts'}, len(entry['starts']), 'starts')
    files += mapcache.with_maps([entry]) + c2.map_files() + c3.strings()
    os.makedirs(OUT, exist_ok=True)
    big.write(os.path.join(OUT, f'{NAME}.big'), files)
    with open(os.path.join(OUT, f'{NAME}_1.0.skudef'), 'w', encoding='ascii', newline='') as f:
        f.write(f'mod-game 1.12\r\nadd-big {NAME}.big\r\n')
    print('->', OUT, [n.split('\\')[-1] for n, _ in files if 'static' not in n])


if __name__ == '__main__':
    main()
