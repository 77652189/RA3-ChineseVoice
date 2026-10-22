"""Blind timbre test: our released movie dubs (IndexTTS2) against GPT-SoVITS zero-shot (v5dev now, v5pro when it is out).

  python -I -X utf8 tools/gsv_ab.py select                    -> work/gsv_ab/set.json (any python with soundfile)
  gsv=third_party/gpt-sovits/.venv/Scripts/python.exe
  $gsv -I -X utf8 tools/gsv_ab.py dub v5dev [--takes 4]       -> work/gsv_ab/v5dev/<asset>_<k>.wav
  python -I -X utf8 tools/gsv_ab.py page v5dev [v5pro ...]    -> work/gsv_ab/index.html (+ key.json, not shown on the page)

The set: the 20 movie lines least like the actor by CAMPPlus (work/qa/features_all.csv; lines of 8+ characters and
2+ s, at most one per scene) plus
5 ordinary ones as a control (a new engine must not make good lines worse). CAMPPlus is the encoder IndexTTS2 itself
conditions on, so it only picks the questions; a person judges. GPT-SoVITS needs a 3-10 s reference and its
transcript: the line's own clean original, else the hand-picked / same-actor one dub.py uses (when that one fits).
Takes are picked the way pick.py picks ours (Whisper CER + extra pauses + overlong); the page shuffles the columns.
"""
import argparse
import csv
import glob
import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
OUT = os.path.join(ROOT, 'work', 'gsv_ab')
REF = os.path.join(ROOT, 'original', 'movie_clean')
DUB = os.path.join(ROOT, 'voices', 'movie')
GSV = os.path.join(ROOT, 'third_party', 'gpt-sovits')
N_BAD, N_CONTROL, CONTROL_SIM = 20, 5, (0.62, 0.72)
MIN_CHARS, MIN_ACTOR_S = 8, 2.0   # CAMPPlus is unreliable on short clips: one-word lines all score low
REF_S = (3.0, 10.0)            # GPT-SoVITS refuses references outside this
MIN_OUT_S, RETRIES = 0.4, 6
MAX_CER = 0.5                  # an engine whose best take is worse than this failed the line: kept off the page


def load_json(rel):
    p = os.path.join(ROOT, rel)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}


def select():
    import soundfile as sf
    feats = [r for r in csv.DictReader(open(os.path.join(ROOT, 'work', 'qa', 'features_all.csv'), encoding='utf-8-sig'))
             if r['spk_sim'] and int(r['chars']) >= MIN_CHARS and float(r['actor_s']) >= MIN_ACTOR_S]
    lines = {r['asset']: r for r in csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig'))}
    same_actor, override = load_json('work/speakers/fallback.json'), load_json('work/speakers/ref_override.json')

    def dur(a):
        p = os.path.join(REF, a + '.wav')
        return sf.info(p).duration if os.path.exists(p) else 0.0

    def ref_for(a):
        for r in (override.get(a), a, same_actor.get(a)):
            if r and r in lines and REF_S[0] <= dur(r) <= REF_S[1]:
                return r
        return None

    def take(pool, n, used):
        out = []
        for f in pool:
            scene, ref = f['asset'].rsplit('_', 1)[0], ref_for(f['asset'])
            if scene in used or not ref or not os.path.exists(os.path.join(DUB, f['asset'] + '.wav')):
                continue
            used.add(scene)
            l = lines[f['asset']]
            out.append({'asset': f['asset'], 'zh': l['zh'], 'en': l['en'], 'ref': ref, 'ref_text': lines[ref]['en'],
                        'spk_sim': float(f['spk_sim'])})
            if len(out) == n:
                break
        return out

    used = set()
    bad = take(sorted(feats, key=lambda f: float(f['spk_sim'])), N_BAD, used)
    mid = [f for f in feats if CONTROL_SIM[0] <= float(f['spk_sim']) <= CONTROL_SIM[1]]
    random.Random(7).shuffle(mid)
    control = take(mid, N_CONTROL, used)
    for x in bad:
        x['band'] = 'bad'
    for x in control:
        x['band'] = 'control'
    os.makedirs(OUT, exist_ok=True)
    json.dump(bad + control, open(os.path.join(OUT, 'set.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(bad)} bad + {len(control)} control -> {os.path.join(OUT, "set.json")}')


def gsv_text(text, asset):
    """pronounce.json rules that are plain homophones (toned pinyin is IndexTTS2's own token set)."""
    for rule in load_json('work/terms/pronounce.json') or []:
        if re.search('[A-Za-z]', rule['to']) or ('assets' in rule and asset not in rule['assets']):
            continue
        text = re.sub(rule['pattern'], rule['to'], text)
    return text


def dub(tag, takes):
    items = json.load(open(os.path.join(OUT, 'set.json'), encoding='utf-8'))
    out = os.path.join(OUT, tag)
    os.makedirs(out, exist_ok=True)
    os.chdir(GSV)
    sys.path[:0] = [GSV, os.path.join(GSV, 'GPT_SoVITS')]
    import numpy as np
    import soundfile as sf
    import torch
    from ra3voice import throttle
    throttle.setup(torch, owner='gsv_ab')
    from TTS_infer_pack.TTS import TTS, TTS_Config
    cfg = TTS_Config({'custom': {
        'device': 'cuda', 'is_half': True, 'version': tag,
        't2s_weights_path': 'GPT_SoVITS/pretrained_models/s1v3.ckpt',
        'vits_weights_path': f'GPT_SoVITS/pretrained_models/gsv-v5-pretrained/s2G{tag}.pth',
        'bert_base_path': 'GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large',
        'cnhuhbert_base_path': 'GPT_SoVITS/pretrained_models/chinese-hubert-base'}})
    tts = TTS(cfg)
    made = failed = 0
    for it in items:
        for k in range(takes):
            dst = os.path.join(out, f"{it['asset']}_{k}.wav")
            if os.path.exists(dst):
                continue
            try:
                # the GPT sometimes stops at once (a 0.2 s clip): try other seeds
                for seed in range(1000 + k, 1000 + k + RETRIES * takes, takes):
                    with throttle.work():
                        chunks = list(tts.run({'text': gsv_text(it['zh'], it['asset']), 'text_lang': 'zh',
                                               'ref_audio_path': os.path.join(REF, it['ref'] + '.wav'),
                                               'prompt_text': it['ref_text'], 'prompt_lang': 'en',
                                               'text_split_method': 'cut0',   # whole line: cut5 adds 0.3 s gaps
                                               'batch_size': 1, 'seed': seed, 'parallel_infer': False}))
                    sr, y = chunks[0][0], np.concatenate([c[1] for c in chunks])
                    if len(y) >= MIN_OUT_S * sr:
                        break
                    print(f"EMPTY {it['asset']}_{k} seed {seed}", flush=True)
                else:
                    raise RuntimeError(f'empty after {RETRIES} seeds')
                sf.write(dst, y, sr)
                made += 1
            except Exception as e:      # one bad line must not stop the set
                failed += 1
                print(f"FAILED {it['asset']}_{k}: {e!r}", flush=True)
    print(f'FINISHED {tag} made={made} failed={failed}', flush=True)


def page(tags):
    import html
    import numpy as np
    import torch
    from transformers import pipeline
    import choose_takes
    import pick
    from ra3voice import audio_io, pauses, throttle
    items = json.load(open(os.path.join(OUT, 'set.json'), encoding='utf-8'))
    choose_takes.OUT = OUT
    throttle.setup(torch, owner='gsv_ab')
    asr = pipeline('automatic-speech-recognition', model=pick.MODEL, torch_dtype=torch.float16, device='cuda:0')
    cache_path = os.path.join(OUT, 'asr_cache.json')
    cache = json.load(open(cache_path, encoding='utf-8')) if os.path.exists(cache_path) else {}
    rng = random.Random(11)
    key, body = {}, []
    for it in items:
        a, orig = it['asset'], os.path.join(REF, it['asset'] + '.wav')
        orig_s = len(pick.trim(audio_io.load_mono(orig, 16000), 16000)) / 16000
        cols = {'current': os.path.join(DUB, a + '.wav')}
        for tag in tags:
            best = None
            for p in sorted(glob.glob(os.path.join(OUT, tag, a + '_*.wav'))):
                x = pick.trim(audio_io.load_mono(p, 16000), 16000)
                if len(x) < MIN_OUT_S * 16000:    # Whisper makes up a sentence for silence
                    continue
                ck = f'{tag}/{os.path.basename(p)}|{os.path.getsize(p)}'
                if ck not in cache:
                    with throttle.work():
                        cache[ck] = asr({'raw': x.astype(np.float32), 'sampling_rate': 16000},
                                        generate_kwargs={'language': 'zh', 'task': 'transcribe'})['text'].strip()
                e = pick.cer(it['zh'], cache[ck])
                score = e + pick.PAUSE_PENALTY * pauses.extra(x, 16000, it['zh'])[0] + max(0.0, len(x) / 16000 / orig_s - 1.3)
                if best is None or score < best[0]:
                    best = (score, p, e)
            if best:
                it.setdefault('cer', {})[tag] = round(best[2], 2)
            if best and best[2] <= MAX_CER:
                cols[tag] = best[1]
            else:
                it.setdefault('failed', []).append(tag)
                print(f'{tag} failed {a}', flush=True)
        if len(cols) < 2:
            continue
        n = len(body) + 1
        names = list(cols)
        rng.shuffle(names)
        key[a] = names
        letters = 'ABCD'[:len(names)]
        au = lambda name, path: f'<audio controls preload=none src="{choose_takes.mp3(name, path)}"></audio>'
        players = ''.join(f'<td><b>{L}</b> {au(f"{a}_{L}.mp3", cols[nm])}</td>' for L, nm in zip(letters, names))
        radios = lambda q: ''.join(f'<label><input type=radio name="{a}|{q}" value="{v}"> {v}</label> '
                                   for v in list(letters) + ['差不多'])
        body.append(f'<tr data-a="{a}"><td class=n>{n}</td><td><div class=zh>{html.escape(it["zh"])}</div>'
                    f'<div class=en>{html.escape(it["en"])} · {a}</div></td>'
                    f'<td><b>原版</b> {au(f"{a}_en.mp3", orig)}</td>{players}'
                    f'<td><div>音色最像原版：{radios("音色")}</div><div>语气最好：{radios("语气")}</div></td></tr>')
    json.dump(cache, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    json.dump({'tags': tags, 'columns': key, 'items': items},
              open(os.path.join(OUT, 'key.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    doc = f'''<!doctype html><meta charset=utf-8><title>配音音色盲测</title>
<style>
:root{{--bg:#15171b;--fg:#ddd;--mut:#999;--line:#333;--hi:#e8b04a}}
@media (prefers-color-scheme: light){{:root{{--bg:#fafafa;--fg:#222;--mut:#666;--line:#ddd;--hi:#b7791f}}}}
body{{font-family:"Microsoft YaHei UI",sans-serif;background:var(--bg);color:var(--fg);margin:24px}}
table{{border-collapse:collapse;width:100%}}td{{padding:8px;border-bottom:1px solid var(--line);vertical-align:middle}}
.zh{{font-size:18px}}.en{{color:var(--mut);font-size:13px;margin-top:2px}}.n{{color:var(--mut)}}b{{color:var(--hi)}}
audio{{width:190px;height:32px;vertical-align:middle}}label{{margin-right:6px;white-space:nowrap}}
#bar{{position:sticky;top:0;background:var(--bg);padding:10px 0;display:flex;gap:12px;align-items:center;z-index:1}}
button{{font-size:15px;padding:6px 14px}}
</style>
<h1>配音音色盲测（{len(body)} 句）</h1>
<p>每句先听「原版」，再听 A / B{" / C" if len(tags) > 1 else ""}。它们是不同方法配的中文，顺序每句打乱。
分别选音色最像原版演员的、语气最好的；听不出差别就选「差不多」。全部选完点「复制结果」发给我。</p>
<div id=bar><button id=copy>复制结果</button><span id=n></span></div>
<table>{chr(10).join(body)}</table>
<script>
const KEY='gsv-ab';let saved={{}};try{{saved=JSON.parse(localStorage.getItem(KEY)||'{{}}')}}catch(e){{}}
const inputs=[...document.querySelectorAll('input[type=radio]')];
function upd(){{const s={{}};inputs.filter(i=>i.checked).forEach(i=>s[i.name]=i.value);try{{localStorage.setItem(KEY,JSON.stringify(s))}}catch(e){{}}
const rows=document.querySelectorAll('tr[data-a]').length;document.getElementById('n').textContent='已选 '+Object.keys(s).length+' / '+rows*2;return s}}
inputs.forEach(i=>{{if(saved[i.name]===i.value)i.checked=true;i.onchange=upd}});upd();
document.getElementById('copy').onclick=async()=>{{const t='盲测结果 '+Object.entries(upd()).map(([k,v])=>k+'='+v).join(' ');
try{{await navigator.clipboard.writeText(t)}}catch(e){{prompt('复制下面这行',t)}}document.getElementById('copy').textContent='已复制'}};
</script>'''
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(doc)
    print('->', os.path.join(OUT, 'index.html'))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('select')
    d = sub.add_parser('dub')
    d.add_argument('tag', help='GPT-SoVITS version, e.g. v5dev')
    d.add_argument('--takes', type=int, default=4)
    p = sub.add_parser('page')
    p.add_argument('tags', nargs='+')
    args = ap.parse_args()
    if args.cmd == 'select':
        select()
    elif args.cmd == 'dub':
        dub(args.tag, args.takes)
    else:
        page(args.tags)


if __name__ == '__main__':
    main()
