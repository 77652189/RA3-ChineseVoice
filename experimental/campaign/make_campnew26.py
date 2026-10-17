"""Light tank v2 buildable (CampNew26): CampNew25's layout plus a CNV War Factory and a power plant for the player.

The new tank gets its own production button (experimental/units/button_icon.py: a transparent Blender render over
the retail button frame), name, type and description. The retail AlliedWarFactoryCommandSet is not overridden
(a map-stream copy of a static-stream instance is untested): CNV_WarFactory is a copy of AlliedWarFactory whose
command set is the retail list plus Command_ConstructCNV_LightTank2.

  python -I -X utf8 experimental/campaign/make_campnew26.py   -> Documents\\Red Alert 3\\Mods\\CampNew26
"""
import math
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew25 as c25                    # noqa: E402

c24, c23 = c25.c24, c25.c23
c18, c7, c6, c4, c2 = c23.c18, c23.c7, c23.c6, c23.c4, c23.c2
newmap = c23.newmap
NAME = 'CampNew26'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
UNIT = c24.AI_UNIT                              # CNV_LightTank2
BUTTON = f'Button_{UNIT}_on'
FACTORY, COMMANDS = 'CNV_WarFactory', 'CNV_WarFactoryCommandSet'
DATA = os.path.join(c2.SDK, 'Mods', 'CNVUnits', 'Data')
PORTRAIT = f'Portrait_{UNIT}'
ART = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'work', 'units', 'lighttank2')     # button_icon.py output
c7.EXTRA_OWN += [b'LogicCommandSet:' + COMMANDS.encode(), b'LogicCommand:Command_Construct' + UNIT.encode()] + \
    [p + n.encode() for n in (BUTTON, PORTRAIT) for p in (b'PackedTextureImage:', b'Texture:')]
c7.EXTRA_TEMPLATES[FACTORY] = {'file': 'DATA:CNVUnits/Data/' + FACTORY + '.xml', 'EditorSorting': 'STRUCTURE'}
c4.c3.STRINGS.update({
    'Name:' + UNIT: '游隼坦克',
    'Type:' + UNIT: '快速突击坦克',
    'Desc:' + UNIT: '轻快的突击坦克，长身管主炮射程远，适合快速穿插、追击受损装甲。',
})
FACTORY_AT = (c18.START[0] + 300, c18.START[1] + 60)
POWER_AT = (c18.START[0] + 300, c18.START[1] - 140)


def image_assets(name):
    """Texture (128 x 128, the image at the top left) and the PackedTextureImage the GameObject names."""
    from PIL import Image
    icon = Image.open(os.path.join(ART, name + '.tga')).convert('RGBA')
    tex = Image.new('RGBA', (128, 128))
    tex.paste(icon, (0, 0))
    tex.save(os.path.join(DATA, name + '.tga'))
    w, h = icon.size
    return (f'\t<Texture id="{name}_tex" File="{name}.tga" OutputFormat="A8R8G8B8" GenerateMipMaps="false"'
            f' AllowAutomaticResize="false"/>\n'
            f'\t<PackedTextureImage id="{name}" Texture="{name}_tex" Rotated="false">\n'
            f'\t\t<Dimensions x="{w}" y="{h}"/>\n\t\t<Coords x="0" y="0"/>\n'
            f'\t\t<TextureDimensions x="128" y="128"/>\n\t</PackedTextureImage>\n')


def patch_unit():
    path = os.path.join(DATA, UNIT + '.xml')
    x = open(path, encoding='utf-8').read()
    x = x.replace('ButtonImage="Button_AlliedAntiVehicleVehicleTech1_on"', f'ButtonImage="{BUTTON}"')
    x = x.replace('SelectPortrait="Portrait_AlliedAntiVehicleVehicleTech1"', f'SelectPortrait="{PORTRAIT}"')
    x = x.replace('Description="Desc:AlliedAntiVehicleVehicleTech1"', f'Description="Desc:{UNIT}"')
    x = x.replace('TypeDescription="Type:AlliedAntiVehicleVehicleTech1"', f'TypeDescription="Type:{UNIT}"')
    x = re.sub(r'(<BuildCost Account="=\$ACCOUNT_ORE" Amount=")\d+(")', r'\g<1>800\2', x)
    # the Guardian needs Upgrade_AlliedTech2 (armor facility); a light tank is buildable from the start
    x = re.sub(r'\s*<GameDependency>\s*<NeededUpgrade>Upgrade_AlliedTech2</NeededUpgrade>\s*</GameDependency>', '', x)
    assert 'Upgrade_AlliedTech2' not in x
    x = x.replace('</AssetDeclaration>', image_assets(BUTTON) + image_assets(PORTRAIT) +
                  f'\t<LogicCommand Type="UNIT_BUILD" id="Command_Construct{UNIT}">\n'
                  f'\t\t<Object>{UNIT}</Object>\n\t</LogicCommand>\n</AssetDeclaration>')
    for want in (f'ButtonImage="{BUTTON}"', f'SelectPortrait="{PORTRAIT}"', f'Description="Desc:{UNIT}"',
                 'Amount="800"'):
        assert want in x, want
    with open(path, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(x.replace('\r\n', '\n'))


def factory_xml():
    src = open(os.path.join(c2.SDK, 'SageXML', 'Allied', 'Structures', 'AlliedWarFactory.xml'), encoding='utf-8').read()
    x = src.replace('id="AlliedWarFactory"', f'id="{FACTORY}"', 1)
    x = x.replace('EditorName="AlliedWarFactory"', f'EditorName="{FACTORY}"')
    x = x.replace('CommandSet="AlliedWarFactoryCommandSet"', f'CommandSet="{COMMANDS}"')
    assert f'id="{FACTORY}"' in x and f'CommandSet="{COMMANDS}"' in x
    sets = open(os.path.join(c2.SDK, 'SageXML', 'GlobalData', 'LogicCommandSet.xml'), encoding='utf-8').read()
    body = re.search(r'id="AlliedWarFactoryCommandSet">(.*?)</LogicCommandSet>', sets, re.S).group(1)
    cmds = re.findall(r'<Cmd>([^<]+)</Cmd>', re.sub(r'<!--.*?-->', '', body, flags=re.S))
    cmds.insert(cmds.index('Command_ConstructAlliedAntiVehicleVehicleTech1') + 1, f'Command_Construct{UNIT}')
    decl = (f'\t<LogicCommandSet id="{COMMANDS}">\n' + ''.join(f'\t\t<Cmd>{c}</Cmd>\n' for c in cmds) +
            '\t</LogicCommandSet>\n')
    x = x.replace('</AssetDeclaration>', decl + '</AssetDeclaration>')
    x = x.replace('<Includes>', f'<Includes>\n\t\t<Include type="all" source="DATA:CNVUnits/Data/{UNIT}.xml" />', 1)
    with open(os.path.join(DATA, FACTORY + '.xml'), 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(x.replace('\r\n', '\n'))
    print('factory commands:', cmds)


_generate = c6.edit


def generate(m):
    _generate(m)                                 # CampNew25: both tanks, Soviet tank, unit XMLs
    patch_unit()
    factory_xml()
    objs = next(n for _, n in m.walk() if n.name == 'ObjectsList')
    p1 = next(k for k in objs.kids if b'AlliedAntiVehicleVehicleTech1' in k.head[:60])
    # factory turned round: at angle 0 its door faced east, under the sidebar in the bench camera
    for template, (x, y), angle in ((FACTORY, FACTORY_AT, math.pi), ('AlliedPowerPlant', POWER_AT, 0.0)):
        pr, flags = newmap.typed_props_of(m, p1)
        objs.kids.append(newmap.object_node(m, pr, flags, template, x, y, angle=angle,
                                            uniqueID=f'{template} {len(objs.kids)}'))


c6.edit = generate

if __name__ == '__main__':
    if c23.game_running():
        c2.OUT = c4.OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'work', 'staging', NAME)
        print('RA3 is running -> staging at', c4.OUT)
    c4.main()
