"""Short-sentence pilot for one movie (the short-drama practice): does rewriting long lines as short spoken clauses
with explicit pauses, and generating them clause by clause, give better dubs than the released one-shot lines?

  venv=third_party/index-tts/.venv/Scripts/python.exe
  (write work/pilot_short/<movie>/script.json: {"lines": {asset: rewritten text}})
  $venv  -I -X utf8 tools/pilot_short.py generate sfs01   # GPU, honours gpu_limit.json
  python -I -X utf8 tools/pilot_short.py pick     sfs01   # Whisper -> B/, C/, report.csv
  python -I -X utf8 tools/pilot_short.py render   sfs01   # the movie three times + per-line table, blind page

A: released dubs. B: the rewritten line in one call. C: the rewritten line cut at 。！？…… into clauses, each
generated and picked on its own, joined with a pause that fits the mark (0.28 s, 0.45 s after ……). Speaker and
emotion references, pronunciation rules and the per-movie EQ are the released ones (dub.py, pick.py), so only the
text and the cutting differ.
"""
import csv
import json
import os
import random
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
TAKES_B, TAKES_C = 4, 3
GAP = {'…': 0.45, '。': 0.28, '！': 0.28, '？': 0.28}


def out_dir(mv):
    return os.path.join(ROOT, 'work', 'pilot_short', mv)


def script(mv):
    return json.load(open(os.path.join(out_dir(mv), 'script.json'), encoding='utf-8'))['lines']


def movie_lines(mv):
    rows = [r for r in csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig'))
            if r['movie'] == mv and r['zh'].strip()]
    game = rows[0]['games'].split('+')[0]
    return [r for r in rows if r['games'].split('+')[0] == game]


def clauses(text):
    """'你也看到了。我们的处境……非常糟糕。' -> ['你也看到了。', '我们的处境……', '非常糟糕。']"""
    parts = re.findall(r'.+?(?:……|[。！？]+|$)', text)
    return [p for p in (x.strip() for x in parts) if p.strip('。！？…，, ')]


# ---------------------------------------------------------------- generate (index-tts venv)
def generate(mv):
    import dub
    units = json.load(open(os.path.join(ROOT, 'units.json'), encoding='utf-8'))
    unit = units['movie']
    src = os.path.abspath(os.path.join(ROOT, unit['ref_dir']))
    min_ref = unit.get('min_ref', dub.MIN_REF_SECONDS)
    same_actor = json.load(open(os.path.join(ROOT, unit['same_actor']), encoding='utf-8')) if unit.get('same_actor') else None
    override = json.load(open(os.path.join(ROOT, unit['ref_override']), encoding='utf-8')) if unit.get('ref_override') else None
    rows = {r['asset']: r for r in movie_lines(mv)}
    prefix = next(p for p in unit['prefixes'] if next(iter(rows)).lower().startswith(p.lower()))
    fallback = {prefix: dub.longest_clip(src, prefix, set(rows))}
    lines = script(mv)
    os.chdir(dub.TTS_DIR)
    sys.path.insert(0, dub.TTS_DIR)
    import torch
    from ra3voice import throttle
    throttle.setup(torch)
    from indextts.infer_v2 import IndexTTS2
    tts = IndexTTS2(cfg_path='checkpoints/config.yaml', model_dir='checkpoints', use_fp16=True,
                    use_cuda_kernel=False, use_qwen_emo=False)
    for asset, text in lines.items():
        spk = dub.speaker_ref(src, prefix, asset, fallback, min_ref, same_actor, override)
        emo = os.path.join(src, asset + '.wav')
        emo = emo if os.path.exists(emo) else spk
        jobs = [(os.path.join('B', f'{asset}_{k}.wav'), text) for k in range(TAKES_B)]
        for i, c in enumerate(clauses(text)):
            jobs += [(os.path.join('C', f'{asset}_c{i}_{k}.wav'), c) for k in range(TAKES_C)]
        for rel, t in jobs:
            dst = os.path.join(out_dir(mv), 'takes', rel)
            if os.path.exists(dst):
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with throttle.work():
                tts.infer(spk_audio_prompt=spk, text=dub.tts_text(t, asset), output_path=dst,
                          emo_audio_prompt=emo, emo_alpha=0.6)
        print('done', asset, flush=True)
    print('FINISHED generate', flush=True)


# ---------------------------------------------------------------- pick (system python: Whisper)
def pick(mv):
    import torch
    from transformers import pipeline
    import pick as base
    from ra3voice import audio_io, eq, pauses, throttle
    throttle.setup(torch)
    rows = {r['asset']: r for r in movie_lines(mv)}
    lines = script(mv)
    takes = os.path.join(out_dir(mv), 'takes')
    asr = pipeline('automatic-speech-recognition', model=base.MODEL, dtype=torch.float16, device='cuda:0')

    def score(path, text, want_sec):
        x = base.trim(audio_io.load_mono(path, base.SR), base.SR)
        x16 = audio_io.load_mono(path, 16000)
        with throttle.work():
            hyp = asr({'raw': base.trim(x16, 16000).astype(np.float32), 'sampling_rate': 16000},
                      generate_kwargs={'language': 'zh', 'task': 'transcribe'})['text'].strip()
        e = base.cer(text, hyp)
        n_pause, _ = pauses.extra(base.trim(x16, 16000), 16000, text)
        sec = len(x) / base.SR
        return dict(audio=x, hyp=hyp, cer=e, pauses=n_pause, sec=sec,
                    usual=base.PAUSE_PENALTY * n_pause + max(0.0, sec / want_sec - 1.3) + e)

    chosen = {'B': {}, 'C': {}}
    report = []
    for asset, text in lines.items():
        orig_sec = float(rows[asset]['seconds'])
        bs = [score(os.path.join(takes, 'B', f'{asset}_{k}.wav'), text, orig_sec) for k in range(TAKES_B)]
        b = min([s for s in bs if s['cer'] <= 0.2] or bs, key=lambda s: s['usual'])
        chosen['B'][asset] = b['audio']
        parts, c_cer, c_pause = [], [], 0
        cl = clauses(text)
        for i, c in enumerate(cl):
            share = orig_sec * len(c) / max(1, len(text))
            cs = [score(os.path.join(takes, 'C', f'{asset}_c{i}_{k}.wav'), c, max(share, 0.6)) for k in range(TAKES_C)]
            best = min([s for s in cs if s['cer'] <= 0.2] or cs, key=lambda s: s['usual'])
            parts.append(best['audio'])
            if i < len(cl) - 1:
                parts.append(np.zeros(int(GAP.get(c.rstrip()[-1], 0.2) * base.SR), dtype=best['audio'].dtype))
            c_cer.append(best['cer'])
            c_pause += best['pauses']
        chosen['C'][asset] = np.concatenate(parts)
        report.append({'asset': asset, 'zh': rows[asset]['zh'], 'short': text, 'orig_s': orig_sec,
                       'B_s': round(b['sec'], 2), 'B_cer': round(b['cer'], 2), 'B_pauses': b['pauses'], 'B_heard': b['hyp'],
                       'C_s': round(len(chosen['C'][asset]) / base.SR, 2), 'C_cer': round(float(np.mean(c_cer)), 2),
                       'C_pauses': c_pause, 'clauses': len(cl)})
        print(asset, report[-1]['B_s'], report[-1]['C_s'], flush=True)
    # the released per-movie EQ (pick.py: one curve per movie prefix), designed for each version on its own takes
    names = list(lines)
    orig = [audio_io.load_mono(os.path.join(ROOT, 'original', 'movie', a + '.wav'), base.SR) for a in names]
    for v, got in chosen.items():
        taps = eq.design(orig, [got[a] for a in names], base.SR)
        d = os.path.join(out_dir(mv), v)
        os.makedirs(d, exist_ok=True)
        for a in names:
            y = eq.apply(got[a], taps)
            y = y * min(1.0, 0.98 / max(float(np.max(np.abs(y))), 1e-9))
            audio_io.save_wav(os.path.join(d, a + '.wav'), audio_io.to_int16(y), base.SR)
    qc = {r['asset']: r for r in csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie_qc.csv'), encoding='utf-8-sig'))}
    for r in report:
        q = qc.get(r['asset'], {})
        r.update(A_s=q.get('new_s'), A_cer=q.get('cer'), A_pauses=q.get('pauses'))
    with open(os.path.join(out_dir(mv), 'report.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(report[0].keys()))
        w.writeheader()
        w.writerows(report)
    tot = lambda k: sum(float(r[k] or 0) for r in report)
    print(f"seconds  orig {tot('orig_s'):.1f}  A {tot('A_s'):.1f}  B {tot('B_s'):.1f}  C {tot('C_s'):.1f}")
    print(f"pauses   A {tot('A_pauses'):.0f}  B {tot('B_pauses'):.0f}  C {tot('C_pauses'):.0f}   "
          f"cer A {tot('A_cer') / len(report):.3f}  B {tot('B_cer') / len(report):.3f}  C {tot('C_cer') / len(report):.3f}")


# ---------------------------------------------------------------- render (system python, ffmpeg)
def render(mv):
    import shutil
    import subprocess
    import html
    import make_demo as md
    from ra3voice import audio_io, big, movie
    import ra3cv_loader
    ra3cv = ra3cv_loader.load()
    md.OUT = out = out_dir(mv)
    for f in ('bhei01b.ttf',):
        shutil.copyfile(os.path.join(ROOT, 'third_party', 'fonts', 'out', f), os.path.join(out, 'font_b.ttf'))
    rows = movie_lines(mv)
    game = rows[0]['games'].split('+')[0]
    gdir = ra3cv.GAMES[game]
    name = 'data\\movies\\' + mv + '.snd'
    snd = big.read_files(os.path.join(gdir, 'Data', 'EnglishMovieAudio.big'), [name])[name]
    voc = np.load(os.path.join(ROOT, 'work', 'sep', game, mv + '.npy'))
    shift = ra3cv.movie_offsets()
    lines = script(mv)
    text = {'A': {r['asset']: r['zh'] for r in rows}, 'B': lines, 'C': lines}
    dirs = {'A': os.path.join(ROOT, 'voices', 'movie'), 'B': os.path.join(out, 'B'), 'C': os.path.join(out, 'C')}
    order = ['A', 'B', 'C']
    random.Random().shuffle(order)
    key = dict(zip('XYZ', order))
    json.dump(key, open(os.path.join(out, 'answer_key.json'), 'w', encoding='utf-8'))
    video = os.path.join(gdir, 'Data', 'Movies', mv.upper() + '.vp6')
    for label, v in key.items():
        placed = sorted((max(0.0, float(r['start']) + shift.get(r['asset'], 0.0)), float(r['dur']),
                         audio_io.load_mono(os.path.join(dirs[v], r['asset'] + '.wav'), movie.SR)) for r in rows)
        new = movie.mix(snd, movie.prepare(snd, placed, voc), voc)
        open(os.path.join(out, f'{label}.snd'), 'wb').write(new)
        subprocess.run([md.VGM, '-o', os.path.join(out, f'{label}.wav'), os.path.join(out, f'{label}.snd')],
                       capture_output=True, check=True)
        mix = md.DOWNMIX6 if movie.eaxa.channels(new) == 6 else 'pan=stereo|FL=c0|FR=c1'
        subs = md.subs_file([(float(r['start']), float(r['dur']), text[v][r['asset']].replace('……', '…'))
                             for r in rows], 0, f'{label}.ass')
        md.ff(['-i', video, '-i', f'{label}.wav', '-filter_complex',
               f'[0:v]scale={md.W}:{md.H}:flags=lanczos,setsar=1,subtitles={label}.ass:fontsdir=.[v];[1:a]{mix},{md.LOUD}[a]',
               '-map', '[v]', '-map', '[a]', '-shortest'] + md.ENC + [f'{label}.mp4'])
        for r in rows:   # per-line clips for the table
            md.ff(['-i', os.path.join(dirs[v], r['asset'] + '.wav'), '-c:a', 'libmp3lame', '-b:a', '128k',
                   f"{label}_{r['asset']}.mp3"])
    body = ''.join(
        f"<tr><td>{html.escape(r['en'])}</td>"
        + ''.join(f"<td><div class=t>{html.escape(text[key[l]][r['asset']])}</div>"
                  f"<audio controls preload=none src='{l}_{r['asset']}.mp3'></audio></td>" for l in 'XYZ')
        + '</tr>' for r in rows)
    page = f'''<!doctype html><meta charset=utf-8><title>短句试点</title>
<style>body{{font-family:"Microsoft YaHei UI",sans-serif;background:#15171b;color:#ddd;margin:24px}}video{{width:100%;max-width:960px;margin:6px 0 24px}}
h2{{color:#e8a33d}}td{{padding:6px;border-bottom:1px solid #333;vertical-align:top}}.t{{font-size:15px;margin-bottom:4px}}audio{{width:200px;height:30px}}</style>
<h1>{mv}：同一段过场，三个版本</h1>
<p>X / Y / Z 顺序随机。一个是现在发布的版本，另外两个用了短剧的做法（口语短句 + 明确停顿；其中一个还逐句拆开生成再拼接）。
先看整段视频，按「自然、像不像这个角色、停顿和节奏、口型时间」排个序；下面的表可以逐句对比。答案在 answer_key.json，听完再看。</p>
{''.join(f'<h2>{l}</h2><video controls preload=metadata src="{l}.mp4"></video>' for l in 'XYZ')}
<table><tr><th>原文</th><th>X</th><th>Y</th><th>Z</th></tr>{body}</table>'''
    open(os.path.join(out, 'index.html'), 'w', encoding='utf-8').write(page)
    print('->', os.path.join(out, 'index.html'))


if __name__ == '__main__':
    {'generate': generate, 'pick': pick, 'render': render}[sys.argv[1]](sys.argv[2])
