"""Effort pilot: QA labels say "wrong tone" goes with dubs that sound much brighter / more forced than the actor
(qa_features effort_diff, AUC 0.86 on 8 labelled lines). Regenerate a random sample of such lines and pick the take
whose effort and pitch are closest to the actor's, then let a person compare old and new blind.

  venv=third_party/index-tts/.venv/Scripts/python.exe
  python -I -X utf8 tools/pilot_effort.py select            # 40 lines with effort_diff > 5 dB -> work/pilot_effort/lines.json
  $venv  -I -X utf8 tools/pilot_effort.py generate          # 6 takes each, same settings as dub.py (GPU, throttled)
  python -I -X utf8 tools/pilot_effort.py pick              # Whisper + actor match -> new/<asset>.wav, report.csv
  python -I -X utf8 tools/pilot_effort.py page              # blind old / new page

The new take gets the released line's EQ (designed from the released file against its own raw take), so old and
new differ only in the take.
"""
import csv
import json
import math
import os
import random
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
OUT = os.path.join(ROOT, 'work', 'pilot_effort')
TAKES, N, THRESH = 6, 40, 5.0


def lines():
    return json.load(open(os.path.join(OUT, 'lines.json'), encoding='utf-8'))


def select():
    feats = list(csv.DictReader(open(os.path.join(ROOT, 'work', 'qa', 'features_all.csv'), encoding='utf-8-sig')))
    hot = [r['asset'] for r in feats if float(r['effort_diff']) > THRESH]
    pick = sorted(random.Random(7).sample(hot, min(N, len(hot))))
    os.makedirs(OUT, exist_ok=True)
    json.dump(pick, open(os.path.join(OUT, 'lines.json'), 'w', encoding='utf-8'), indent=1)
    print(len(hot), 'over', THRESH, 'dB; sampled', len(pick))


def generate():
    import dub
    unit = json.load(open(os.path.join(ROOT, 'units.json'), encoding='utf-8'))['movie']
    src = os.path.abspath(os.path.join(ROOT, unit['ref_dir']))
    min_ref = unit.get('min_ref', dub.MIN_REF_SECONDS)
    same_actor = json.load(open(os.path.join(ROOT, unit['same_actor']), encoding='utf-8')) if unit.get('same_actor') else None
    override = json.load(open(os.path.join(ROOT, unit['ref_override']), encoding='utf-8')) if unit.get('ref_override') else None
    rows = {r['asset']: r for r in csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig'))}
    spoken = {a for a, r in rows.items() if r['zh'].strip()}
    todo = lines()
    os.chdir(dub.TTS_DIR)
    sys.path.insert(0, dub.TTS_DIR)
    import torch
    from ra3voice import throttle
    throttle.setup(torch)
    from indextts.infer_v2 import IndexTTS2
    tts = IndexTTS2(cfg_path='checkpoints/config.yaml', model_dir='checkpoints', use_fp16=True,
                    use_cuda_kernel=False, use_qwen_emo=False)
    fallback = {}
    for asset in todo:
        prefix = next(p for p in unit['prefixes'] if asset.lower().startswith(p.lower()))
        if prefix not in fallback:
            fallback[prefix] = dub.longest_clip(src, prefix, spoken)
        spk = dub.speaker_ref(src, prefix, asset, fallback, min_ref, same_actor, override)
        emo = os.path.join(src, asset + '.wav')
        for k in range(TAKES):
            dst = os.path.join(OUT, 'takes', f'{asset}_{k}.wav')
            if os.path.exists(dst):
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with throttle.work():
                tts.infer(spk_audio_prompt=spk, text=dub.tts_text(rows[asset]['zh'], asset), output_path=dst,
                          emo_audio_prompt=emo if os.path.exists(emo) else spk, emo_alpha=0.6)
        print('done', asset, flush=True)
    print('FINISHED generate', flush=True)


def actor_gap(m, act):
    """How far a measured take is from the actor: effort (dB / 3), pitch (log2 x 2), pitch spread (|log|)."""
    g = abs(m['effort'] - act['effort']) / 3
    if 'f0' in m and 'f0' in act:
        g += 2 * abs(math.log2(m['f0'] / act['f0']))
    if 'spread' in m and 'spread' in act:
        g += abs(math.log(max(m['spread'], 1.0) / max(act['spread'], 1.0)))
    return g


def pick():
    import torch
    from transformers import pipeline
    import pick as base
    import qa_features as qf
    from ra3voice import audio_io, eq, pauses, throttle
    throttle.setup(torch)
    rows = {r['asset']: r for r in csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig'))}
    qc = {r['asset']: r for r in csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie_qc.csv'), encoding='utf-8-sig'))}
    asr = pipeline('automatic-speech-recognition', model=base.MODEL, dtype=torch.float16, device='cuda:0')
    report = []
    os.makedirs(os.path.join(OUT, 'new'), exist_ok=True)
    for asset in lines():
        r = rows[asset]
        act = qf.measure(audio_io.load_mono(os.path.join(ROOT, 'original', 'movie_clean', asset + '.wav'), 16000).astype(np.float32))
        old_final = audio_io.load_mono(os.path.join(ROOT, 'voices', 'movie', asset + '.wav'), base.SR)
        old_raw = base.trim(audio_io.load_mono(os.path.join(ROOT, 'candidates', 'movie', qc[asset]['take']), base.SR), base.SR)
        taps = eq.design([old_final], [old_raw], base.SR)          # the released line's EQ
        scored = []
        for k in range(TAKES):
            p = os.path.join(OUT, 'takes', f'{asset}_{k}.wav')
            x = base.trim(audio_io.load_mono(p, base.SR), base.SR)
            x16 = base.trim(audio_io.load_mono(p, 16000), 16000).astype(np.float32)
            with throttle.work():
                hyp = asr({'raw': x16, 'sampling_rate': 16000}, generate_kwargs={'language': 'zh', 'task': 'transcribe'})['text']
            e = base.cer(r['zh'], hyp)
            n_pause, _ = pauses.extra(x16, 16000, r['zh'])
            y = eq.apply(x, taps)
            y = y * min(1.0, 0.98 / max(float(np.max(np.abs(y))), 1e-9))
            eqd = os.path.join(OUT, 'eqd', f'{asset}_{k}.wav')     # the take as it would ship, measured like the old one
            os.makedirs(os.path.dirname(eqd), exist_ok=True)
            audio_io.save_wav(eqd, audio_io.to_int16(y), base.SR)
            m = qf.measure(audio_io.load_mono(eqd, 16000).astype(np.float32))
            usual = base.PAUSE_PENALTY * n_pause + max(0.0, len(x) / base.SR / float(r['seconds']) - 1.3) + e
            scored.append(dict(k=k, cer=e, pauses=n_pause, usual=usual, gap=actor_gap(m, act), effort=m['effort'] - act['effort'], y=y))
        ok = [s for s in scored if s['cer'] <= 0.1 and s['pauses'] == 0] or [s for s in scored if s['cer'] <= 0.2] or scored
        best = min(ok, key=lambda s: s['usual'] + s['gap'])
        audio_io.save_wav(os.path.join(OUT, 'new', asset + '.wav'), audio_io.to_int16(best['y']), base.SR)
        old_m = qf.measure(audio_io.load_mono(os.path.join(ROOT, 'voices', 'movie', asset + '.wav'), 16000).astype(np.float32))
        report.append({'asset': asset, 'zh': r['zh'], 'take': best['k'], 'cer': round(best['cer'], 2), 'pauses': best['pauses'],
                       'old_effort': round(old_m['effort'] - act['effort'], 2), 'new_effort': round(best['effort'], 2),
                       'old_gap': round(actor_gap(old_m, act), 2), 'new_gap': round(best['gap'], 2)})
        print(asset, report[-1]['old_effort'], '->', report[-1]['new_effort'], flush=True)
    with open(os.path.join(OUT, 'report.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(report[0]))
        w.writeheader()
        w.writerows(report)


def page():
    import html
    import choose_takes
    choose_takes.OUT = OUT
    rows = {r['asset']: r for r in csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig'))}
    rng = random.Random()
    key, body = {}, []
    for i, a in enumerate(lines(), 1):
        new_is_a = rng.random() < 0.5
        key[a] = 'A' if new_is_a else 'B'
        en = choose_takes.mp3(f'{a}_en.mp3', os.path.join(ROOT, 'original', 'movie_clean', a + '.wav'))
        old = os.path.join(ROOT, 'voices', 'movie', a + '.wav')
        new = os.path.join(OUT, 'new', a + '.wav')
        fa = choose_takes.mp3(f'{a}_A.mp3', new if new_is_a else old)
        fb = choose_takes.mp3(f'{a}_B.mp3', old if new_is_a else new)
        opts = ''.join(f'<label><input type=radio name="{a}" value="{v}"> {v}</label> ' for v in ('A 更好', 'B 更好', '差不多'))
        body.append(f'<tr data-a="{a}"><td>{i}</td><td><div class=zh>{html.escape(rows[a]["zh"])}</div><div class=en>{html.escape(rows[a]["en"])}</div></td>'
                    f'<td><audio controls preload=none src="{en}"></audio></td><td><audio controls preload=none src="{fa}"></audio></td>'
                    f'<td><audio controls preload=none src="{fb}"></audio></td><td class=o>{opts}</td></tr>')
    json.dump(key, open(os.path.join(OUT, 'answer_key.json'), 'w', encoding='utf-8'), indent=1)
    doc = f'''<!doctype html><meta charset=utf-8><title>语气对比</title>
<style>:root{{--bg:#15171b;--fg:#ddd;--mut:#999;--line:#333}}@media (prefers-color-scheme: light){{:root{{--bg:#fafafa;--fg:#222;--mut:#666;--line:#ddd}}}}
body{{font-family:"Microsoft YaHei UI",sans-serif;background:var(--bg);color:var(--fg);margin:24px}}table{{border-collapse:collapse;width:100%}}
td,th{{padding:7px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}}.zh{{font-size:17px}}.en{{color:var(--mut);font-size:13px}}
audio{{width:190px;height:30px}}.o label{{white-space:nowrap;margin-right:8px}}#bar{{position:sticky;top:0;background:var(--bg);padding:10px 0}}button{{font-size:15px;padding:6px 14px}}</style>
<h1>语气对比（{len(key)} 句，盲听）</h1><p>每句先听演员原声，再听 A 和 B。一个是现在的配音，一个是新生成的，顺序随机。选语气更贴近演员、听着更自然的那个；分不出来就选「差不多」。完了点「复制结果」发给我。</p>
<div id=bar><button id=copy>复制结果</button> <span id=n></span></div>
<table><tr><th></th><th>台词</th><th>演员原声</th><th>A</th><th>B</th><th>选</th></tr>{"".join(body)}</table>
<script>const K='effort-ab';let s={{}};try{{s=JSON.parse(localStorage.getItem(K)||'{{}}')}}catch(e){{}}
const rows=[...document.querySelectorAll('tr[data-a]')];function st(){{const o={{}};rows.forEach(r=>{{const c=r.querySelector('input:checked');if(c)o[r.dataset.a]=c.value}});
document.getElementById('n').textContent='已选 '+Object.keys(o).length+' / '+rows.length;try{{localStorage.setItem(K,JSON.stringify(o))}}catch(e){{}}return o}}
rows.forEach(r=>{{const v=s[r.dataset.a];r.querySelectorAll('input').forEach(c=>{{if(c.value===v)c.checked=true;c.onchange=st}})}});st();
document.getElementById('copy').onclick=async()=>{{const o=st();const t='语气AB: '+Object.entries(o).map(([a,v])=>a+'='+v[0].replace('差','=')).join(' ');
try{{await navigator.clipboard.writeText(t)}}catch(e){{prompt('复制下面这行',t)}}document.getElementById('copy').textContent='已复制';}};</script>'''
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(doc)
    print('->', os.path.join(OUT, 'index.html'))


if __name__ == '__main__':
    {'select': select, 'generate': generate, 'pick': pick, 'page': page}[sys.argv[1]]()
