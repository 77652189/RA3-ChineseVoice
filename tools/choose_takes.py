"""Let a person choose the delivery: for each line, the original, the current dub and the three candidate takes that
read correctly and move most like the original (pitch spread, loudness swings, pitch vs the speaker's usual).

  python -I -X utf8 tools/choose_takes.py page  BATCH A1 A2 ...   -> work/choose/index.html, work/choose/options.json
  python -I -X utf8 tools/choose_takes.py apply BATCH A1=B A2=C ... # keep only the chosen take, then pick.py --only

apply moves every other candidate of the line to archive/choose_rejected/ so that pick.py --only takes the chosen
one (EQ'd with its group as usual); the person's choice wins over the scores.
"""
import csv
import glob
import html
import json
import os
import shutil
import sys

import lameenc
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ra3voice import audio_io  # noqa: E402

OUT = os.path.join(ROOT, 'work', 'choose')
REF = {'movie': os.path.join(ROOT, 'original', 'movie_clean'), 'mission': os.path.join(ROOT, 'original', 'mission')}


def mp3(name, path):
    x = audio_io.load_mono(path, 44100)
    x = x / (np.abs(x).max() + 1e-9) * 0.9
    e = lameenc.Encoder()
    e.set_bit_rate(128)
    e.set_in_sample_rate(44100)
    e.set_channels(1)
    e.set_quality(2)
    open(os.path.join(OUT, name), 'wb').write(e.encode((x * 32767).astype('<i2').tobytes()) + e.flush())
    return name


def page(batch, assets):
    import torch
    from transformers import pipeline
    import pick as base
    from pilot_emotion import prosody
    from ra3voice import throttle
    throttle.setup(torch)
    os.makedirs(OUT, exist_ok=True)
    rows = {r['asset']: r for r in csv.DictReader(open(os.path.join(ROOT, 'lines', batch + '.csv'), encoding='utf-8-sig'))}
    asr = pipeline('automatic-speech-recognition', model=base.MODEL, dtype=torch.float16, device='cuda:0')
    options, html_rows = {}, []
    for a in assets:
        ref = audio_io.load_mono(os.path.join(REF[batch], a + '.wav'), 16000).astype(np.float32)
        spread_o, swing_o, f0_o = prosody(ref)
        scored = []
        for p in sorted(glob.glob(os.path.join(ROOT, 'candidates', batch, a + '_*.wav'))):
            x = base.trim(audio_io.load_mono(p, 16000), 16000).astype(np.float32)
            with throttle.work():
                hyp = asr({'raw': x, 'sampling_rate': 16000}, generate_kwargs={'language': 'zh', 'task': 'transcribe'})['text']
            e = base.cer(rows[a]['zh'], hyp)
            if e > 0.2:
                continue
            spread, swing, f0 = prosody(x)
            gap = (abs(spread - spread_o) / max(spread_o, 2.0) + abs(swing - swing_o) / max(swing_o, 3.0)
                   + (2 * abs(np.log2(f0 / f0_o)) if f0 and f0_o else 0))
            scored.append((e + 0.5 * gap, os.path.basename(p)))
        scored.sort()
        top = [t for _, t in scored[:3]]
        options[a] = dict(zip('ABC', top))
        cells = [mp3(f'{a}_orig.mp3', os.path.join(REF[batch], a + '.wav')),
                 mp3(f'{a}_cur.mp3', os.path.join(ROOT, 'voices', batch, a + '.wav'))]
        cells += [mp3(f'{a}_{k}.mp3', os.path.join(ROOT, 'candidates', batch, t)) for k, t in options[a].items()]
        html_rows.append(f'<tr><td><b>{html.escape(rows[a]["zh"])}</b><div class=en>{html.escape(rows[a]["en"])} · {a}</div></td>'
                         + ''.join(f'<td><audio controls preload=none src="{c}"></audio></td>' for c in cells) + '</tr>')
        print(a, options[a], flush=True)
    json.dump({'batch': batch, 'options': options}, open(os.path.join(OUT, 'options.json'), 'w'), indent=1)
    doc = ['<!doctype html><meta charset=utf-8><title>选语气</title><style>body{font-family:"Microsoft YaHei UI",sans-serif;'
           'background:#15171b;color:#ddd;margin:24px}td,th{padding:6px 8px;border-bottom:1px solid #333;text-align:left}'
           'audio{width:170px;height:30px}.en{color:#999;font-size:13px}</style><h1>每句选一个语气最合适的（A / B / C），'
           '都不行就说「都不行」</h1><table><tr><th>台词</th><th>演员原声</th><th>现在的配音</th><th>A</th><th>B</th><th>C</th></tr>']
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write('\n'.join(doc + html_rows + ['</table>']))
    print('->', os.path.join(OUT, 'index.html'))


def apply(batch, choices):
    opts = json.load(open(os.path.join(OUT, 'options.json'), encoding='utf-8'))['options']
    for c in choices:
        a, k = c.split('=')
        take = opts[a][k.upper()]
        keep = os.path.join(ROOT, 'candidates', batch, take)
        dst = os.path.join(ROOT, 'archive', 'choose_rejected', batch)
        os.makedirs(dst, exist_ok=True)
        for p in glob.glob(os.path.join(ROOT, 'candidates', batch, a + '_*.wav')):
            if os.path.normcase(p) != os.path.normcase(keep):
                shutil.move(p, dst)
        print(a, 'keeps', take)


if __name__ == '__main__':
    if sys.argv[1] == 'page':
        page(sys.argv[2], sys.argv[3:])
    else:
        apply(sys.argv[2], sys.argv[3:])
