"""游隼坦克 gameplay (CampNew27): the Cryocopter's partner. On CampNew26 (buildable, button, portrait) it changes:

  rapid cannon     CNV_LightTank2Cannon: 0.1 s firing + 0.25 s reload (~2.9 shots/s; Guardian 1 per 2 s), 11 CANNON
                   per shot (about the Guardian's damage per second against normal targets). A fully frozen unit
                   takes 90000% damage (CryoBeamFrozenArmor), so every shot kills one: high rate + fast retargeting
                   is the "clears frozen enemies" behaviour. The game cannot rank targets by status
                   (TargetingCompareList has distance / combat chain / turret arc only).
  fast retarget    turret 900 deg/s (360), pitch 360 (180), AcceptableAimDelta 30d (20d)
  (no frozen vision) an ObjectVisionRange for UNDER_FROZEN units was tried and dropped (CampNew28 runs): its Range
                   is a percentage of vision (a bare "250" read as 250% = 500: the tanks chased Hammers 460 away
                   before any order), and its Filter ignores StatusBitFlags (Rule ANY and ALL alike: unfrozen ore
                   collectors 230 away were attacked; without the rule they were left alone)
  speed            LocomotorSet 125 (Guardian 80, Multigunner 120; shrunk enemies run at 200%)
  crushing         CrusherLevel stays 20: crushes shrunk vehicles (CrushableLevel 1 under SHRINK_EFFECT, BaseVehicle)
                   and infantry, not normal tanks (20); CrushDecelerationPercent 20% (80%) keeps its speed
  no painter       own command set without Command_ToggleTargetPainter (attack-move, move only)
  health           400 (480): fast and hard-hitting, so a bit more fragile

Test scene (A/B): 游隼 and v1 (Guardian stats, moved 350 west) each get a Cryocopter (AlliedSupportAircraft) and
three enemy Soviet ore collectors (unarmed) 120 to the north; compare how fast each group clears them.

  python -I -X utf8 experimental/campaign/make_campnew27.py   -> Documents\\Red Alert 3\\Mods\\CampNew27
"""
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew26 as c26                    # noqa: E402

c24, c23 = c26.c24, c26.c23
c18, c7, c6, c4, c2 = c23.c18, c23.c7, c23.c6, c23.c4, c23.c2
newmap = c23.newmap
NAME = 'CampNew27'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
UNIT = c26.UNIT
CANNON, WARHEAD, COMMANDS = f'{UNIT}Cannon', f'{UNIT}Warhead', f'{UNIT}CommandSet'
c7.EXTRA_OWN += [b'LogicCommandSet:' + COMMANDS.encode()]
c4.c3.STRINGS['Desc:' + UNIT] = ('冷冻直升机的协同坦克。主炮射速极高、转塔迅速，能飞快清理被冰冻的敌人；'
                                 '机动性强，可碾压被缩小的载具。')
c4.c3.STRINGS['Type:' + UNIT] = '冰冻协同坦克'
# A/B test against unarmed targets (Hammers made it a plain tank brawl at load, twice): group A = 游隼 (already
# placed by CampNew25 just south of TANK_AT), group B = v1 with the Guardian's stats, moved 350 west; each group
# gets a Cryocopter and three enemy Soviet ore collectors (500 HP, no weapon) 120 to the north
GROUP_A = (c23.TANK_AT[0], c23.TANK_AT[1] - 45)
GROUP_B = (c23.TANK_AT[0] - 350, c23.TANK_AT[1] - 45)
TARGETS = [(g[0] + dx, g[1] + 120) for g in (GROUP_A, GROUP_B) for dx in (-45, 0, 45)]
if os.environ.get('CNV_KITE_TEST') == '1':     # range test: group A's targets at 200 (normal range 150, evade 250)
    TARGETS = [(GROUP_A[0] + dx, GROUP_A[1] + 200) for dx in (-45, 0, 45)] + TARGETS[3:]
CRYOS = [(g[0] - 30, g[1] + 50) for g in (GROUP_A, GROUP_B)]

WEAPONS = f'''	<WeaponTemplate
		id="{CANNON}"
		AttackRange="150.0"
		WeaponSpeed="1000"
		MinWeaponSpeed="5000"
		MaxWeaponSpeed="5000"
		AcceptableAimDelta="30d"
		ClipSize="1"
		WeaponRecoil="2d"
		AutoReloadsClip="AUTO"
		Flags="ATTACK_NEEDS_LINE_OF_SIGHT"
		CanFireWhileMoving="true"
		RequiredAntiMask="ANTI_WATER ANTI_GROUND ANTI_STRUCTURE"
		FireSound="ALL_Guardian_WeaponFire"
		FireFX="FX_AlliedTankGun"
		FireVeteranFX="FX_AlliedTankGun_Vet">
		<FiringDuration MinSeconds="0.1s" MaxSeconds="0.1s" />
		<ClipReloadTime MinSeconds="0.25s" MaxSeconds="0.25s" />
		<Nuggets>
			<ProjectileNugget
				WarheadTemplate="{WARHEAD}"
				ProjectileTemplate="AlliedAntiVehicleVehicleTech1Projectile">
				<VeterancyProjectiles VeterancyLevel="HEROIC" ProjectileTemplate="AlliedAntiVehicleVehicleTech1Projectile"/>
			</ProjectileNugget>
			<InformTargetNugget />
		</Nuggets>
	</WeaponTemplate>
	<WeaponTemplate
		id="{WARHEAD}"
		RadiusDamageAffects="ALLIES ENEMIES NEUTRALS"
		RequiredAntiMask="ANTI_GROUND ANTI_STRUCTURE ANTI_WATER"
		Flags="NOT_ATTRACTED_BY_MAGNETS">
		<Nuggets>
			<DamageNugget Damage="11.0" DamageType="CANNON" DamageFXType="ALLIED_CANNON" DeathType="EXPLODED" />
		</Nuggets>
	</WeaponTemplate>
	<LogicCommandSet id="{COMMANDS}">
		<Cmd>Command_CNV_ToggleEvadeMelee</Cmd>
		<Cmd>Command_AttackMove</Cmd>
		<Cmd>Command_MoveToPositionAndCollect</Cmd>
	</LogicCommandSet>
'''

# 规避近战 (evade melee) toggle, built like the Guardian's target painter / the Javelin's laser lock: ON swaps the
# cannon for a 250-range copy (Hammer / Tsunami / Tengu / Apocalypse main guns are 150) and applies SPEED 115% and
# VISION 135% (vision 200 -> 270, or it could not see its own range). There is no keep-distance AI in RA3 (no
# retreat / kite behaviour for player units; the retreat logic is skirmish-AI only): it out-ranges brawlers and
# the player keeps the gap with its speed. Not out-ranged: Hammer leech beam and Apocalypse harpoon (300; the
# leech beam cannot fire on the move). Status bit SWITCHED_WEAPONS: the dormant painter modules use
# GENERIC_TOGGLE_STATE.
KITE, EVADE = f'{UNIT}Cannon_Kite', 'CNV_EvadeMelee'
EVADE_DECL = f'''	<AttributeModifier id="AttributeModifier_{EVADE}" Category="NONE">
		<Modifier Type="SPEED" Value="115%"/>
		<Modifier Type="VISION" Value="135%"/>
	</AttributeModifier>
	<SpecialPowerTemplate id="SpecialPower_{EVADE}" TargetType="NONE" Flags="CAN_NOT_BE_SCRAMBLED"
		WaypointModeTerminal="false" ReloadTime="1s"/>
	<LogicCommand Type="SPECIAL_POWER" id="Command_CNV_ToggleEvadeMelee">
		<SpecialPower>SpecialPower_{EVADE}</SpecialPower>
		<AISpecialPowerInfo Heuristic="TOGGLE" Manager="MICRO_MANAGER"/>
	</LogicCommand>
'''
# the button: nothing references it (it names its LogicCommand), so it lives in its own file included type="all"
EVADE_UI_FILE = f'{EVADE}_UI.xml'
EVADE_UI = f'''	<ButtonSingleStateData id="ButtonState_{EVADE}On">
		<State Image="AUA_Javelin_LaserMode" Title="NAME:{EVADE}On" Description="DESC:{EVADE}On" />
	</ButtonSingleStateData>
	<ButtonSingleStateData id="ButtonState_{EVADE}Off">
		<State Image="AUA_Tank_MainGun" Title="NAME:{EVADE}Off" Description="DESC:{EVADE}Off" />
	</ButtonSingleStateData>
	<UnitAbilityButtonTemplate id="Button_{EVADE}" LogicCommand="Command_CNV_ToggleEvadeMelee">
		<Data>
			<ToggleSpecialPower>
				<StateData>ButtonState_{EVADE}On</StateData>
				<StateData>ButtonState_{EVADE}Off</StateData>
			</ToggleSpecialPower>
		</Data>
	</UnitAbilityButtonTemplate>
'''
EVADE_MODULES = f'''			<SpecialPower
				id="ModuleTag_{EVADE}Trigger"
				SpecialPowerTemplate="SpecialPower_{EVADE}"
				UpdateModuleStartsAttack="true" />
			<ToggleStatusSpecialAbilityUpdate
				id="ModuleTag_{EVADE}Update"
				Options="RECONSTITUTE_STORED_COMMAND"
				SpecialPowerTemplate="SpecialPower_{EVADE}">
				<ToggleState>
					<SkirmishAiInfo ToggleHint="TOGGLE_DEFAULT"/>
				</ToggleState>
				<ToggleState
					ObjectStatus="SWITCHED_WEAPONS"
					AttributeModifier="AttributeModifier_{EVADE}">
					<SkirmishAiInfo ToggleHint="TOGGLE_WEAPON">
						<StateWeapon Weapon="{KITE}"/>
					</SkirmishAiInfo>
				</ToggleState>
			</ToggleStatusSpecialAbilityUpdate>

			<!-- the target painter trigger -->'''
c4.c3.STRINGS.update({
    f'NAME:{EVADE}On': '规避近战：开启',
    f'DESC:{EVADE}On': '切换为远射模式：主炮射程提升到 250，移速和视野提高。在铁锤等近战坦克够不着的距离开火，'
                       '靠机动拉开距离。',
    f'NAME:{EVADE}Off': '规避近战：关闭',
    f'DESC:{EVADE}Off': '恢复常规射程与速度。',
})
c7.EXTRA_OWN += [b'LogicCommand:Command_CNV_ToggleEvadeMelee', b'UnitAbilityButtonTemplate:Button_' + EVADE.encode(),
                 b'ButtonSingleStateData:ButtonState_' + EVADE.encode(), b'AttributeModifier:AttributeModifier_' +
                 EVADE.encode(), b'SpecialPowerTemplate:SpecialPower_' + EVADE.encode(),
                 b'WeaponTemplate:' + KITE.encode()]
c7.EXTRA_ALL.append('DATA:CNVUnits/Data/' + EVADE_UI_FILE)


def write_evade_ui():
    with open(os.path.join(c26.DATA, EVADE_UI_FILE), 'w', encoding='utf-8', newline='\r\n') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<AssetDeclaration xmlns="uri:ea.com:eala:asset" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n' + EVADE_UI + '</AssetDeclaration>\n')


def kite_weapon():
    """The cannon's declaration with the kite id, 250 range and a minimum range of 100 (the Athena's solar
    targeter and the V4 keep min / max at 0.4, 200 / 500): inside it the tank does not fire, so in this mode it
    leaves Hammer-range brawls (150) to the player's micro instead of trading shots point blank."""
    block = WEAPONS[:WEAPONS.index('</WeaponTemplate>') + len('</WeaponTemplate>')] + '\n'
    out = block.replace(f'id="{CANNON}"', f'id="{KITE}"').replace(
        'AttackRange="150.0"', 'AttackRange="250.0"\n\t\tMinimumAttackRange="100.0"')
    assert f'id="{KITE}"' in out and 'MinimumAttackRange="100.0"' in out
    return out



def sub1(x, old, new):
    """Replace the first occurrence, insisting it is there (the Guardian XML is the template)."""
    assert old in x, old
    return x.replace(old, new, 1)


_patch_unit = c26.patch_unit


def patch_unit():
    _patch_unit()                               # CampNew26: button, portrait, name, cost, no tech-2 prerequisite
    path = os.path.join(c26.DATA, UNIT + '.xml')
    x = open(path, encoding='utf-8').read()
    x = sub1(x, 'Template="AlliedAntiVehicleVehicleTech1Cannon"', f'Template="{CANNON}"')
    x = sub1(x, 'TurretTurnRate="360"', 'TurretTurnRate="900"')
    x = sub1(x, 'TurretPitchRate="180"', 'TurretPitchRate="360"')
    x = sub1(x, 'CommandSet="AlliedAntiVehicleVehicleTech1CommandSet"', f'CommandSet="{COMMANDS}"')
    x = re.sub(r'(<LocomotorSet\b[^>]*Condition="NORMAL"[^>]*Speed=")80\.0(")', r'\g<1>125.0\2', x)
    assert 'Speed="125.0"' in x
    x = sub1(x, 'MaxHealth="480"', 'MaxHealth="400"')
    x = sub1(x, 'CrushDecelerationPercent="80%"', 'CrushDecelerationPercent="20%"')
    # 规避近战: cannon only outside the toggle, the kite cannon inside it; the toggle modules before the painter's
    x, n = re.subn(r'(<Weapon\s+Ordering="PRIMARY_WEAPON"\s+Template="' + CANNON + r'")\s+'
                   r'ForbiddenObjectStatus="GENERIC_TOGGLE_STATE"\s*/>',
                   r'\1 ForbiddenObjectStatus="SWITCHED_WEAPONS"/>\n\t\t\t\t\t<Weapon Ordering="PRIMARY_WEAPON" '
                   f'Template="{KITE}" ObjectStatus="SWITCHED_WEAPONS"/>', x, count=1)
    assert n == 1
    x = sub1(x, '\t\t\t<!-- the target painter trigger -->', EVADE_MODULES)
    x = sub1(x, '</AssetDeclaration>', WEAPONS + kite_weapon() + EVADE_DECL + '</AssetDeclaration>')
    with open(path, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(x.replace('\r\n', '\n'))
    write_evade_ui()
    print('gameplay:', CANNON, 'turret 900', 'speed 125', 'health 400', COMMANDS, '+', EVADE, 'toggle')


c26.patch_unit = patch_unit
_generate = c6.edit


def generate(m):
    _generate(m)                                 # CampNew26 (and its factory, power plant, both tanks)
    objs = next(n for _, n in m.walk() if n.name == 'ObjectsList')
    p1 = next(k for k in objs.kids if b'AlliedAntiVehicleVehicleTech1' in k.head[:60])
    s1 = next(k for k in objs.kids if b'SovietAntiVehicleVehicleTech1' in k.head[:60])
    v1 = [k for k in objs.kids if b'CNV_LightTank' in k.head[:60] and b'CNV_LightTank2' not in k.head[:60]]
    assert len(v1) == 1
    objs.kids.remove(v1[0])                      # v1 goes to group B
    # the map's Soviet tank and CampNew23's copy of it drove in and killed 游隼 (third and fourth runs)
    objs.kids[:] = [k for k in objs.kids if b'SovietAntiVehicleVehicleTech1' not in k.head[:60]]
    for src, template, (x, y), angle in ([(p1, c23.UNIT, GROUP_B, 0.0)] +
                                         [(p1, 'AlliedSupportAircraft', at, 0.0) for at in CRYOS] +
                                         [(s1, 'SovietMiner', at, -math.pi / 2) for at in TARGETS]):
        pr, flags = newmap.typed_props_of(m, src)
        objs.kids.append(newmap.object_node(m, pr, flags, template, x, y, angle=angle,
                                            uniqueID=f'{template} {len(objs.kids)}'))


c6.edit = generate

if __name__ == '__main__':
    if c23.game_running():
        c2.OUT = c4.OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'work', 'staging', NAME)
        print('RA3 is running -> staging at', c4.OUT)
    c4.main()
