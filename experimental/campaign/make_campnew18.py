"""A map generated from scratch (CampNew18): Heidelberg's .map only as the container (dimensions 560 x 560, chunk
layout, its 34 ground textures / atlas, players and teams); terrain, water, textures, blends, passability,
objects, waypoints, scripts, objectives and time of day are all produced by newmap.py.

  python -I -X utf8 experimental/campaign/make_campnew18.py   -> Documents\\Red Alert 3\\Mods\\CampNew18

An island in open sea; the Allies (MCV + Guardian tanks + Riptides) start on its west end, Soviet Hammer tanks
wait on the east end; a caption names the map, one objective. Built through the CampNew7 pipeline (mission slot,
map cache, linked map stream), with the map cache start positions moved to ours.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew7 as c7                      # noqa: E402
import maplight                                 # noqa: E402
import mapterrain                               # noqa: E402
import mapxml                                   # noqa: E402
import newmap                                   # noqa: E402

c6, c4, c2 = c7.c6, c7.c4, c7.c2
NAME = 'CampNew18'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
CENTER, RADIUS = (2500.0, 2500.0), 1800.0
START = (1250.0, 2500.0)                         # west end of the island
ENEMY = (3700.0, 2500.0)
CAPTION = 'SCRIPT:CNV02_INTRO'
OBJ = 'Objective01 - CNV Island'
c4.c3.STRINGS.update({CAPTION: 'CNV02：这张地图的地形、贴图、水面、单位和脚本全部由代码生成。',
                      'MISSIONOBJ:CNV02_1': 'CNV02 目标：消灭岛屿东侧的苏军坦克',
                      'MISSIONOBJ:CNV02_1_DESC': '一张完全由我们的工具生成的测试地图。'})

_entry = c4.cache_entry


def cache_entry():
    e = _entry()
    e['starts'] = [('InitialCameraPosition', START[0], START[1], 0.0), ('Player_1_Start', START[0], START[1], 0.0),
                   ('Player_2_Start', START[0] + 60, START[1] + 60, 0.0)]
    return e


c4.cache_entry = cache_entry


def generate(m):
    hm = mapterrain.HeightMap(m)
    heights = newmap.island_heights(hm, center=CENTER, radius=RADIUS)
    for (i, j), v in heights.items():
        hm.set(i, j, v)
    hm.store()
    tiles = mapterrain.Tiles(m, hm.width)
    for f in range(8):
        tiles.fill_field(f, f == 4)          # field 4 is set nearly everywhere on retail maps
    painted, blended = newmap.paint_terrain(m, hm, tiles)
    tiles.store()
    PREVIEWS['art'] = newmap.preview_tga(hm, tiles, 512, 24)
    PREVIEWS['small'] = newmap.preview_tga(hm, tiles, 128, 32)
    print('terrain:', painted, 'blended cells', blended, 'blend descriptions', len(tiles.descs))
    newmap.set_water(m, -300.0, -300.0, 5300.0, 5300.0)

    # objects: keep property templates of a Player_1 unit, a Soviet_1 unit and a waypoint, then start empty
    objs = next(n for _, n in m.walk() if n.name == 'ObjectsList')
    like = {}
    for k in objs.kids:
        pr, flags = newmap.typed_props_of(m, k)
        owner = pr.get('originalOwner', (3, ''))[1]
        tmpl = k.head[22:22 + int.from_bytes(k.head[20:22], 'little')].decode('latin-1')
        if tmpl == '*Waypoints/Waypoint':
            like.setdefault('wp', (pr, flags))
        elif owner == 'Player_1/teamPlayer_1':
            like.setdefault('p1', (pr, flags))
        elif owner == 'Soviet_1/teamSoviet_1' and 'objectInitialStance' not in pr:
            like.setdefault('s1', (pr, flags))
    objs.kids = []
    wp_id = [1]

    def waypoint(name, x, y):
        pr, flags = like['wp']
        objs.kids.append(newmap.object_node(m, pr, flags, '*Waypoints/Waypoint', x, y, waypointName=name,
                                            waypointID=wp_id[0], uniqueID=f'Waypoint {wp_id[0]}'))
        wp_id[0] += 1

    def unit(kind, template, x, y, angle, name=''):
        pr, flags = like[kind]
        objs.kids.append(newmap.object_node(m, pr, 0, template, x, y, angle=angle, objectName=name,
                                            uniqueID=f'{template} {len(objs.kids)}'))
    waypoint('Player_1_Start', *START)
    waypoint('Player_2_Start', START[0] + 60, START[1] + 60)
    waypoint('InitialCameraPosition', *START)
    unit('p1', 'AlliedMCV', START[0] + 150, START[1], 0.0, 'UNIT - CNV MCV')
    for k in range(4):
        unit('p1', 'AlliedAntiVehicleVehicleTech1', START[0] + 260, START[1] - 150 + 100 * k, 0.0)
    for k in range(3):
        unit('p1', 'AlliedAntiInfantryVehicle', START[0] + 360, START[1] - 100 + 100 * k, 0.0)
    for k in range(5):
        unit('s1', 'SovietAntiVehicleVehicleTech1', ENEMY[0], ENEMY[1] - 200 + 100 * k, 3.14)
    print('objects:', len(objs.kids), {k: v[1] for k, v in like.items()})

    # scripts: only ours (built before clearing: chunk versions are read off existing nodes)
    script = m.new_script('CNV02 - Intro', [m.new_content('Condition', 'CONDITION_TRUE')],
                          [m.new_content('ScriptAction', 'SHOW_MILITARY_CAPTION', CAPTION, 20.0),
                           m.new_content('ScriptAction', 'SET_MISSION_OBJECTIVE_STATUS', OBJ, 0)])
    lists = newmap.clear_scripts(m)
    lists[2].kids.append(script)
    m.set_objectives([dict(name=OBJ, title='MISSIONOBJ:CNV02_1', desc='MISSIONOBJ:CNV02_1_DESC', bonus=0, flags=1)])

    lt = maplight.lighting(m)
    lt['time_of_day'] = 1                    # morning: Heidelberg's brightest group (afternoon read dark)
    maplight.set_lighting(m, lt)


c6.edit = generate
PREVIEWS = {}
_edited = c7._edited


def edited_with_previews():
    """The map folder with our radar / preview pictures in place of Heidelberg's."""
    files = _edited()
    out = []
    for path, data in files:
        leaf = path.split(chr(92))[-1].lower()
        if leaf == c2.NEW_STEM + '_art.tga':
            data = PREVIEWS['art']
        elif leaf == c2.NEW_STEM + '.tga':
            data = PREVIEWS['small']
        out.append((path, data))
    return out


c7._edited = edited_with_previews

if __name__ == '__main__':
    c4.main()
