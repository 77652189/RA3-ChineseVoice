"""Listening page for what changed since v1.0.2 (work/review/index.html): pronunciation fixes, movie redubs with
the actor's own line next to the old and new dub, and newly dubbed adjutant lines.

  python -I -X utf8 tools/review_page.py
"""
import csv
import html
import json
import os
import sys

import lameenc
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ra3voice import audio_io  # noqa: E402

OUT = os.path.join(ROOT, 'work', 'review')


def mp3(name, path, sr=44100):
    x = audio_io.load_mono(path, sr)
    x = x / (np.abs(x).max() + 1e-9) * 0.9
    e = lameenc.Encoder()
    e.set_bit_rate(128)
    e.set_in_sample_rate(sr)
    e.set_channels(1)
    e.set_quality(2)
    open(os.path.join(OUT, name), 'wb').write(e.encode((x * 32767).astype('<i2').tobytes()) + e.flush())
    return name


def rows(batch):
    with open(os.path.join(ROOT, 'lines', batch + '.csv'), encoding='utf-8-sig') as f:
        return {r['asset']: r for r in csv.DictReader(f)}


def cell(src):
    return f'<td><audio controls preload=none src="{src}"></audio></td>' if src else '<td></td>'


def main():
    os.makedirs(OUT, exist_ok=True)
    page = ['<!doctype html><meta charset=utf-8><title>1.0.2 之后的改动试听</title><style>body{font-family:"Microsoft YaHei UI",'
            'sans-serif;background:#15171b;color:#ddd;margin:24px;max-width:1100px}td,th{padding:6px 8px;border-bottom:1px solid #333;'
            'text-align:left}audio{width:190px;height:30px}.en{color:#999;font-size:13px}h2{color:#e8a33d;margin-top:32px}'
            '</style><h1>1.0.2 之后的改动（未发布）</h1>']
    # 1. pronunciation
    t = json.load(open(os.path.join(ROOT, 'work', 'terms', 'dan4_redub.json'), encoding='utf-8'))
    page.append('<h2>「弹」的读音（配音时按「蛋」念，字幕不变）</h2><table><tr><th>台词</th><th>旧</th><th>新</th></tr>')
    for b, assets in t.items():
        if b == 'mission':
            continue
        lines = rows(b)
        for a in assets:
            old = mp3(f'{a}_old.mp3', os.path.join(ROOT, 'archive', 'dan4_redub', b, 'voices', a + '.wav'))
            new = mp3(f'{a}_new.mp3', os.path.join(ROOT, 'voices', b, a + '.wav'))
            page.append(f'<tr><td>{html.escape(lines[a]["zh"])}<div class=en>{a}</div></td>{cell(old)}{cell(new)}</tr>')
    page.append('</table>')
    # 2. movie redubs: the biggest gains in similarity to the actor
    kb = [r for r in csv.DictReader(open(os.path.join(ROOT, 'work', 'voice_audit', 'keep_better.csv'), encoding='utf-8-sig'))
          if r['kept'] == 'new']
    kb.sort(key=lambda r: float(r['old_sim']) - float(r['new_sim']))
    mv = rows('movie')
    page.append('<h2>过场重配（参考音改为从演员开口处截取）：提升最大的 12 句</h2>'
                '<table><tr><th>台词</th><th>演员原声</th><th>旧</th><th>新</th></tr>')
    for r in kb[:12]:
        a = r['asset']
        ref = mp3(f'{a}_ref.mp3', os.path.join(ROOT, 'original', 'movie_clean', a + '.wav'))
        old = mp3(f'{a}_old.mp3', os.path.join(ROOT, 'archive', 'movie_redub_onset_refs', 'voices', a + '.wav'))
        new = mp3(f'{a}_new.mp3', os.path.join(ROOT, 'voices', 'movie', a + '.wav'))
        page.append(f'<tr><td>{html.escape(mv[a]["zh"])}<div class=en>{html.escape(mv[a]["en"])} · 像本人 '
                    f'{r["old_sim"]} → {r["new_sim"]}</div></td>{cell(ref)}{cell(old)}{cell(new)}</tr>')
    page.append('</table>')
    # 3. adjutant lines that stayed English (misspelled file names)
    ev = rows('eva')
    page.append('<h2>新补配的副官台词（原来是英文）</h2><table><tr><th>台词</th><th>英文原声</th><th>中文</th></tr>')
    for a in ('Svea_UltraNagnticSatellteReady', 'Svea_MagnticSingularityReady', 'Svea_RedAlertAct', 'Ivea_RedAlertAct',
              'Ieve_SecurityPointGranted'):
        en = mp3(f'{a}_en.mp3', os.path.join(ROOT, 'original', 'eva', a + '.wav'))
        zh = mp3(f'{a}_zh.mp3', os.path.join(ROOT, 'voices', 'eva', a + '.wav'))
        page.append(f'<tr><td>{html.escape(ev[a]["zh"])}<div class=en>{html.escape(ev[a]["en"])}</div></td>{cell(en)}{cell(zh)}</tr>')
    page.append('</table>')
    # 4. still doubtful: pitch and fingerprint both off the actor, and no same-actor reference found to fix them
    doubt = os.path.join(ROOT, 'work', 'voice_audit', 'doubtful.json')
    if os.path.exists(doubt):
        page.append('<h2>还拿不准的几句（音高和声纹都不像演员，自动方法修不了）：请听一下配音是不是这个角色</h2>'
                    '<table><tr><th>台词</th><th>演员原声</th><th>现在的配音</th></tr>')
        for a in json.load(open(doubt, encoding='utf-8')):
            ref = mp3(f'{a}_ref.mp3', os.path.join(ROOT, 'original', 'movie_clean', a + '.wav'))
            cur = mp3(f'{a}_cur.mp3', os.path.join(ROOT, 'voices', 'movie', a + '.wav'))
            page.append(f'<tr><td>{html.escape(mv[a]["zh"])}<div class=en>{html.escape(mv[a]["en"])} · {a}</div></td>'
                        f'{cell(ref)}{cell(cur)}</tr>')
        page.append('</table>')
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write('\n'.join(page))
    print('->', os.path.join(OUT, 'index.html'))


if __name__ == '__main__':
    main()
