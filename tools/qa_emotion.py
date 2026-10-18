"""Does the dub carry the actor's emotion? emotion2vec+ (FunASR) hears the actor's own line (original/movie_clean)
and our dub, and the two are compared: emotion embedding similarity and the distance between the 9-way emotion
distributions. Emotion recognition works on the sound, not the words, so English vs Chinese is comparable.

  emo=third_party/emo-venv/Scripts/python.exe      (uv venv over the system Python's torch, + funasr)
  $emo -I -X utf8 tools/qa_emotion.py [--assets A B ...] [--voices DIR] [--out work/qa/emotion.csv]

Columns: emb_cos (1 = same emotional colour), js (0 = same distribution), actor_top / dub_top (labels),
p_<emotion>_actor / _dub.
"""
import argparse
import csv
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io  # noqa: E402

MODEL = 'iic/emotion2vec_plus_large'
EN = ['angry', 'disgusted', 'fearful', 'happy', 'neutral', 'other', 'sad', 'surprised', 'unknown']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--assets', nargs='*')
    ap.add_argument('--voices', default=os.path.join(ROOT, 'voices', 'movie'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'work', 'qa', 'emotion.csv'))
    a = ap.parse_args()
    rows = [r for r in csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig'))
            if r['zh'].strip() and os.path.exists(os.path.join(a.voices, r['asset'] + '.wav'))
            and os.path.exists(os.path.join(ROOT, 'original', 'movie_clean', r['asset'] + '.wav'))]
    if a.assets:
        rows = [r for r in rows if r['asset'] in set(a.assets)]
    import torch
    from ra3voice import throttle
    throttle.setup(torch)
    from funasr import AutoModel
    model = AutoModel(model=MODEL, hub='hf', disable_update=True)

    def hear(path):
        y = audio_io.load_mono(path, 16000).astype(np.float32)
        with throttle.work():
            r = model.generate(y, granularity='utterance', extract_embedding=True)[0]
        p = np.zeros(len(EN))
        for lab, s in zip(r['labels'], r['scores']):
            en = lab.split('/')[-1].strip().lower().replace('<unk>', 'unknown')
            if en in EN:
                p[EN.index(en)] = s
        return np.asarray(r['feats'], dtype=np.float64).ravel(), p / max(p.sum(), 1e-9)

    def js(p, q):
        m = (p + q) / 2
        kl = lambda x, y: float(np.sum(np.where(x > 0, x * np.log((x + 1e-12) / (y + 1e-12)), 0)))
        return 0.5 * kl(p, m) + 0.5 * kl(q, m)

    out = []
    for i, r in enumerate(rows):
        ea, pa = hear(os.path.join(ROOT, 'original', 'movie_clean', r['asset'] + '.wav'))
        ed, pd = hear(os.path.join(a.voices, r['asset'] + '.wav'))
        row = {'asset': r['asset'], 'zh': r['zh'],
               'emb_cos': round(float(ea @ ed / (np.linalg.norm(ea) * np.linalg.norm(ed) + 1e-12)), 4),
               'js': round(js(pa, pd), 4), 'actor_top': EN[int(pa.argmax())], 'dub_top': EN[int(pd.argmax())]}
        row.update({f'p_{e}_actor': round(float(pa[k]), 3) for k, e in enumerate(EN)})
        row.update({f'p_{e}_dub': round(float(pd[k]), 3) for k, e in enumerate(EN)})
        out.append(row)
        if i % 100 == 0:
            print(i, len(rows), r['asset'], row['actor_top'], row['dub_top'], flush=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print('->', a.out, len(out))


if __name__ == '__main__':
    main()
