"""New mission through the mod map-metadata stream (CampNew3) -- no static stream splicing.

  python -I -X utf8 experimental/campaign/make_campnew3.py   -> Documents\\Red Alert 3\\Mods\\CampNew3

The Arsenal campaign mod keeps its MissionTemplates, its map cache (MapMetaData:TheMapCache_MOD) and portrait
images in data\\additionalmaps\\mapmetadata_mod.*, a small stream the game loads for mods. This probe does the same:
  - campaign: MissionTemplate Allies_New (retail Allies_3, Heidelberg, unlocked) + CampaignTemplate Allies of 10
  - map: data\\maps\\official\\camp_cnv01_probe\\camp_cnv01_probe.map (renamed copy, no precompiled map streams),
    registered in TheMapCache_MOD with the retail Heidelberg values (CRC 0 and not official, as Arsenal does)
  - strings: data\\gamestrings.csf = the installed CNVoice text table + the new labels (mod.str is read as Latin-1)
"""
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from ra3voice import big, csf, refpack                   # noqa: E402

SDK = r'C:\RA3ModSDK'
NAME = 'CampNew3'
GAME = r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3'
SRC_DIR = os.path.join(SDK, 'Mods', NAME, 'data', 'additionalmaps')
BUILT = os.path.join(SDK, 'BuiltMods', 'mods', NAME.lower(), 'data', 'additionalmaps')
OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
OLD_DIR, OLD_STEM = 'data\\maps\\official\\camp_a03_heidelberg_smith\\', 'camp_a03_heidelberg_smith'
NEW_STEM = 'camp_cnv01_probe'
NEW_DIR = f'data\\maps\\official\\{NEW_STEM}\\'
NEW_MAP = NEW_DIR + NEW_STEM + '.map'
# CNV_PROBE_MAP=retail: register / use the retail Heidelberg map (which has compiled map streams) instead, as a
# control: tells a failing new-map folder apart from a failing campaign route
if os.environ.get('CNV_PROBE_MAP') == 'retail':
    NAME, NEW_MAP = 'CampNew3R', 'data\\maps\\official\\CAMP_A03_Heidelberg_Smith\\CAMP_A03_Heidelberg_Smith.map'
    SRC_DIR = os.path.join(SDK, 'Mods', NAME, 'data', 'additionalmaps')
    BUILT = os.path.join(SDK, 'BuiltMods', 'mods', NAME.lower(), 'data', 'additionalmaps')
    OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
GAME_ALL_TYPES_HASH = 1424942948      # manifest header field 4 of static.12 / global.12 ... and of Arsenal's stream
STRINGS = {
    'MissionName:CNV01': 'CNV01 新关卡测试：海德堡',
    'MissionName:CNV01_Short': 'CNV01 新关卡',
    'BriefingSummary:CNV01': 'CNV01：这是由配音 mod 测试生成的新关卡。地图来自新的文件夹，标题和简报来自 mod 自己的字符串表。',
    'MISSIONOBJ:CNV01_1': 'CNV01 目标一：护送基地车',
    'MISSIONOBJ:CNV01_2': 'CNV01 目标二：攻下苏军总部',
}
# retail TheMapCache entry of CAMP_A03_Heidelberg_Smith (data\\mapmetadata in Maps11.big)
MAP_ENTRY = dict(Description='Map:CAMP_A03_Heidelberg_Smith/Desc', DisplayName='CAMP_A03_Heidelberg_Smith',
                 IsMultiplayer='false', NumPlayers='2', CRC='0', IsOfficial='false', Width='560', Height='560',
                 BorderSize='30')
STARTS = [('InitialCameraPosition', 0, 0, 0), ('Player_1_Start', 773.44, 3002.5, 0), ('Player_2_Start', 797.87, 3021.47, 0)]


def sources():
    xml = open(os.path.join(SDK, 'SageXML', 'GlobalData', 'CampaignTemplates.xml'), encoding='ascii').read()
    new = re.search(r'<MissionTemplate\s+id="Allies_3".*?</MissionTemplate>', xml, re.S).group(0)
    new = new.replace('id="Allies_3"', 'id="Allies_New"')
    new = re.sub(r'<Prerequisite>\d+</Prerequisite>', '<Prerequisite>0</Prerequisite>', new)
    new = re.sub(r'ShortDisplayName="[^"]*"', 'ShortDisplayName="MissionName:CNV01_Short"', new)
    new = re.sub(r'(?<!Short)DisplayName="[^"]*"', 'DisplayName="MissionName:CNV01"', new)
    new = re.sub(r'BriefingSummary="[^"]*"', 'BriefingSummary="BriefingSummary:CNV01"', new)
    for k, o in enumerate(re.findall(r'<Objective>[^<]*</Objective>', new)):
        new = new.replace(o, f'<Objective>MISSIONOBJ:CNV01_{k + 1}</Objective>' if k < 2 else '', 1)
    new = re.sub(r'MapName="[^"]*"', lambda m: f'MapName="{NEW_MAP}"', new)     # (backslashes: no template)
    camp = re.search(r'<CampaignTemplate\s+id="Allies".*?</CampaignTemplate>', xml, re.S).group(0)
    camp = camp.replace('<Mission>Allies_1</Mission>', '<Mission>Allies_New</Mission>\n\t<Mission>Allies_1</Mission>', 1)
    assert camp.count('<Mission>') == 10
    # self-contained like Arsenal's stream (it links nothing; linked to static / global the game crashes ~3 s in):
    # the campaign's other 9 missions come along, and the co-op AI commanders lose their portraits (OnDemandImageRef
    # into static; optional in the schema, an AICommander itself is required)
    retail = [re.search(rf'<MissionTemplate\s+id="Allies_{k}".*?</MissionTemplate>', xml, re.S).group(0) for k in range(1, 10)]
    no_ai = lambda t: re.sub(r'\s*Portrait="[^"]*"', '', t)       # noqa: E731
    os.makedirs(SRC_DIR, exist_ok=True)
    with open(os.path.join(SRC_DIR, 'campaigntemplates.xml'), 'w', encoding='ascii', newline='\r\n') as f:
        f.write('<?xml version="1.0" encoding="us-ascii"?>\n<AssetDeclaration xmlns="uri:ea.com:eala:asset">\n\n')
        f.write('\n\n'.join(no_ai(t) for t in [new] + retail) + '\n\n' + camp + '\n\n</AssetDeclaration>\n')
    attrs = ' '.join(f'{k}="{v}"' for k, v in MAP_ENTRY.items())
    starts = ''.join(f'\n\t\t\t<StartPosition Name="{n}"><Position x="{x}" y="{y}" z="{z}" /></StartPosition>'
                     for n, x, y, z in STARTS)
    with open(os.path.join(SRC_DIR, 'mapmetadata_mod.xml'), 'w', encoding='utf-8', newline='\r\n') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<AssetDeclaration xmlns="uri:ea.com:eala:asset" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
                '\t<Tags></Tags>\n\t<Includes>\n'
                f'\t\t<Include type="all" source="DATA:{NAME}/data/additionalmaps/campaigntemplates.xml" />\n'
                '\t</Includes>\n'
                '\t<MapMetaData id="TheMapCache_MOD">\n'
                f'\t\t<MapMetaData id="{NEW_STEM}" FileName="{NEW_MAP}" {attrs}>{starts}\n\t\t</MapMetaData>\n'
                '\t</MapMetaData>\n</AssetDeclaration>\n')


def compile_stream():
    r = subprocess.run([os.path.join(SDK, 'tools', 'BinaryAssetBuilder.exe'), os.path.join(SRC_DIR, 'mapmetadata_mod.xml'),
                        r'/od:C:\RA3ModSDK\BuiltMods', r'/iod:C:\RA3ModSDK\BuiltMods', '/ls:true', '/gui:false',
                        '/pc:true', '/vf:false', '/el:0'], cwd=SDK, capture_output=True, text=True, errors='replace')
    log = os.path.join(SDK, f'_build_{NAME}.log')
    open(log, 'w', encoding='utf-8').write(r.stdout + r.stderr)
    if r.returncode or 'BinaryAssetBuilder complete' not in r.stdout:
        sys.exit('BinaryAssetBuilder failed, see ' + log)
    files = []
    for x in ('manifest', 'bin', 'relo', 'imp'):
        p = os.path.join(BUILT, f'mapmetadata_mod.{x}')
        v = open(p, 'rb').read()
        if x == 'manifest':
            # the SDK stamps its own AllTypesHash (177706643); the 1.12 game and its patch streams (and Arsenal's
            # working stream) carry 1424942948: with the SDK value the game crashes ~3 s after start
            v = v[:12] + struct.pack('<I', GAME_ALL_TYPES_HASH) + v[16:]
        files.append((f'data\\additionalmaps\\mapmetadata_mod.{x}', v))
    return files


def map_files():
    found = {}
    for a in ('MapsCampaign.big', 'Maps10.big', 'Maps11.big'):
        p = os.path.join(GAME, 'Data', a)
        names = [n for n, _, _ in big.read_index(p) if n.lower().startswith(OLD_DIR)]
        for n, v in big.read_files(p, names).items():
            leaf = n[len(OLD_DIR):].lower()
            if not leaf.startswith('map.'):            # no precompiled map streams: they belong to the old folder
                found[NEW_DIR + leaf.replace(OLD_STEM, NEW_STEM)] = v
    return sorted(found.items())


def strings():
    name = 'data\\gamestrings.csf'
    data = big.read_files(os.path.join(GAME, 'Data', 'CNVoice_text.big'), [name])[name]
    header, entries = csf.parse_full(data)
    have = {e[0] for e in entries}
    entries += [(k, v, None, 1) for k, v in STRINGS.items() if k not in have]
    return [(name, refpack.compress_literal(csf.write(header, entries)))]


def main():
    sources()
    files = compile_stream() + ([] if NAME.endswith('R') else map_files()) + strings()
    for n, v in files:
        print(f'  {n} {len(v)}')
    os.makedirs(OUT, exist_ok=True)
    big.write(os.path.join(OUT, f'{NAME}.big'), files)
    with open(os.path.join(OUT, f'{NAME}_1.0.skudef'), 'w', encoding='ascii', newline='') as f:
        f.write(f'mod-game 1.12\r\nadd-big {NAME}.big\r\n')
    print('->', OUT)


if __name__ == '__main__':
    main()
