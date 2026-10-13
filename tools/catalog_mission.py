"""Catalog the streamed (EALayer3) dialogue of both games as batch `mission`.

  python tools/catalog_mission.py

Covers mission dialogue (MA/MS/MI/ME/MY/MT/MX..), unit introductions (MAIn_/MSIn_/MIIn_) and the
EVA directive lines that are streamed. Test leftovers (TEMP_*, RA3_CinematicExcerpt*, the
Uprising WA* weapon test clips) are skipped.
Originals are decoded with vgmstream to original/mission/<asset>.wav (mono; Uprising's copy when an
asset exists in both games). lines/mission.csv gets the official English subtitle (DIALOGEVENT:<asset>)
as `en` and the official Traditional Chinese subtitle, converted to simplified mainland wording, as
`zh_official`; existing `zh` / `note` values are kept. Rows without subtitles get en='' (Whisper fills
them, see tools/transcribe.py).
"""
import csv
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io, csf, textpack               # noqa: E402
from ra3voice.game import AudioStream, chain_for_game        # noqa: E402

GAMES = {
    'uprising': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3 Uprising',
    'ra3': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3',
}
BATCH = 'mission'
SKIP_RE = re.compile(r'^(TEMP_|RA3_|WA)', re.I)
GROUP_RES = [re.compile(r'^(?P<g>M[A-Z]{1,2}In_)'),                       # unit introductions (one narrator)
             re.compile(r'^(?P<g>[ASI]ev[ae]_)'),                         # EVA directives
             re.compile(r'^(?P<g>M[A-Za-z]{1,6}\d*_[A-Za-z]+?)(?=\d|$)')]  # MA01_AlliedIntel, MXlevel1_Apoc
FIELDS = ['asset', 'group', 'games', 'seconds', 'en', 'zh_official', 'zh', 'note']
STRINGS = 'data\\gamestrings.csf'


def group_of(name):
    for r in GROUP_RES:
        m = r.match(name)
        if m:
            return m['g']
    return name


def subtitles(game_dir, lang):
    chain = chain_for_game(game_dir, lang)
    out = {}
    for n in [STRINGS, 'data\\gamestrings_temp.csf']:
        if n in chain.where:
            for k, v in csf.parse(chain.read([n])[n]).items():
                if k.upper().startswith('DIALOGEVENT:'):
                    out.setdefault(k.upper()[len('DIALOGEVENT:'):], v)
    return out


def clean_en(t):
    return t.lstrip('*').strip()


def main():
    streams = {g: AudioStream(chain_for_game(d)) for g, d in GAMES.items()}
    subs = {g: (subtitles(d, 'english'), subtitles(d, 'chinese_t')) for g, d in GAMES.items()}
    picked = {}
    for g, s in streams.items():
        for a in s.assets:
            if s.header_in_bin(a) is None or SKIP_RE.match(a.short_name):
                continue
            picked.setdefault(a.short_name.lower(), {'asset': a.short_name, 'src': {}})['src'][g] = a
    old = {}
    path = os.path.join(ROOT, 'lines', f'{BATCH}.csv')
    if os.path.exists(path):
        with open(path, encoding='utf-8-sig') as f:
            old = {r['asset'].lower(): r for r in csv.DictReader(f)}
    out_dir = os.path.join(ROOT, 'original', BATCH)
    os.makedirs(out_dir, exist_ok=True)

    def extract(e):
        g = 'uprising' if 'uprising' in e['src'] else 'ra3'
        a = e['src'][g]
        dst = os.path.join(out_dir, e['asset'] + '.wav')
        s = streams[g]
        if not os.path.exists(dst):
            pcm, sr = s.decode(a)
            audio_io.save_wav(dst, pcm, sr)
        e['seconds'] = f'{s.num_samples(a) / s._layout(a)[0]:.2f}'
        e['game'] = g

    items = [picked[k] for k in sorted(picked)]
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(extract, items))
    rows = []
    for e in items:
        key = e['asset'].upper()
        order = [e['game']] + [g for g in e['src'] if g != e['game']]
        en = next((subs[g][0][key] for g in order if key in subs[g][0]), '')
        zt = next((subs[g][1][key] for g in order if key in subs[g][1]), '')
        o = old.get(e['asset'].lower(), {})
        rows.append({'asset': e['asset'], 'group': group_of(e['asset']), 'games': '+'.join(sorted(e['src'])),
                     'seconds': e['seconds'], 'en': clean_en(en) or o.get('en', ''),
                     'zh_official': textpack.to_simplified(zt).strip(), 'zh': o.get('zh', ''), 'note': o.get('note', '')})
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    units_path = os.path.join(ROOT, 'units.json')
    units = json.load(open(units_path, encoding='utf-8'))
    units[BATCH] = {'name_zh': '剧情对白', 'prefixes': sorted({r['group'] for r in rows}), 'fx': {}}
    json.dump(units, open(units_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    n_sub = sum(1 for r in rows if r['zh_official'])
    mins = sum(float(r['seconds']) for r in rows) / 60
    print(f'{BATCH}: {len(rows)} clips ({mins:.0f} min), {n_sub} with official subtitles, '
          f'{len(units[BATCH]["prefixes"])} voice groups')


if __name__ == '__main__':
    main()
