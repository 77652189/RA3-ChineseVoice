"""Which audio files in the games still speak English? (everything we do not dub, run through Whisper)

  python -I -X utf8 tools/english_audit.py          # GPU, honours gpu_limit.json; resumable
  -> work/english_audit/heard.json (cache) and work/english_audit/report.csv

Our catalog finds lines by name (UNIT_RE / EVA_RE ...), so misspelled or oddly named files slip through:
EA wrote Svea_UltraNagnticSatellteReady for the level-3 magnetic satellite and it stayed English until a
player noticed. This walks every asset of both games that is in no lines/*.csv, decodes it, and asks Whisper
what it hears. Sound effects make Whisper hallucinate stock phrases; those are flagged, not hidden.
"""
import csv
import json
import os
import re
import sys

from math import gcd

import numpy as np
from scipy.signal import resample_poly

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice.game import AudioStream, chain_for_game  # noqa: E402

GAMES = {'uprising': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3 Uprising',
         'ra3': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3'}
OUT = os.path.join(ROOT, 'work', 'english_audit')
MIN_SECONDS = 0.3
# what Whisper says over noise, music and silence
STOCK = re.compile(r"^\s*(thank you\.?|thanks for watching!?|bye\.?|you|oh\.?|ah\.?|uh\.?|hmm\.?|huh\.?|music|"
                   r"\[.*\]|\(.*\)|\.+|♪.*)\s*$", re.I)


def dubbed_assets():
    known = set()
    for p in os.listdir(os.path.join(ROOT, 'lines')):
        if p.endswith('.csv') and '_qc' not in p and 'before' not in p:
            with open(os.path.join(ROOT, 'lines', p), encoding='utf-8-sig') as f:
                known |= {r['asset'].lower() for r in csv.DictReader(f)}
    return known


def main():
    import torch
    from transformers import pipeline
    from ra3voice import throttle
    os.makedirs(OUT, exist_ok=True)
    cache_path = os.path.join(OUT, 'heard.json')
    heard = json.load(open(cache_path, encoding='utf-8')) if os.path.exists(cache_path) else {}
    known = dubbed_assets()
    throttle.setup(torch)
    asr = pipeline('automatic-speech-recognition', model='openai/whisper-large-v3', dtype=torch.float16, device='cuda:0')
    seen = {}
    for g, d in GAMES.items():          # Uprising first: it has every RA3 asset plus its own
        s = AudioStream(chain_for_game(d))
        todo = [a for a in s.assets if a.short_name.lower() not in known and a.short_name.lower() not in seen]
        for a in todo:
            seen[a.short_name.lower()] = g
        todo = [a for a in todo if a.short_name not in heard]
        print(g, 'to transcribe', len(todo), flush=True)
        for k in range(0, len(todo), 64):
            part = todo[k:k + 64]
            blobs = s.read_cdata(part)
            clips, names = [], []
            for a in part:
                try:
                    pcm, sr = s.decode(a, blobs[a.short_name])
                except Exception as e:  # noqa: BLE001 - odd formats: record and move on
                    heard[a.short_name] = {'game': g, 'seconds': 0, 'text': f'<decode failed: {type(e).__name__}>'}
                    continue
                sec = len(pcm) / sr
                if sec < MIN_SECONDS or not np.any(pcm):
                    heard[a.short_name] = {'game': g, 'seconds': round(sec, 2), 'text': ''}
                    continue
                y = pcm.astype(np.float32) / 32768
                y = y.mean(axis=1) if y.ndim == 2 else y
                q = gcd(sr, 16000)
                x = resample_poly(y, 16000 // q, sr // q).astype(np.float32)
                x = x[:30 * 16000]
                clips.append({'raw': x / (np.abs(x).max() + 1e-9) * 0.9, 'sampling_rate': 16000})
                names.append((a.short_name, round(sec, 2)))
            if clips:
                kw = {'language': 'en', 'task': 'transcribe', 'max_new_tokens': 96}
                try:
                    with throttle.work():
                        res = asr(clips, batch_size=4, generate_kwargs=kw)
                except torch.OutOfMemoryError:      # a batch of long music beds: one at a time
                    torch.cuda.empty_cache()
                    res = []
                    for c in clips:
                        with throttle.work():
                            res.append(asr(c, generate_kwargs=kw))
                for (n, sec), r in zip(names, res):
                    heard[n] = {'game': g, 'seconds': sec, 'text': r['text'].strip()}
            json.dump(heard, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False)
            print(f'PROGRESS {g} {min(k + 64, len(todo))}/{len(todo)}', flush=True)
    rows = []
    for n, h in sorted(heard.items()):
        words = re.findall(r"[A-Za-z']+", h['text'])
        stock = bool(STOCK.match(h['text'])) or not words
        rows.append({'asset': n, 'game': h['game'], 'seconds': h['seconds'], 'words': len(words),
                     'stock_or_empty': int(stock), 'text': h['text']})
    with open(os.path.join(OUT, 'report.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print('FINISHED', len(rows), 'assets;', sum(1 for r in rows if not r['stock_or_empty']), 'with words', flush=True)


if __name__ == '__main__':
    main()
