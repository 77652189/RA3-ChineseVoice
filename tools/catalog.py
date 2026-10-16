"""Build the dubbing catalog for both games.

  python tools/catalog.py

Selects unit voice lines and EVA announcements from RA3 and Uprising, splits them into batches
(allied / soviet / empire / eva), extracts the originals to original/<batch>/ and writes
lines/<batch>.csv (keeping any existing en/zh text) plus the batch entries in units.json.
Death screams (Voi*Die*) are left out and keep the original audio. Crash, fall and fear lines are shouted
sentences (pilots going down, Tengu/Rocket Angel falls, Natasha) and are dubbed like any other line.
"""
import csv
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io, snr                         # noqa: E402
from ra3voice.game import AudioStream, chain_for_game        # noqa: E402

GAMES = {
    'uprising': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3 Uprising',
    'ra3': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3',
}
UNIT_RE = re.compile(r'^(?P<group>[AJIS]U[A-Za-z0-9]+?_)[Vv]oi(?P<cat>[A-Za-z0-9]*)$')   # digits too: Tanya's VoiAtkC4Ba
# EA misspelled a few adjutant files: Svea_UltraNagnticSatellteReady (the level-3 magnetic satellite), Svea_ / Ivea_RedAlertAct
EVA_RE = re.compile(r'^(?P<group>[ASI]eva_|Svea_|Ivea_)', re.I)
# spoken lines whose file name lacks the _Voi marker (found by walking the games' *Voice* audio events):
# the Tesla Tank's select picks these two now and then
UNNAMED_VOICE = {'sutesla_seltnka', 'sutesla_seltnkb'}
NONVERBAL_RE = re.compile(r'die', re.I)    # crash / fal / fear carry words: checked with Whisper, see tools/nonverbal_probe.py
# co-commanders (ACGiles_, SCMoskvin_, ECKenji_ ...), soldier chatter, Commander Challenge Giles, UI chat
COMMANDER_RE = re.compile(r'^(?P<group>(?:AC|SC|EC)[A-Z][a-z]+_|CC_[A-Za-z]+_|CHAT_[A-Za-z]+?(?=\d)|UIChat_)')
FIELDS = ['asset', 'group', 'games', 'seconds', 'en', 'zh', 'note']


def batch_of(name):
    if EVA_RE.match(name):
        return 'eva'
    if COMMANDER_RE.match(name):
        return 'commander'
    return {'A': 'allied', 'S': 'soviet', 'J': 'empire', 'I': 'empire'}[name[0]]


def select(asset_name):
    m = EVA_RE.match(asset_name) or COMMANDER_RE.match(asset_name)
    if m:
        return m['group']
    if asset_name.lower() in UNNAMED_VOICE:
        return asset_name.split('_')[0] + '_'
    m = UNIT_RE.match(asset_name)
    if not m:
        return None
    cat = re.sub(r'[a-z]$', '', m['cat'])  # drop the take letter
    if NONVERBAL_RE.search(cat):
        return None
    return m['group']


def old_rows():
    rows = {}
    for p in glob.glob(os.path.join(ROOT, 'lines', '*.csv')):
        if p.endswith('_qc.csv'):
            continue
        with open(p, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                rows[r['asset'].lower()] = r
    return rows


def main():
    streams = {g: AudioStream(chain_for_game(d)) for g, d in GAMES.items()}
    picked = {}  # lower name -> dict
    for g, s in streams.items():
        for a in s.assets:
            grp = select(a.short_name)
            if not grp:
                continue
            e = picked.setdefault(a.short_name.lower(), {'asset': a.short_name, 'group': grp, 'src': {}})
            e['src'][g] = a
    old = old_rows()
    batches = {}
    differ = 0
    for key, e in sorted(picked.items()):
        src = e['src']
        if len(src) == 2 and src['uprising'].inst_hash != src['ra3'].inst_hash:
            differ += 1
        e['games'] = '+'.join(sorted(src))
        batches.setdefault(batch_of(e['asset']), []).append(e)

    units = json.load(open(os.path.join(ROOT, 'units.json'), encoding='utf-8'))
    for b, items in batches.items():
        out_dir = os.path.join(ROOT, 'original', b)
        os.makedirs(out_dir, exist_ok=True)
        rows = []
        # read originals game by game (prefer Uprising's copy when both exist)
        for g in ('uprising', 'ra3'):
            todo = [e for e in items if g in e['src'] and 'pcm' not in e
                    and (g == 'uprising' or 'uprising' not in e['src'])]
            blobs = streams[g].read_cdata([e['src'][g] for e in todo])
            for e in todo:
                try:
                    pcm, sr = snr.decode(blobs[e['src'][g].short_name])
                except ValueError as err:
                    print('skip', e['asset'], err)
                    e['pcm'] = None
                    continue
                e['pcm'] = True
                audio_io.save_wav(os.path.join(out_dir, e['asset'] + '.wav'), pcm, sr)
                e['seconds'] = f'{len(pcm) / sr:.2f}'
        for e in items:
            if not e.get('pcm'):
                continue
            o = old.get(e['asset'].lower(), {})
            rows.append({'asset': e['asset'], 'group': e['group'], 'games': e['games'], 'seconds': e['seconds'],
                         'en': o.get('en', ''), 'zh': o.get('zh', ''), 'note': o.get('note', '')})
        with open(os.path.join(ROOT, 'lines', f'{b}.csv'), 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        groups = sorted({r['group'] for r in rows})
        units[b] = {'name_zh': {'allied': '盟军', 'soviet': '苏联', 'empire': '帝国', 'eva': '播报', 'commander': '指挥官'}[b],
                    'prefixes': groups, 'fx': {}}
        print(f'{b}: {len(rows)} clips, {len(groups)} voice groups')
    units.pop('giga_fortress', None)
    json.dump(units, open(os.path.join(ROOT, 'units.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('assets in both games with different audio:', differ)


if __name__ == '__main__':
    main()
