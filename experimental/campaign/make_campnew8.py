"""Fourth campaign, data side (CampNew8): CampNew7 + a new CampaignTemplate 'CNV' listed in the CampaignEnumerator.

  python -I -X utf8 experimental/campaign/make_campnew8.py   -> Documents\\Red Alert 3\\Mods\\CampNew8

The faction menu (APT fes_m_factionMenu) starts a campaign with FSCommand
'Campaign_SetFaction?FactionIndex=' + one of three CAMPAIGN_TYPE enum values; the campaigns themselves are data
(CampaignEnumerator: Allies, Soviet, Japan). This probe puts CNV first and the retail Allies campaign last:
  CampaignEnumerator = CNV, Soviet, Japan, Allies
so a bench run through the Allies card shows how the index maps: our CNV01 mission first -> FactionIndex is a
position in the enumerator (a 4th campaign needs only a 4th button in the APT); retail Allies mission 1 -> the
game picks campaigns some other way (by faction).

Result (bench, 2026-10-16): retail Allies mission 1 (Brighton Beach). The enumerator position is not the index.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew7 as c7                      # noqa: E402

c4, c2 = c7.c4, c7.c2
NAME = 'CampNew8'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
ORDER = ['CNV', 'Soviet', 'Japan', 'Allies']
c4.c3.STRINGS['Side:CNV'] = 'CNV 测试战役'

_sources = c2.sources


def sources():
    _sources()          # Allies_New mission + a 10-mission Allies campaign, in <NAME>.xml
    path = os.path.join(c2.SRC_DIR, f'{c2.NAME}.xml')
    xml = open(path, encoding='ascii').read()
    camp = re.search(r'<CampaignTemplate\s+id="Allies".*?</CampaignTemplate>', xml, re.S).group(0)
    cnv = camp.replace('id="Allies"', 'id="CNV"').replace('DisplayName="Side:Allies"', 'DisplayName="Side:CNV"')
    cnv = cnv.replace('ConsoleAutosaveFilename="Allies"', 'ConsoleAutosaveFilename="CNV"')
    enum = '<CampaignEnumerator id="CampaignEnumerator">\n' + ''.join(
        f'\t<Campaign>{c}</Campaign>\n' for c in ORDER) + '</CampaignEnumerator>'
    xml = xml.replace(camp, cnv + '\n\n' + enum)        # the retail Allies campaign stays as it is
    with open(path, 'w', encoding='ascii', newline='\r\n') as f:
        f.write(xml.replace('\r\n', '\n'))
    print('campaigns:', ORDER)


c2.sources = sources

if __name__ == '__main__':
    c4.main()
