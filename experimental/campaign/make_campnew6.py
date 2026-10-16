"""CampNew4 + structural script edits made with our own editor (mapscript.py): new scripts, a removed action, an
added condition, renamed mission objectives (CampNew6).

  python -I -X utf8 experimental/campaign/make_campnew6.py   -> Documents\\Red Alert 3\\Mods\\CampNew6

What a bench run should show in the new mission:
  - no A03TH03 video call (MOVIE_PLAY_RADAR removed from 'TH - A03TH03 - Play'; 'TH - A03TH03 - End' now fires on
    CONDITION_TRUE instead of waiting for that video, so the talking-head controller keeps going)
  - a few seconds in, a military caption with our new CSF line (two new scripts: start a timer, show the caption)
  - objectives 1 and 5 titled with the CNV01 labels
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew4 as c4                      # noqa: E402
from mapscript import MapFile                   # noqa: E402

NAME = 'CampNew6'
c4.NAME = c4.c2.NAME = NAME
c4.c2.SRC_DIR = os.path.join(c4.c2.SDK, 'Mods', NAME, 'data')
c4.c2.BUILT = os.path.join(c4.c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c4.c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
CAPTION = 'SCRIPT:CNV01_HINT_INTRO'
c4.c3.STRINGS[CAPTION] = 'CNV01 测试：这条提示来自我们自己的脚本编辑器新增的脚本。'
TIMER = 'TIMER - CNV Intro'

_map_files = c4.c2.map_files


def edit(m):
    play, end = 'TH - A03TH03 - Play', 'TH - A03TH03 - End'
    print('removed actions:', m.remove_contents(play, 'MOVIE_PLAY_RADAR'))
    print('removed conditions:', m.remove_contents(end, 'HAS_FINISHED_VIDEO'))
    m.add_condition(end, m.new_content('Condition', 'CONDITION_TRUE'), group=0)
    timer = m.new_script('CNV - Intro Timer', [m.new_content('Condition', 'CONDITION_TRUE')],
                         [m.new_content('ScriptAction', 'SET_MILLISECOND_TIMER', TIMER, 3.0)])
    caption = m.new_script('CNV - Intro Caption', [m.new_content('Condition', 'TIMER_EXPIRED', TIMER)],
                           [m.new_content('ScriptAction', 'SHOW_MILITARY_CAPTION', CAPTION, 30.0)])
    m.add_script(timer, after='Allied Special Power Restrictions')
    m.add_script(caption, after='CNV - Intro Timer')
    objs = m.objectives()
    objs[0]['title'] = 'MISSIONOBJ:CNV01_1'
    objs[5]['title'] = 'MISSIONOBJ:CNV01_2'
    m.set_objectives(objs)


def edited_map_files():
    out = []
    for path, data in _map_files():
        if path.lower().endswith('.map'):
            m = MapFile(data)
            edit(m)
            data = m.map_file()
            again = MapFile(data)
            assert again.chunk_file() == m.chunk_file()
            text = again.script_text()
            for line in text.split('\n'):
                if 'CNV' in line or 'A03TH03' in line:
                    print('   ', line)
            print('   objectives:', [o['title'] for o in again.objectives()])
        out.append((path, data))
    return out


c4.c2.map_files = edited_map_files

if __name__ == '__main__':
    c4.main()
