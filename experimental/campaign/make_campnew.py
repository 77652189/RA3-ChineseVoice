"""SDK mod sources for the "new mission" probe: Allied campaign = [Allies_New, Allies_1 .. Allies_9].

  python -I -X utf8 experimental/campaign/make_campnew.py      -> C:\\RA3ModSDK\\Mods\\CampNew\\data\\*.xml

Allies_New is a brand-new MissionTemplate (copied from retail Allies_3, Heidelberg, unlocked from the start), so a
new Allied campaign starting on Heidelberg proves both a new instance and a longer mission list load.
"""
import os
import re

SDK = r'C:\RA3ModSDK'
SRC = os.path.join(SDK, 'SageXML', 'GlobalData', 'CampaignTemplates.xml')
OUT = os.path.join(SDK, 'Mods', 'CampNew', 'data')

xml = open(SRC, encoding='ascii').read()
m = re.search(r'<MissionTemplate\s+id="Allies_3".*?</MissionTemplate>', xml, re.S)
new = m.group(0).replace('id="Allies_3"', 'id="Allies_New"')
new = re.sub(r'<Prerequisite>\d+</Prerequisite>', '<Prerequisite>0</Prerequisite>', new)
camp = re.search(r'<CampaignTemplate\s+id="Allies".*?</CampaignTemplate>', xml, re.S).group(0)
camp = camp.replace('<Mission>Allies_1</Mission>', '<Mission>Allies_New</Mission>\n\t<Mission>Allies_1</Mission>', 1)
assert camp.count('<Mission>') == 10
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, 'CampNew.xml'), 'w', encoding='ascii', newline='\r\n') as f:
    f.write('<?xml version="1.0" encoding="us-ascii"?>\n<AssetDeclaration xmlns="uri:ea.com:eala:asset">\n\n')
    f.write(new + '\n\n' + camp + '\n\n</AssetDeclaration>\n')
with open(os.path.join(OUT, 'mod.xml'), 'w', encoding='utf-8', newline='\r\n') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<AssetDeclaration xmlns="uri:ea.com:eala:asset" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            '\t<Tags></Tags>\n\t<Includes>\n'
            '\t\t<Include type="reference" source="DATA:static.xml" />\n'
            '\t\t<Include type="reference" source="DATA:global.xml" />\n'
            '\t\t<Include type="reference" source="DATA:audio.xml" />\n'
            '\t\t<Include type="all" source="DATA:CampNew/Data/CampNew.xml" />\n'
            '\t</Includes>\n</AssetDeclaration>\n')
print('->', OUT, '| Allies_New from Allies_3:', re.search(r'MapName="([^"]+)"', new).group(1))
