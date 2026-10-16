"""Mechanical effects on the clean dubs (run with the IndexTTS venv python, needs librosa).

  .../python tools/fx.py audition giga_fortress     A/B page with every preset on a few sample lines
  .../python tools/fx.py apply giga_fortress [P2]   clean/<unit> + preset -> voices/<unit>
                                                    (no preset: per-group choice from units.json "fx")

"semitones": "auto" shifts each voice group to the original's median pitch (pYIN); groups whose
originals are too unvoiced to measure get 0.
"""
import argparse
import html
import json
import os
import shutil
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io, fx  # noqa: E402

SR = 48000
SAMPLES = {'giga_fortress': ['IUGigaF_voiSelecta', 'IUGigaF_voiSelAira', 'IUGigaF_voiAttackd',
                             'IUGigaF_voiSelUndd', 'IUGigaF_voiCreateb', 'IUGigaN_VoiCrea']}


def median_f0(paths):
    import librosa
    f0s, voiced = [], []
    for p in paths:
        x = audio_io.load_mono(p, 24000)
        f0, vf, _ = librosa.pyin(x, fmin=60, fmax=500, sr=24000, frame_length=1024)
        f0s.append(f0[vf])
        voiced.append(vf.mean())
    f = np.concatenate(f0s)
    return (float(np.median(f)) if len(f) else 0.0), float(np.median(voiced))


def group_shifts(unit, prefixes):
    cache = os.path.join(ROOT, 'lines', f'{unit}_fx.json')
    if os.path.exists(cache):
        return json.load(open(cache, encoding='utf-8'))
    out = {}
    for p in prefixes:
        names = sorted(n[:-4] for n in os.listdir(os.path.join(ROOT, 'clean', unit)) if n.lower().startswith(p.lower()))
        fo, vo = median_f0([os.path.join(ROOT, 'original', unit, n + '.wav') for n in names])
        fn, vn = median_f0([os.path.join(ROOT, 'clean', unit, n + '.wav') for n in names])
        st = round(12 * np.log2(fo / fn), 1) if vo > 0.2 and vn > 0.2 and fo and fn else 0.0
        out[p] = {'orig_f0': round(fo, 1), 'new_f0': round(fn, 1), 'orig_voiced': round(vo, 2), 'semitones': st}
        print(p, out[p])
    json.dump(out, open(cache, 'w', encoding='utf-8'), indent=1)
    return out


def chain_for(preset, shift):
    return [[n, {k: (shift if v == 'auto' else v) for k, v in prm.items()}] for n, prm in preset['chain']]


def process(unit, name, preset, shifts, prefixes):
    prefix = next(p for p in prefixes if name.lower().startswith(p.lower()))
    x = audio_io.load_mono(os.path.join(ROOT, 'clean', unit, name + '.wav'), SR).astype(np.float64)
    return fx.apply_chain(x, SR, chain_for(preset, shifts[prefix]['semitones']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['audition', 'apply'])
    ap.add_argument('unit')
    ap.add_argument('preset', nargs='?')
    a = ap.parse_args()
    presets = json.load(open(os.path.join(ROOT, 'fx_presets.json'), encoding='utf-8'))
    units = json.load(open(os.path.join(ROOT, 'units.json'), encoding='utf-8'))
    prefixes = units[a.unit]['prefixes']
    in_use = [presets[a.preset]] if a.preset else (list(presets.values()) if a.cmd == 'audition'
                                                   else [presets[units[a.unit].get('fx', {}).get(p, 'P0')] for p in prefixes])
    needs_pitch = any(v == 'auto' for pr in in_use for _, prm in pr['chain'] for v in prm.values())
    # pitch measurement (pYIN over every clip) is slow, so only run it when a chosen preset shifts pitch
    shifts = group_shifts(a.unit, prefixes) if needs_pitch else {p: {'semitones': 0} for p in prefixes}

    if a.cmd == 'apply':
        out = os.path.join(ROOT, 'voices', a.unit)
        os.makedirs(out, exist_ok=True)
        # preset per voice group: CLI preset for all, else units.json "fx": {prefix: preset}
        chosen = units[a.unit].get('fx', {})
        names = sorted(n[:-4] for n in os.listdir(os.path.join(ROOT, 'clean', a.unit)) if n.endswith('.wav'))
        for n in names:
            prefix = next(p for p in prefixes if n.lower().startswith(p.lower()))
            pid = a.preset or chosen.get(prefix, 'P0')
            if not presets[pid]['chain']:
                # no effect: copy the bytes. Re-encoding through float shifts every sample a hair (x 32767/32768),
                # and a rerun then touched every released line (all movies in the next patch)
                shutil.copyfile(os.path.join(ROOT, 'clean', a.unit, n + '.wav'), os.path.join(out, n + '.wav'))
                continue
            audio_io.save_wav(os.path.join(out, n + '.wav'), audio_io.to_int16(process(a.unit, n, presets[pid], shifts, prefixes)), SR)
        print(f'{len(names)} clips -> {out}  presets: {a.preset or chosen}')
        return

    base = os.path.join(ROOT, 'preview', 'fx')
    names = SAMPLES[a.unit]
    for pid in presets:
        os.makedirs(os.path.join(base, pid), exist_ok=True)
    for n in names:
        ref = (audio_io.load_mono(os.path.join(ROOT, 'original', a.unit, n + '.wav'), SR) * 32768).astype(np.int16)
        outs = {pid: audio_io.match_level(process(a.unit, n, p, shifts, prefixes), ref) for pid, p in presets.items()}
        level = min(audio_io.rms(y) for y in outs.values())  # equal loudness so presets compare fairly
        for pid, y in outs.items():
            audio_io.save_wav(os.path.join(base, pid, n + '.wav'), audio_io.to_int16(y * level / audio_io.rms(y)), SR)
    import csv
    zh = {r['asset']: r for r in csv.DictReader(open(os.path.join(ROOT, 'lines', f'{a.unit}.csv'), encoding='utf-8-sig'))}
    cols = ''.join(f'<th>{pid}<br><small>{html.escape(p["label"])}</small></th>' for pid, p in presets.items())
    rows = ''.join(
        f'<tr><td><b>{html.escape(zh[n]["zh"])}</b><br><small>{html.escape(zh[n]["en"])}</small><br><code>{n}</code></td>'
        f'<td><audio controls preload="none" src="orig/{n}.wav"></audio></td>'
        + ''.join(f'<td><audio controls preload="none" src="fx/{pid}/{n}.wav"></audio></td>' for pid in presets)
        + '</tr>' for n in names)
    info = '；'.join(f'{p}: 原版 {v["orig_f0"]}Hz / 中文 {v["new_f0"]}Hz → 升 {v["semitones"]} 半音' for p, v in shifts.items())
    page = f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>音效方案对比</title><style>body{{font:14px system-ui,sans-serif;margin:0;padding:16px;background:#111;color:#ddd}}
.wrap{{overflow-x:auto}}table{{border-collapse:collapse}}td,th{{border-bottom:1px solid #333;padding:6px;vertical-align:top;text-align:left}}
th{{background:#222;font-weight:600}}small{{color:#999}}code{{color:#8ab4f8;font-size:11px}}audio{{width:170px;height:32px}}</style>
<h2 style="font-size:18px;margin:0 0 4px">机械音效方案对比</h2>
<p style="color:#999;margin:0 0 12px">每行一句台词，左边是原版，往右是各方案。表格可以左右滑动。音高测量：{html.escape(info)}</p>
<div class="wrap"><table><tr><th>台词</th><th>原版</th>{cols}</tr>{rows}</table></div>'''
    open(os.path.join(ROOT, 'preview', 'fx.html'), 'w', encoding='utf-8').write(page)
    print('->', os.path.join(ROOT, 'preview', 'fx.html'))


if __name__ == '__main__':
    main()
