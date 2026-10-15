"""Before/after audio samples for the player-facing Xiaoheihe post.

  python -I -X utf8 docs/article/make_xhh_samples.py

Writes work/xhh_samples/<id>_en.mp3, <id>_zh.mp3 and <id>_ab.mp3 (original, a short pause, then the Chinese dub)
plus index.html to pick from. Unit lines and EVA come from original/ and voices/ (the released takes); in-mission
video calls ("th" movies) are the whole movie soundtrack, original from the game's EnglishMovieAudio.big and the
dub from dist/<game>/CNVoice_movie.big, so music and effects are in both.
"""
import csv
import html
import os
import re
import sys

import lameenc
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ra3voice import audio_io, big, movie  # noqa: E402
import listen_index  # noqa: E402

OUT = os.path.join(ROOT, 'work', 'xhh_samples')
SR = 44100
GAMES = {'ra3': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3',
         'uprising': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3 Uprising'}

# well-known units first, then everything Uprising added
UNITS = ['AUTanya_', 'SUKirov_', 'SUApoca_', 'SUNatas_', 'JUYurik_', 'JUKingO_', 'IUShogu_', 'JUImper_', 'SUConsc_',
         'AUPeace_', 'AUMirag_', 'AUCentu_', 'IUMecha_', 'IURocke_', 'SUHamme_', 'AUGuard_', 'SUSickl_', 'JUShino_',
         'AUCryoL_', 'AUFutur_', 'AUHarbi_', 'AUPacif_', 'SUDesol_', 'SUGrind_', 'SUMorta_', 'SUReape_',
         'IUGigaF_', 'IUSteel_', 'IUArche_']
PER_UNIT = 3
EVA_KEYS = ['construction complete', 'unit ready', 'under attack', 'superweapon', 'chronosphere', 'iron curtain',
            'vacuum imploder', 'proton', 'psionic', 'reinforcements', 'insufficient funds', 'building', 'unit lost',
            'ore', 'launch']
PER_EVA_FACTION = 5
TH_PER_FACTION = 5


def qc_ok(batch):
    ok = set()
    for r in csv.DictReader(open(os.path.join(ROOT, 'lines', f'{batch}_qc.csv'), encoding='utf-8-sig')):
        if float(r['cer'] or 1) == 0 and not r['flag']:
            ok.add(r['asset'])
    return ok


def load(path):
    return audio_io.load_mono(path, SR).astype(np.float32)


def norm(x, peak=0.89):
    m = float(np.abs(x).max()) or 1.0
    return x * (peak / m)


def mp3(path, x):
    enc = lameenc.Encoder()
    enc.set_bit_rate(160)
    enc.set_in_sample_rate(SR)
    enc.set_channels(1 if x.ndim == 1 else x.shape[1])
    enc.set_quality(2)
    pcm = (np.clip(x, -1, 1) * 32767).astype('<i2')
    open(path, 'wb').write(enc.encode(pcm.tobytes()) + enc.flush())


def pair(item_id, en, zh):
    en, zh = norm(en), norm(zh)
    gap = np.zeros((int(0.6 * SR),) + en.shape[1:], np.float32)
    mp3(os.path.join(OUT, item_id + '_en.mp3'), en)
    mp3(os.path.join(OUT, item_id + '_zh.mp3'), zh)
    mp3(os.path.join(OUT, item_id + '_ab.mp3'), np.concatenate([en, gap, zh]))
    return len(en) / SR, len(zh) / SR


def unit_items(names):
    out = []
    for batch in ('allied', 'soviet', 'empire'):
        ok = qc_ok(batch)
        rows = list(csv.DictReader(open(os.path.join(ROOT, 'lines', f'{batch}.csv'), encoding='utf-8-sig')))
        for g in [u for u in UNITS if any(r['group'] == u for r in rows)]:
            cand = [r for r in rows if r['group'] == g and r['asset'] in ok and 0.8 <= float(r['seconds']) <= 3.5
                    and len(r['en'].split()) >= 2 and r['zh']]
            cand.sort(key=lambda r: (('Sel' not in r['asset'] and 'sel' not in r['asset']), -len(r['en'])))
            seen = set()
            for r in cand:
                if r['zh'] in seen:
                    continue
                seen.add(r['zh'])
                up = r['games'] == 'uprising'
                out.append(dict(id=r['asset'], cat='单位语音', who=names.get(g, g) + ('（起义时刻）' if up else ''),
                                en_text=r['en'], zh_text=r['zh'],
                                en=os.path.join(ROOT, 'original', batch, r['asset'] + '.wav'),
                                zh=os.path.join(ROOT, 'voices', batch, r['asset'] + '.wav')))
                if len(seen) == PER_UNIT:
                    break
    return out


def eva_items():
    ok = qc_ok('eva')
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'lines', 'eva.csv'), encoding='utf-8-sig')))
    out = []
    for pre, who in (('aeva_', '盟军 EVA'), ('seva_', '苏联 EVA'), ('ieva_', '帝国 EVA')):
        picked, seen = 0, set()
        for k in EVA_KEYS:
            for r in rows:
                if picked >= PER_EVA_FACTION:
                    break
                if r['asset'].lower().startswith(pre) and r['asset'] in ok and k in r['en'].lower() \
                        and r['zh'] not in seen and float(r['seconds']) <= 4:
                    seen.add(r['zh'])
                    picked += 1
                    out.append(dict(id=r['asset'], cat='EVA 播报', who=who, en_text=r['en'], zh_text=r['zh'],
                                    en=os.path.join(ROOT, 'original', 'eva', r['asset'] + '.wav'),
                                    zh=os.path.join(ROOT, 'voices', 'eva', r['asset'] + '.wav')))
    return out


def th_items():
    ok = qc_ok('movie')
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig')))
    by = {}
    for r in rows:
        if re.match(r'[asjy]\d\dth\d\d$|[asjy]th\d\d', r['movie']):
            by.setdefault((r['games'].split('+')[0], r['movie']), []).append(r)
    out, count = [], {}
    for (game, mv), lines in sorted(by.items()):
        if not (2 <= len(lines) <= 4) or not all(r['asset'] in ok for r in lines):
            continue
        end = max(float(r['start']) + float(r['dur']) for r in lines)
        if not 5 <= end <= 15:
            continue
        cat, grp = listen_index.movie_group(mv, lines[0]['asset'])
        side = grp.split(' ')[0]
        # one call per mission, so more characters show up
        if count.get(side, 0) >= TH_PER_FACTION or (side, grp) in count:
            continue
        count[side] = count.get(side, 0) + 1
        count[(side, grp)] = 1
        out.append(dict(id=mv, cat='视频通话', who=grp, game=game,
                        en_text=' / '.join(r['en'] for r in lines), zh_text=' / '.join(r['zh'] for r in lines)))
    return out


def movie_track(pack, name):
    x = movie.decode(big.read_files(pack, [name])[name]).astype(np.float32) / 32768
    if x.shape[1] == 6:          # 5.1 -> stereo: L/R plus centre (dialogue) and the surrounds
        l = x[:, 0] + 0.71 * x[:, 1] + 0.5 * x[:, 4]
        r = x[:, 2] + 0.71 * x[:, 1] + 0.5 * x[:, 5]
        x = np.stack([l, r], 1)
    elif x.shape[1] == 1:
        x = np.repeat(x, 2, 1)
    # 48 kHz -> 44.1 kHz
    t = np.arange(int(len(x) * SR / movie.SR)) * movie.SR / SR
    return np.stack([np.interp(t, np.arange(len(x)), x[:, c]) for c in range(2)], 1).astype(np.float32)


def main():
    os.makedirs(OUT, exist_ok=True)
    names = listen_index.unit_names()
    items = unit_items(names) + eva_items() + th_items()
    for it in items:
        if it['cat'] == '视频通话':
            entry = 'data\\movies\\' + it['id'] + '.snd'
            en = movie_track(os.path.join(GAMES[it['game']], 'Data', 'EnglishMovieAudio.big'), entry)
            zh = movie_track(os.path.join(ROOT, 'dist', it['game'], 'CNVoice_movie.big'), entry)
        else:
            en, zh = load(it['en']), load(it['zh'])
        it['en_s'], it['zh_s'] = pair(it['id'], en, zh)
    page = ['<!doctype html><meta charset=utf-8><title>小黑盒配音对比素材</title><style>',
            'body{font-family:"Microsoft YaHei UI",sans-serif;background:#15171b;color:#ddd;margin:20px;max-width:1100px}',
            'h2{color:#e8a33d}table{border-collapse:collapse;width:100%}td{padding:6px 8px;border-bottom:1px solid #333;'
            'vertical-align:middle}audio{height:30px;width:220px}.id{color:#888;font-size:12px}.zh{color:#fff}',
            '.en{color:#aaa}</style><h1>配音对比素材（挑你觉得效果最好的，告诉我编号）</h1>',
            '<p>每条：左边原版，中间中文，右边是「原版 → 中文」连播（准备上传小黑盒的就是这一版）。</p>']
    for cat in ('单位语音', 'EVA 播报', '视频通话'):
        page.append(f'<h2>{cat}</h2><table>')
        for n, it in enumerate([i for i in items if i['cat'] == cat], 1):
            page.append(f'<tr><td class=id>{cat[0]}{n}<br>{html.escape(it["id"])}</td><td>{html.escape(it["who"])}</td>'
                        f'<td><div class=en>{html.escape(it["en_text"])}</div><div class=zh>{html.escape(it["zh_text"])}</div></td>'
                        f'<td><audio controls preload=none src="{it["id"]}_en.mp3"></audio></td>'
                        f'<td><audio controls preload=none src="{it["id"]}_zh.mp3"></audio></td>'
                        f'<td><audio controls preload=none src="{it["id"]}_ab.mp3"></audio></td></tr>')
            it['label'] = f'{cat[0]}{n}'
        page.append('</table>')
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write('\n'.join(page))
    with open(os.path.join(OUT, 'items.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['label', 'id', 'cat', 'who', 'en', 'zh', 'en_s', 'zh_s'])
        for it in items:
            w.writerow([it['label'], it['id'], it['cat'], it['who'], it['en_text'], it['zh_text'],
                        f'{it["en_s"]:.1f}', f'{it["zh_s"]:.1f}'])
    print({c: sum(i['cat'] == c for i in items) for c in ('单位语音', 'EVA 播报', '视频通话')}, '->', OUT)


if __name__ == '__main__':
    main()
