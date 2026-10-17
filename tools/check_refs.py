"""Does each onset-cut movie reference hold its own line? Whisper on the reference vs the line's English text.

  python -I -X utf8 tools/check_refs.py [assets.json]      -> work/voice_audit/ref_text.csv

A reference cut from a wrongly measured onset holds someone else (or crowd noise, j03mm01_01), and a dub made
from it takes that voice -- while keep_better, comparing against the same reference, would call it better.
match = share of the line's words heard in the reference (as in align_movies.tokens).
"""
import csv
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from align_movies import tokens  # noqa: E402
from ra3voice import audio_io  # noqa: E402


def main(path):
    import torch
    from transformers import pipeline
    from ra3voice import throttle
    assets = json.load(open(path, encoding='utf-8')) if path else [
        r['asset'] for r in csv.DictReader(open(os.path.join(ROOT, 'work', 'voice_audit', 'keep_better.csv'), encoding='utf-8-sig'))]
    en = {r['asset']: r['en'] for r in csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig'))}
    throttle.setup(torch)
    asr = pipeline('automatic-speech-recognition', model='openai/whisper-large-v3', dtype=torch.float16, device='cuda:0')
    out = []
    for k in range(0, len(assets), 8):
        part = assets[k:k + 8]
        clips = [{'raw': audio_io.load_mono(os.path.join(ROOT, 'original', 'movie_clean', a + '.wav'), 16000).astype(np.float32),
                  'sampling_rate': 16000} for a in part]
        with throttle.work():
            res = asr(clips, batch_size=4, generate_kwargs={'language': 'en', 'task': 'transcribe', 'max_new_tokens': 96})
        for a, r in zip(part, res):
            want, got = tokens(en[a]), set(tokens(r['text']))
            match = sum(1 for w in want if w in got) / len(want) if want else 1.0
            out.append({'asset': a, 'match': round(match, 2), 'words': len(want), 'heard': r['text'].strip(), 'en': en[a]})
    with open(os.path.join(ROOT, 'work', 'voice_audit', 'ref_text.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    bad = [o for o in out if o['match'] < 0.5]
    print(f'{len(out)} references; under half of the line heard: {len(bad)}')
    for o in sorted(bad, key=lambda o: o['match'])[:40]:
        print(f"  {o['asset']:18} {o['match']:.2f}  en: {o['en'][:40]!r:44} heard: {o['heard'][:50]!r}")


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
