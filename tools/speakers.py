"""Who is speaking? Speaker fingerprints for movie lines (run with the IndexTTS venv python).

  third_party/index-tts/.venv/Scripts/python tools/speakers.py

Uses the CAMPPlus speaker-embedding model that ships with IndexTTS2 and a YIN pitch estimate on:
  - the clean English references (original/movie_clean, tools/clean_refs.py), and
  - the current Chinese dubs (voices/movie), if present.
Writes
  work/speakers/fallback.json  {asset: asset} for references too short to carry a voice: the closest
                               same-movie line (by fingerprint), i.e. the same actor, not just the
                               movie's longest line (which made e.g. Tanya borrow a male officer's voice)
  work/speakers/check.json     dubbed lines whose voice does not match their own actor: pitch far off
                               (male/female swap) or the fingerprint is closer to another actor in the
                               same movie than to its own line.
"""
import csv
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TTS = os.path.join(ROOT, 'third_party', 'index-tts')
sys.path.insert(0, TTS)
OUT = os.path.join(ROOT, 'work', 'speakers')
REF = os.path.join(ROOT, 'original', 'movie_clean')
DUB = os.path.join(ROOT, 'voices', 'movie')
SHORT, GOOD = 1.0, 1.5          # seconds: below SHORT a reference borrows; only GOOD+ lines are lent
F0_LO, F0_HI = 0.72, 1.39       # dub / original median pitch outside this (about 5.7 semitones) = wrong voice
OTHER = 0.45                    # two references below this similarity are treated as different actors


def load_16k(path):
    import librosa
    y, _ = librosa.load(path, sr=16000, mono=True)
    return y


class Fingerprint:
    def __init__(self):
        import torch
        from indextts.s2mel.modules.campplus.DTDNN import CAMPPlus
        self.torch = torch
        m = CAMPPlus(feat_dim=80, embedding_size=192)
        m.load_state_dict(torch.load(os.path.join(TTS, 'checkpoints', 'hf_cache', 'campplus_cn_common.bin'), map_location='cpu'))
        self.m = m.eval()

    def __call__(self, y):
        import torchaudio
        t = self.torch.from_numpy(y).float()[None]
        feat = torchaudio.compliance.kaldi.fbank(t, num_mel_bins=80, dither=0, sample_frequency=16000)
        feat = feat - feat.mean(dim=0, keepdim=True)
        with self.torch.no_grad():
            e = self.m(feat[None])[0].numpy()
        return e / (np.linalg.norm(e) + 1e-9)


def median_f0(y):
    import librosa
    if len(y) < 1600:
        return 0.0
    f0 = librosa.yin(y, fmin=65, fmax=500, sr=16000, frame_length=1024)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=256)[0][:len(f0)]
    voiced = f0[:len(rms)][rms > rms.max() * 0.2] if rms.max() > 0 else f0
    return float(np.median(voiced)) if len(voiced) else 0.0


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f)]
    fp = Fingerprint()
    info = {}
    for i, r in enumerate(rows):
        p = os.path.join(REF, r['asset'] + '.wav')
        if not os.path.exists(p):
            continue
        y = load_16k(p)
        d = {'movie': (r['games'], r['movie']), 'dur': len(y) / 16000, 'emb': fp(y), 'f0': median_f0(y)}
        q = os.path.join(DUB, r['asset'] + '.wav')
        if r['zh'].strip() and os.path.exists(q):
            z = load_16k(q)
            d['dub_emb'], d['dub_f0'] = fp(z), median_f0(z)
        info[r['asset']] = d
        if i % 300 == 0:
            print(f'PROGRESS {i}/{len(rows)}', flush=True)
    by_movie = {}
    for a, d in info.items():
        by_movie.setdefault(d['movie'], []).append(a)
    fallback, check = {}, []
    for mv, assets in by_movie.items():
        good = [a for a in assets if info[a]['dur'] >= GOOD]
        for a in assets:
            d = info[a]
            if d['dur'] < SHORT and good:
                cand = [b for b in good if b != a]
                if cand:
                    fallback[a] = max(cand, key=lambda b: float(info[b]['emb'] @ d['emb']))
            if 'dub_emb' not in d:
                continue
            own = info[fallback.get(a, a)]
            reasons = []
            if own['f0'] > 0 and d['dub_f0'] > 0:
                ratio = d['dub_f0'] / own['f0']
                if not F0_LO <= ratio <= F0_HI:
                    reasons.append(f'pitch {own["f0"]:.0f}->{d["dub_f0"]:.0f} Hz')
            others = [b for b in good if float(info[b]['emb'] @ own['emb']) < OTHER]
            if others:
                s_own = float(d['dub_emb'] @ own['emb'])
                best = max(others, key=lambda b: float(d['dub_emb'] @ info[b]['emb']))
                s_other = float(d['dub_emb'] @ info[best]['emb'])
                if s_other > s_own + 0.05:
                    reasons.append(f'sounds like {best} ({s_other:.2f} vs own {s_own:.2f})')
            if reasons:
                check.append({'asset': a, 'movie': mv[1], 'game': mv[0], 'why': reasons})
    json.dump(fallback, open(os.path.join(OUT, 'fallback.json'), 'w', encoding='utf-8'), indent=1)
    json.dump(check, open(os.path.join(OUT, 'check.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(info)} lines, {len(fallback)} short references re-pointed to the same actor, '
          f'{len(check)} dubs with the wrong voice')
    for c in check[:25]:
        print('  ', c['asset'], '; '.join(c['why']))


if __name__ == '__main__':
    main()
