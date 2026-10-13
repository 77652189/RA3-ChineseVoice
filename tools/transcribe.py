"""Fill the `en` column of lines/<batch>.csv with Whisper transcriptions of original/<batch>/*.wav.

Usage: python tools/transcribe.py allied soviet empire eva
Rows that already have `en` text are left alone.
"""
import csv
import os
import sys

import numpy as np
import torch
from transformers import pipeline

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io, throttle  # noqa: E402

MODEL = 'openai/whisper-large-v3'
BATCH = 2


def run(asr, batch):
    path = os.path.join(ROOT, 'lines', f'{batch}.csv')
    with open(path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    todo = [r for r in rows if not r['en'].strip()]
    print(f'{batch}: {len(todo)} of {len(rows)} to transcribe', flush=True)
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        inputs = [{'raw': audio_io.load_mono(os.path.join(ROOT, 'original', batch, r['asset'] + '.wav'), 16000)
                   .astype(np.float32), 'sampling_rate': 16000} for r in chunk]
        # clips over Whisper's 30 s window (a few movie spans) need chunked long-form decoding
        long_form = {'chunk_length_s': 30} if any(len(x['raw']) > 28 * 16000 for x in inputs) else {}
        with throttle.work():
            outs = asr(inputs, batch_size=BATCH, **long_form,
                       generate_kwargs={'language': 'en', 'task': 'transcribe', 'max_new_tokens': 64 if not long_form else 440})
        for r, o in zip(chunk, outs):
            r['en'] = o['text'].strip() or '(none)'
        if (i // BATCH) % 25 == 0:
            print(f'  {i + len(chunk)}/{len(todo)}', flush=True)
            _save(path, fields, rows)
    _save(path, fields, rows)


def _save(path, fields, rows):
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def main(batches):
    throttle.setup(torch)
    asr = pipeline('automatic-speech-recognition', model=MODEL, torch_dtype=torch.float16, device='cuda:0')
    for b in batches:
        run(asr, b)


if __name__ == '__main__':
    main(sys.argv[1:])
