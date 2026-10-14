"""Score IndexTTS candidates with Whisper (zh) and keep the best take per line.

  python tools/pick.py giga_fortress

Score = toneless-pinyin syllable error rate vs. the intended text
      + PAUSE_PENALTY per unexplained mid-sentence pause (ra3voice.pauses)
      + a penalty when the take is much longer than the original clip.
The winner is silence-trimmed, matching-EQ'd to the originals and written to clean/<unit>/<asset>.wav
(tools/fx.py adds effects -> voices/). Report: lines/<unit>_qc.csv; flag lists the reasons
(READ = mispronounced, PAUSE = extra pause, LONG = >1.6x and >0.5 s longer than the original).
Whisper results are cached per candidate file in lines/<unit>_asr_cache.json.
"""
import csv
import glob
import json
import os
import re
import sys

import numpy as np
import torch
from pypinyin import lazy_pinyin
from transformers import pipeline

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io, eq, pauses, throttle  # noqa: E402

MODEL = 'openai/whisper-large-v3'
SR = 48000
PAUSE_PENALTY = 0.3
PUNCT = re.compile(r'[\s，。！？、,.!?;；:："“”\'‘’…\-]')
EQ_SKIP_RE = re.compile(r'_[Vv]oi(Crash|Fal|Fear)')


# sentence particles Whisper writes interchangeably (啦/了/喽/咯) count as the same syllable
PARTICLES = {'la': 'le', 'lou': 'le', 'luo': 'le'}
# traditional forms Whisper uses whose pinyin differs from the simplified character in the script
TRAD = str.maketrans({'著': '着'})
DIGITS = '零一二三四五六七八九'
LATIN = {'omega': '欧米伽', 'delta': '德尔塔', 'alpha': '阿尔法', 'beta': '贝塔', 'x': '艾克斯', 'v': '威'}


def number_zh(n):
    """Arabic integer -> Chinese numerals, as the scripts write them (30 -> 三十, 25000 -> 两万五千)."""
    n = int(n)
    if n == 0:
        return '零'
    def below_10k(v):
        out, zero = '', False
        for unit, d in (('千', v // 1000 % 10), ('百', v // 100 % 10), ('十', v // 10 % 10), ('', v % 10)):
            if d:
                out += ('零' if zero and out else '') + DIGITS[d] + unit
                zero = False
            else:
                zero = True
        return out[1:] if out.startswith('一十') else out
    wan, rest = divmod(n, 10000)
    s = (below_10k(wan) + '万' if wan else '') + (('零' if wan and rest < 1000 else '') + below_10k(rest) if rest else '')
    return s.replace('二千', '两千').replace('二万', '两万')


def normalize_hyp(text):
    """Whisper writes numbers and Greek letters in Latin script; map them back before comparing sounds."""
    text = re.sub(r'\d+', lambda m: number_zh(m.group()), text.replace(',', '') if re.search(r'\d,\d', text) else text)
    text = text.translate(TRAD)
    return re.sub(r'[A-Za-z]+', lambda m: LATIN.get(m.group().lower(), m.group()), text)


def cer(ref, hyp):
    """Syllable error rate on toneless pinyin, so homophones and traditional characters count as correct."""
    a = [PARTICLES.get(p, p) for p in lazy_pinyin(PUNCT.sub('', ref))]
    b = [PARTICLES.get(p, p) for p in lazy_pinyin(PUNCT.sub('', normalize_hyp(hyp)))]
    if not a:
        return 0.0
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
    return d[len(b)] / len(a)


def trim(x, sr, thresh_db=-45, pad=0.04):
    if not len(x):
        return x
    win = max(1, int(0.01 * sr))
    env = np.sqrt(np.convolve(x.astype(np.float64) ** 2, np.ones(win) / win, mode='same'))
    on = np.where(env > env.max() * 10 ** (thresh_db / 20))[0]
    if not len(on):
        return x
    p = int(pad * sr)
    return x[max(0, on[0] - p):min(len(x), on[-1] + p)]


def main(unit):
    with open(os.path.join(ROOT, 'lines', f'{unit}.csv'), encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f) if r['zh'].strip()]
    cand_dir = os.path.join(ROOT, 'candidates', unit)
    out_dir = os.path.join(ROOT, 'clean', unit)
    os.makedirs(out_dir, exist_ok=True)
    throttle.setup(torch)
    asr = pipeline('automatic-speech-recognition', model=MODEL, torch_dtype=torch.float16, device='cuda:0')
    cache_path = os.path.join(ROOT, 'lines', f'{unit}_asr_cache.json')
    cache = json.load(open(cache_path, encoding='utf-8')) if os.path.exists(cache_path) else {}
    report, winners = [], {}
    for i, r in enumerate(rows, 1):
        orig_sec = float(r['seconds'])
        best = None
        for p in sorted(glob.glob(os.path.join(cand_dir, r['asset'] + '_*.wav'))):
            x = trim(audio_io.load_mono(p, 16000), 16000)
            key = f'{os.path.basename(p)}|{os.path.getsize(p)}|{int(os.path.getmtime(p))}'
            hyp = cache.get(key)
            if hyp is None:
                # long mission lines: Whisper sees 30 s windows, so chunk anything near that
                long_form = {'chunk_length_s': 30} if len(x) > 28 * 16000 else {}
                with throttle.work():
                    hyp = asr({'raw': x.astype(np.float32), 'sampling_rate': 16000}, **long_form,
                              generate_kwargs={'language': 'zh', 'task': 'transcribe'})['text'].strip()
                cache[key] = hyp
            e = cer(r['zh'], hyp)
            sec = len(x) / 16000
            n_pause, longest = pauses.extra(x, 16000, r['zh'])
            score = e + PAUSE_PENALTY * n_pause + max(0.0, sec / orig_sec - 1.3)
            if best is None or score < best[0]:
                best = (score, p, hyp, e, sec, n_pause, longest)
        if best is None:
            print('no candidates for', r['asset'])
            continue
        score, p, hyp, e, sec, n_pause, longest = best
        winners[r['asset']] = trim(audio_io.load_mono(p, SR), SR)
        reasons = [k for k, bad in (('READ', e > 0.2), ('PAUSE', n_pause > 0), ('LONG', sec / orig_sec > 1.6 and sec - orig_sec > 0.5)) if bad]
        flag = '+'.join(reasons)
        report.append({'asset': r['asset'], 'zh': r['zh'], 'heard': hyp, 'cer': f'{e:.2f}',
                       'pauses': n_pause, 'longest_gap': f'{longest:.2f}',
                       'orig_s': f'{orig_sec:.2f}', 'new_s': f'{sec:.2f}', 'take': os.path.basename(p), 'flag': flag})
        if i % 200 == 0:
            json.dump(cache, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False)
            print(f'PROGRESS pick {unit} {i}/{len(rows)}', flush=True)
    json.dump(cache, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False)
    # matching EQ per voice group (e.g. Giga Fortress vs. its Nanocore), then write voices/
    prefixes = json.load(open(os.path.join(ROOT, 'units.json'), encoding='utf-8'))[unit]['prefixes']
    for prefix in prefixes:
        names = [n for n in winners if n.lower().startswith(prefix.lower())]
        if not names:
            continue
        # shouted crash / fall / fear lines would bend the whole group's curve (and every released line with it):
        # they only receive the curve designed from the group's ordinary lines
        design = [n for n in names if not EQ_SKIP_RE.search(n)] or names
        orig = [audio_io.load_mono(os.path.join(ROOT, 'original', unit, n + '.wav'), SR) for n in design]
        taps = eq.design(orig, [winners[n] for n in design], SR)
        for n in names:
            y = eq.apply(winners[n], taps)
            y = y * min(1.0, 0.98 / max(float(np.max(np.abs(y))), 1e-9))
            audio_io.save_wav(os.path.join(out_dir, n + '.wav'), audio_io.to_int16(y), SR)
    with open(os.path.join(ROOT, 'lines', f'{unit}_qc.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(report[0].keys()))
        w.writeheader()
        w.writerows(report)
    n = {k: sum(1 for r in report if k in r['flag']) for k in ('READ', 'PAUSE', 'LONG')}
    print(f"{sum(1 for r in report if r['flag'])} / {len(report)} flagged for listening  {n}")


if __name__ == '__main__':
    main(sys.argv[1])
