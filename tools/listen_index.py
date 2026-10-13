"""Index of every dubbed line for the installer's "试听" window: files/listen_index.json in each release.

The installer plays a line straight out of the package's own archives (files/<game>/CNVoice_*.big), so the
index only says where each line lives and what to call it - no extra audio is shipped.

  entry = [category, group, zh, en, game, archive, entry name, kind, sample_rate, channels, start_s, length_s]
  kind  x = cdata with its own SNR header (unit voices, EVA, commanders)
        s = streamed cdata: RefPack-wrapped SNS blocks, header rebuilt from sample_rate / channels (mission lines)
        m = a whole movie .snd (EA-XA v2); the line is the window start_s .. start_s + length_s
Groups are named the way the game names things (unit names from its string table after this mod's term map).
"""
import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import big, textpack  # noqa: E402

VOICE = ['allied', 'soviet', 'empire', 'eva', 'commander', 'mission']
FACTION = {'A': '盟军', 'S': '苏联', 'J': '帝国', 'I': '帝国'}
UNITS = {  # group prefix -> English name in the game's string table (glossary name as fallback)
    'AUAircr_': ('Aircraft Carrier', '航空母舰'), 'AUApoll_': ('Apollo Fighter', '阿波罗战斗机'),
    'AUAssau_': ('Assault Destroyer', '突击驱逐舰'), 'AUAthen_': ('Athena Cannon', '雅典娜炮'),
    'AUCentu_': ('Century Bomber', '世纪轰炸机'), 'AUCryoL_': ('Cryo Legionnaire', '冷冻军团兵'),
    'AUCryoc_': ('Cryocopter', '冷冻直升机'), 'AUEngin_': ('Engineer', '工程师'), 'AUFutur_': ('Future Tank X-1', '未来坦克X-1'),
    'AUGuard_': ('Guardian Tank', '守护者坦克'), 'AUHarbi_': ('Harbinger Gunship', '先驱者炮艇'),
    'AUHydro_': ('Hydrofoil', '水翼船'), 'AUIFV_': ('Multigunner IFV', '多功能步兵车'), 'AUJavel_': ('Javelin Soldier', '标枪兵'),
    'AUMCV_': ('', '盟军基地车'), 'AUMirag_': ('Mirage Tank', '幻影坦克'), 'AUPacif_': ('Pacifier FAV', '和平使者'),
    'AUPeace_': ('Peacekeeper', '维和步兵'), 'AUProsp_': ('Prospector', '勘探者'), 'AURipti_': ('Riptide ACV', '激流气垫船'),
    'AUSpy_': ('Spy', '间谍'), 'AUTanya_': ('Tanya', '谭雅'), 'AUVindi_': ('Vindicator', '复仇者'),
    'SUAkula_': ('Akula Sub', '阿库拉潜艇'), 'SUApoca_': ('Apocalypse Tank', '天启坦克'), 'SUBullf_': ('Bullfrog', '牛蛙'),
    'SUComba_': ('Combat Engineer', '战斗工程师'), 'SUConsc_': ('Conscript', '动员兵'), 'SUDesol_': ('Desolator Trooper', '辐射工兵'),
    'SUDread_': ('Dreadnought', '无畏舰'), 'SUFlakt_': ('Flak Trooper', '防空步兵'), 'SUGrind_': ('Grinder', '粉碎者'),
    'SUHamme_': ('Hammer Tank', '铁锤坦克'), 'SUKirov_': ('Kirov Airship', '基洛夫飞艇'), 'SUMCV_': ('', '苏联基地车'),
    'SUMigFi_': ('MiG Fighter', '米格战机'), 'SUMorta_': ('Mortar Cycle', '迫击炮摩托'), 'SUNatas_': ('Natasha', '娜塔莎'),
    'SUOreCo_': ('', '苏联矿车'), 'SUReape_': ('Reaper', '收割者'), 'SUScien_': ('', '苏联科学家'), 'SUSickl_': ('Sickle', '镰刀机甲'),
    'SUSputn_': ('Sputnik', '斯普特尼克'), 'SUSting_': ('Stingray', '黄貂鱼'), 'SUTesla_': ('Tesla Trooper', '磁暴步兵'),
    'SUTwinb_': ('Twinblade', '双刃直升机'), 'SUV4_': ('V4 Rocket Launcher', 'V4火箭车'),
    'IUArche_': ('Archer Maiden', '弓箭少女'), 'IUGigaF_': ('Giga-Fortress', '超级要塞'), 'IUGigaN_': ('', '超级要塞（纳米核心）'),
    'IUMCV_': ('', '帝国基地车'), 'IUMecha_': ('Mecha Tengu', '天狗机甲'), 'IUNano1_': ('', '纳米核心（建筑）'),
    'IUNano2_': ('', '纳米核心（防御）'), 'IUNano3_': ('', '纳米核心（科技）'), 'IUOreCo_': ('', '帝国矿车'),
    'IURocke_': ('Rocket Angel', '火箭天使'), 'IUSeaWi_': ('Sea-Wing', '海翼'), 'IUShogu_': ('Shogun Battleship', '将军战舰'),
    'IUSteel_': ('Steel Ronin', '钢铁浪人'), 'IUStrik_': ('Striker-VX', '鹰击者VX'), 'IUSudde_': ('Sudden Transport', '突击运输车'),
    'IUTankb_': ('Tankbuster', '坦克杀手'), 'IUTsuna_': ('Tsunami Tank', '海啸坦克'), 'IUWaveF_': ('Wave-Force Artillery', '波能炮'),
    'IUYariM_': ('Yari Mini-Sub', '长矛潜艇'), 'JUBurst_': ('Burst Drone', '爆裂无人机'), 'JUEngin_': ('', '帝国工程师'),
    'JUImper_': ('Imperial Warrior', '帝国武士'), 'JUKingO_': ('King Oni', '鬼王'), 'JUNagin_': ('Naginata Cruiser', '薙刀巡洋舰'),
    'JUShino_': ('Shinobi', '忍者'), 'JUYurik_': ('Yuriko Omega', '百合子'),
}
PEOPLE = {'Giles': '吉尔利斯', 'Liss': '莉塞特', 'Warr': '华伦', 'Warren': '华伦', 'Kenj': '贤治', 'Kenji': '贤治',
          'Naom': '直美', 'Naomi': '直美', 'Shin': '晋三', 'Shinzo': '晋三', 'Mosk': '莫斯克文', 'Moskvin': '莫斯克文',
          'Oleg': '奥列格', 'Zhan': '扎娜', 'Zhana': '扎娜'}
COMMANDER = {'ACGiles_': '盟军 · 吉尔利斯', 'ACLiss_': '盟军 · 莉塞特', 'ACWarren_': '盟军 · 华伦',
             'CC_AUMaGil_': '盟军 · 吉尔利斯少校（起义时刻）', 'CHAT_AlliedSoldier': '士兵闲聊 · 盟军',
             'CHAT_SovietSoldier': '士兵闲聊 · 苏联', 'CHAT_ImperialSoldier': '士兵闲聊 · 帝国',
             'ECKenji_': '帝国 · 贤治', 'ECNaomi_': '帝国 · 直美', 'ECShinzo_': '帝国 · 晋三',
             'SCMoskvin_': '苏联 · 莫斯克文', 'SCOleg_': '苏联 · 奥列格', 'SCZhana_': '苏联 · 扎娜'}
ROLE = {'AlliedIntel': '情报官', 'SovietIntel': '情报官', 'ImperialIntel': '情报官', 'AlliedSoldier': '盟军士兵',
        'SovietSoldier': '苏联士兵', 'ImperialSoldier': '帝国士兵', 'Tanya': '谭雅', 'Tanay': '谭雅', 'Natasha': '娜塔莎',
        'Spy': '间谍', 'Scientist': '科学家', 'SovietEngineer': '苏联工程师', 'AlliedMCV': '盟军基地车',
        'Yuriko': '百合子', 'DrShimada': '岛田博士', 'Izumi': '泉', 'MajorGiles': '吉尔利斯少校', 'Apoc': '天启坦克',
        'Consc': '动员兵', 'Tesla': '磁暴步兵', 'Guardian': '守护者坦克', 'Hammer': '铁锤坦克', 'Tsunami': '海啸坦克',
        'TsunamiTank': '海啸坦克'}
AI_CMD = {'agi': '盟军 · 吉尔利斯', 'ali': '盟军 · 莉塞特', 'awa': '盟军 · 华伦', 'jke': '帝国 · 贤治', 'jna': '帝国 · 直美',
          'jsh': '帝国 · 晋三', 'smo': '苏联 · 莫斯克文', 'sol': '苏联 · 奥列格', 'szh': '苏联 · 扎娜'}
EVA = {'Aeva_': '盟军 EVA', 'Seva_': '苏联 EVA', 'Ieva_': '帝国 EVA', 'Aeve_': '盟军 EVA', 'Seve_': '苏联 EVA', 'Ieve_': '帝国 EVA'}


def unit_names():
    terms = textpack.Terms(os.path.join(ROOT, 'work', 'terms', 'term_map.json'))
    ui = {}
    for n in json.load(open(os.path.join(ROOT, 'work', 'terms', 'names.json'), encoding='utf-8')):
        ui.setdefault(n['en'].strip().lower(), terms.apply(n['zh_official']))
    return {g: ui.get(en.lower(), fallback) if en else fallback for g, (en, fallback) in UNITS.items()}


def mission_group(g):
    """MA03_Tanya -> ('剧情对白', '盟军战役 第3关 · 谭雅')."""
    if g in EVA:
        return '剧情对白', '指令播报 · ' + EVA[g]
    m = re.match(r'M([ASIE])In_$', g)
    if m:
        return '剧情对白', '单位介绍旁白 · ' + FACTION.get(m.group(1), '帝国')
    m = re.match(r'M([ASIETXY])(?:level)?(\d+)_(?:TEMP_)?(\w+?)(?:\d+|_PU\d+_\d+)?$', g)
    if not m:
        return '剧情对白', g
    side, n, who = m.group(1), int(m.group(2)), m.group(3)
    role = PEOPLE.get(who[2:], who) + '（副指挥官）' if who.startswith('Co') else ROLE.get(who, who)
    where = {'A': f'盟军战役 第{n}关', 'S': f'苏联战役 第{n}关', 'I': f'帝国战役 第{n}关', 'E': f'帝国战役 第{n}关',
             'T': f'教学关 第{n}关', 'X': f'起义时刻 · 盟军篇 第{n}关', 'Y': f'起义时刻 · 百合子篇 第{n}关'}[side]
    return '剧情对白', f'{where} · {role}'


def movie_group(movie, asset):
    up = asset.startswith('U_')
    m = re.match(r'([asj])(\d\d)(mm|th)\d\d$', movie)
    if m:
        f = {'a': '盟军', 's': '苏联', 'j': '帝国'}[m.group(1)]
        return '过场视频', f'{f}战役 第{int(m.group(2))}关 · ' + ('任务简报' if m.group(3) == 'mm' else '视频通话')
    m = re.match(r'([asj])fs(\d\d)$', movie)
    if m:
        return '过场视频', {'a': '盟军', 's': '苏联', 'j': '帝国'}[m.group(1)] + f'战役 · 剧情过场 {int(m.group(2))}'
    m = re.match(r'([asj])mb(\d\d)$', movie)
    if m:
        return '过场视频', {'a': '盟军', 's': '苏联', 'j': '帝国'}[m.group(1)] + f'战役 · 战况简报 {int(m.group(2))}'
    m = re.match(r'([asj][a-z]{2})(de|dg|gr|nd|td|tg|tv|dn|fstv)\d$', movie)
    if m and m.group(1) in AI_CMD:
        return '过场视频', '遭遇战 AI 指挥官 · ' + AI_CMD[m.group(1)]
    m = re.match(r'([asjy])th(\d\d)', movie)
    if m and up:
        f = {'a': '盟军篇', 's': '苏联篇', 'j': '帝国篇', 'y': '百合子篇'}[m.group(1)]
        return '过场视频', f'起义时刻 · {f} 第{int(m.group(2))}关 · 视频通话'
    m = re.match(r'ch(\d\d|xx|win)', movie)
    if m:
        return '过场视频', '起义时刻 · 指挥官挑战' + (f' 第{int(m.group(1))}关' if m.group(1).isdigit() else '')
    if re.match(r'(ffs|yfs|recapfs)', movie):
        return '过场视频', '起义时刻 · ' + ('百合子篇 剧情过场' if movie.startswith('yfs') else '剧情过场')
    if re.match(r'(ao|so)\d', movie):
        return '过场视频', ('盟军' if movie.startswith('a') else '苏联') + ' · 简报'
    if movie.startswith(('main_', 'miin_')):
        return '过场视频', '单位介绍'
    return '过场视频', ('起义时刻 · ' if up else '') + movie


def group_of(batch, r, names):
    g = r['group']
    if batch in ('allied', 'soviet', 'empire'):
        return '单位语音', {'allied': '盟军', 'soviet': '苏联', 'empire': '帝国'}[batch] + ' · ' + names.get(g, g.strip('_'))
    if batch == 'eva':
        return '战场播报', EVA.get(g, g)
    if batch == 'commander':
        return '指挥官', COMMANDER.get(g, g)
    return mission_group(g)


def entries(game, stream, comp_big):
    """All index rows for one game, using its AudioStream (asset -> cdata path / layout) and dist archives."""
    names = unit_names()
    rows = {}
    for b in VOICE:
        with open(os.path.join(ROOT, 'lines', b + '.csv'), encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                if r['zh'].strip():
                    rows.setdefault(r['asset'].lower(), (b, r))
    out = []
    dist = os.path.join(ROOT, 'dist', game)
    for b in VOICE:
        path = os.path.join(dist, comp_big.format(b))
        if not os.path.exists(path):
            continue
        inside = {n.lower() for n, _, _ in big.read_index(path)}
        for a in stream.assets:
            if a.cdata_path.lower() not in inside or a.short_name.lower() not in rows:
                continue
            batch, r = rows[a.short_name.lower()]
            sr, ch = stream._layout(a)
            kind = 'x' if stream.header_in_bin(a) is None else 's'
            cat, grp = group_of(batch, r, names)
            out.append([cat, grp, r['zh'], r['en'], game, comp_big.format(b), a.cdata_path, kind, sr, ch, 0, 0])
    movie_big = os.path.join(dist, comp_big.format('movie'))
    if os.path.exists(movie_big):
        inside = {n.lower() for n, _, _ in big.read_index(movie_big)}
        with open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                entry = 'data\\movies\\' + r['movie'] + '.snd'
                if not r['zh'].strip() or entry not in inside or game not in r['games'].split('+'):
                    continue
                start, slot = float(r['start']), max(float(r['dur']), float(r['slot'] or r['dur']))
                cat, grp = movie_group(r['movie'], r['asset'])
                out.append([cat, grp, r['zh'], r['en'], game, comp_big.format('movie'), entry, 'm', 0, 0,
                            round(max(0.0, start - 0.1), 2), round(min(slot, 12.0) + 0.3, 2)])
    return out


def write(files_dir, rows_by_game, games):
    """files_dir/listen_index.json for the games of one edition; a line in both games is listed once."""
    seen, lines = set(), []
    for g in games:
        for e in rows_by_game.get(g, []):
            key = (e[0], e[2], e[3], e[1])
            if key in seen:
                continue
            seen.add(key)
            lines.append(e)
    order = {'单位语音': 0, '战场播报': 1, '指挥官': 2, '剧情对白': 3, '过场视频': 4}
    rank = ['盟军', '苏联', '帝国', '教学关', '单位介绍', '指令播报', '士兵闲聊', '遭遇战', '起义时刻']

    def natural(s):   # 盟军 / 苏联 / 帝国 first, and 第2关 before 第10关
        r = next((i for i, w in enumerate(rank) if s.startswith(w)), len(rank))
        return f'{r:02d}' + re.sub(r'\d+', lambda m: m.group(0).zfill(4), s)
    lines.sort(key=lambda e: (order.get(e[0], 9), natural(e[1]), e[6], e[10]))
    with open(os.path.join(files_dir, 'listen_index.json'), 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'lines': lines}, f, ensure_ascii=False, separators=(',', ':'))
    return len(lines)
