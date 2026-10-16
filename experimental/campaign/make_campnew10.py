"""A campaign entry that jumps straight to chapters appended to a retail campaign (CampNew10).

  python -I -X utf8 experimental/campaign/make_campnew10.py   -> Documents\\Red Alert 3\\Mods\\CampNew10

CampNew8/9: FactionIndex is not a CampaignEnumerator position (CNV listed first, the Allies card still opens
Allies), and 'FactionIndex=3&x=..' gives an 'undefined' briefing and a crash. The idea tried here: the shell
seems to chain game calls in one FSCommand string separated by '%' (fem_m_coopstaging's constants read
'%SetMap?Map=..%Campaign_SetFaction?FactionIndex=..%Campaign_SetMission?MissionIndex=..'), and
Campaign_SetMission picks any chapter of the current campaign. So the CNV01 mission is appended to the Allies
campaign (chapter index 9, after the nine retail ones) and the faction menu's command becomes
  %Campaign_SetFaction?FactionIndex=0%Campaign_SetMission?MissionIndex=9&x=<card index>
which in this probe sends every card to that chapter. A briefing titled CNV01 means a new entry button (a fourth
card, still to be drawn in the APT) can start our own chapters.

Result (bench, 2026-10-16): no. Both orders (faction then mission with '&x=' after the card index, and
'%Campaign_SetMission?MissionIndex=9%Campaign_SetFaction?FactionIndex=' + index) give the 'undefined' briefing
and a crash; the control run (CNV_FSCOMMAND set to the original string, same append-and-repoint edit) opens Allies
mission 1 normally. So the engine takes one call per FSCommand (coopstaging's pieces are separate calls) and the
APT constant edit itself is sound. CampNew9's 'FactionIndex=3&x=' is therefore no proof that index 3 is out of
range either. Next step for a real entry: an APT bytecode edit (a fourth card whose handler makes two calls).
"""
import os
import re
import sys

os.environ.setdefault('CNV_FSCOMMAND', '%Campaign_SetFaction?FactionIndex=0%Campaign_SetMission?MissionIndex=9&x=')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew9 as c9                      # noqa: E402

c8, c7, c4, c2 = c9.c8, c9.c7, c9.c4, c9.c2
NAME = 'CampNew10'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'


def sources():
    c8._sources()       # make_campnew2: Allies_New first in a 10-mission Allies campaign; move it to the end
    path = os.path.join(c2.SRC_DIR, f'{NAME}.xml')
    xml = open(path, encoding='ascii').read().replace('\r\n', '\n')
    camp = re.search(r'<CampaignTemplate\s+id="Allies".*?</CampaignTemplate>', xml, re.S).group(0)
    missions = re.findall(r'<Mission>[^<]+</Mission>', camp)
    assert missions[0] == '<Mission>Allies_New</Mission>' and len(missions) == 10, missions
    moved = camp.replace(missions[0] + '\n\t', '', 1).replace(missions[-1], missions[-1] + '\n\t' + missions[0], 1)
    assert re.findall(r'<Mission>[^<]+</Mission>', moved)[-1] == missions[0], moved
    with open(path, 'w', encoding='ascii', newline='\r\n') as f:
        f.write(xml.replace(camp, moved))
    print('Allies chapters:', [m[9:-10] for m in re.findall(r'<Mission>[^<]+</Mission>', moved)])


c2.sources = sources

if __name__ == '__main__':
    c4.main()
