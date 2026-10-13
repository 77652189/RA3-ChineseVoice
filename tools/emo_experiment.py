"""A/B/C listening test for emotional delivery in movie lines (run with the IndexTTS venv python).

  third_party/index-tts/.venv/Scripts/python tools/emo_experiment.py ASSET [ASSET ...]

A: clean reference, emo_alpha 0.6 (the setting used so far)
B: clean reference, emo_alpha 1.0
C: emotion from IndexTTS2's text emotion model only (emotion inferred from the Chinese line; IndexTTS2
   drops the audio emotion reference in this mode). The Qwen emotion model runs on the CPU first, so the
   TTS stays inside the gpu_limit.json VRAM cap; its vectors are passed as emo_vector.
Writes work/emo_test/<asset>_{orig,A,B,C}.wav and work/emo_test/index.html.
"""
import csv
import html
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TTS_DIR = os.path.join(ROOT, 'third_party', 'index-tts')
OUT = os.path.join(ROOT, 'work', 'emo_test')
REF = os.path.join(ROOT, 'original', 'movie_clean')
VARIANTS = [('A', '现在的设置：干净参考，情感强度 0.6', dict(emo_alpha=0.6)),
            ('B', '干净参考，情感强度 1.0', dict(emo_alpha=1.0)),
            ('C', '只按台词文字判断情绪（不参考原声语气）', dict(emo_alpha=1.0))]


def text_emotions(texts):
    """{text: 8-dim emotion vector} from IndexTTS2's QwenEmotion, loaded on the CPU."""
    import transformers
    from indextts import infer_v2
    orig = transformers.AutoModelForCausalLM.from_pretrained

    def on_cpu(*a, **kw):
        kw.update(device_map='cpu', torch_dtype='float32')
        return orig(*a, **kw)
    infer_v2.AutoModelForCausalLM.from_pretrained = on_cpu
    q = infer_v2.QwenEmotion(os.path.join('checkpoints', 'qwen0.6bemo4-merge'))
    out = {t: list(q.inference(t).values()) for t in texts}
    infer_v2.AutoModelForCausalLM.from_pretrained = orig
    del q
    return out


def main(assets):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig') as f:
        rows = {r['asset']: r for r in csv.DictReader(f)}
    os.chdir(TTS_DIR)
    sys.path.insert(0, TTS_DIR)
    sys.path.insert(0, ROOT)
    import torch
    from ra3voice import throttle
    throttle.setup(torch)
    from indextts.infer_v2 import IndexTTS2
    emos = text_emotions([rows[a]['zh'] for a in assets])
    tts = IndexTTS2(cfg_path='checkpoints/config.yaml', model_dir='checkpoints', use_fp16=True,
                    use_cuda_kernel=False, use_qwen_emo=False)
    cards = []
    for a in assets:
        r = rows[a]
        ref = os.path.join(REF, a + '.wav')
        shutil.copyfile(os.path.join(ROOT, 'original', 'movie', a + '.wav'), os.path.join(OUT, a + '_orig.wav'))
        for tag, _, kw in VARIANTS:
            dst = os.path.join(OUT, f'{a}_{tag}.wav')
            if not os.path.exists(dst):
                extra = {'emo_vector': emos[r['zh']]} if tag == 'C' else {'emo_audio_prompt': ref}
                with throttle.work():
                    tts.infer(spk_audio_prompt=ref, text=r['zh'], output_path=dst, **extra, **kw)
        cards.append((a, r))
        print('done', a, flush=True)
    css = ('body{font:15px system-ui,sans-serif;background:#111;color:#ddd;margin:0;padding:20px;max-width:900px}'
           '.c{background:#1c1f24;border-radius:8px;padding:14px 16px;margin:12px 0}.zh{font-size:19px;color:#fff;margin:4px 0}'
           '.en{color:#999;font-size:13px}.row{display:flex;align-items:center;gap:10px;margin:6px 0}.row b{width:24px}'
           '.row span{width:240px;color:#aaa;font-size:13px}audio{height:32px}')
    body = ''.join(
        f'<div class="c"><code>{html.escape(a)}</code><div class="zh">{html.escape(r["zh"])}</div>'
        f'<div class="en">{html.escape(r["en"])}</div>'
        f'<div class="row"><b>原</b><span>英文原声</span><audio controls preload="none" src="{a}_orig.wav"></audio></div>'
        + ''.join(f'<div class="row"><b>{t}</b><span>{html.escape(d)}</span>'
                  f'<audio controls preload="none" src="{a}_{t}.wav"></audio></div>' for t, d, _ in VARIANTS)
        + '</div>' for a, r in cards)
    with open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(f'<!doctype html><meta charset="utf-8"><title>情感对比试听</title><style>{css}</style>'
                f'<h2>情感表达对比：苏联开篇</h2><p>每句先听英文原声，再听 A / B / C，选出最接近原版情绪、又不夸张的那一档。</p>{body}')
    print('->', os.path.join(OUT, 'index.html'))


if __name__ == '__main__':
    main(sys.argv[1:])
