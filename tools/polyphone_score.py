"""Which reading did the dub use? For every polyphone spot, Whisper scores the line's audio against the text with
that character swapped for a single-reading homophone of each candidate reading (中弹 -> 中蛋 dan4 / 中谈 tan2).
The swap removes Whisper's habit of hearing the familiar word; both variants are equally odd, so only the sound
decides.

  python -I -X utf8 tools/polyphone_score.py all                     -> work/polyphone/scores.csv
  python -I -X utf8 tools/polyphone_score.py lines BATCH:ASSET ... [--voices DIR] [--out NAME]

Only readings that differ in the syllable are compared (dan / tan): Whisper cannot tell tones apart. Columns:
reading (context syllable, pypinyin), best (highest-scoring syllable, best tone of each), margin = logp(reading) -
logp(best other syllable); negative = the audio sounds like another reading.
"""
import argparse
import csv
import glob
import os
import sys
from collections import Counter

import numpy as np
import torch
from pypinyin import Style, lazy_pinyin, pinyin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io  # noqa: E402

MODEL = 'openai/whisper-large-v3'
OUT = os.path.join(ROOT, 'work', 'polyphone')
BATCHES = ['allied', 'soviet', 'empire', 'eva', 'commander', 'mission', 'movie']
# sentence particles and structural words: the model reads them by position, the swap would only add noise
SKIP = set('了着地的得啊呢哟啦吗么吧呀哪哇哈嘛咯喽哦噢呐什')


def common_syllables():
    """char -> toneless syllables it really takes (>= 3 phrases or >= 3 % of its phrases in pypinyin's dictionary)."""
    from collections import Counter, defaultdict
    from pypinyin.phrases_dict import phrases_dict
    cnt = defaultdict(Counter)
    for ph, py in phrases_dict.items():
        if len(ph) == len(py):
            for c, p in zip(ph, py):
                cnt[c][toneless_of(p[0])] += 1
    return {c: [s for s, n in k.items() if n >= 3 or n >= 0.03 * sum(k.values())] for c, k in cnt.items()}


def toneless_of(p):
    """'dàn' -> 'dan'"""
    import unicodedata
    return ''.join(ch for ch in unicodedata.normalize('NFD', p) if not unicodedata.combining(ch)).replace('ü', 'v')


def readings(ch):
    return list(dict.fromkeys(pinyin(ch, style=Style.TONE3, heteronym=True, neutral_tone_with_five=True)[0]))


def han(c):
    return '一' <= c <= '鿿'


def homophones(texts):
    """toned reading -> a common character with only that reading (most frequent in our own scripts first)."""
    freq = Counter(c for t in texts for c in t if han(c))
    pool = [c for c, _ in freq.most_common()] + [chr(x) for x in range(0x4e00, 0x9fa6)]
    out = {}
    for c in pool:
        r = pinyin(c, style=Style.TONE3, heteronym=True, neutral_tone_with_five=True)[0]
        if len(r) == 1 and r[0] not in out:
            out[r[0]] = c
    return out


def released(batches):
    rows = []
    for b in batches:
        for r in csv.DictReader(open(os.path.join(ROOT, 'lines', b + '.csv'), encoding='utf-8-sig')):
            if r.get('zh') and os.path.exists(os.path.join(ROOT, 'voices', b, r['asset'] + '.wav')):
                rows.append((b, r['asset'], r['zh']))
    return rows


class Scorer:
    def __init__(self):
        from transformers import WhisperForConditionalGeneration, WhisperProcessor
        from ra3voice import throttle
        throttle.setup(torch)      # share the GPU (gpu_limit.json): a full-speed run starved a game test once
        self.throttle = throttle
        self.proc = WhisperProcessor.from_pretrained(MODEL)
        self.model = WhisperForConditionalGeneration.from_pretrained(MODEL, torch_dtype=torch.float16).to('cuda').eval()
        tok = self.proc.tokenizer
        self.prefix = tok.convert_tokens_to_ids(['<|startoftranscript|>', '<|zh|>', '<|transcribe|>', '<|notimestamps|>'])
        self.eot = tok.eos_token_id

    def logp(self, wav, texts):
        with self.throttle.work():
            return self._logp(wav, texts)

    @torch.no_grad()
    def _logp(self, wav, texts):
        x = audio_io.load_mono(wav, 16000).astype(np.float32)[:16000 * 30]
        feats = self.proc(x, sampling_rate=16000, return_tensors='pt').input_features.to('cuda', torch.float16)
        enc = self.model.model.encoder(feats).last_hidden_state
        ids = [self.prefix + self.proc.tokenizer(t, add_special_tokens=False).input_ids + [self.eot] for t in texts]
        n = max(map(len, ids))
        inp = torch.full((len(ids), n - 1), self.eot, dtype=torch.long)
        tgt = torch.full((len(ids), n - 1), -1, dtype=torch.long)
        for k, s in enumerate(ids):
            inp[k, :len(s) - 1] = torch.tensor(s[:-1])
            tgt[k, len(self.prefix) - 1:len(s) - 1] = torch.tensor(s[len(self.prefix):])
        inp, tgt = inp.cuda(), tgt.cuda()
        out = []
        for i in range(0, len(ids), 16):
            logits = self.model(encoder_outputs=(enc.expand(len(inp[i:i + 16]), -1, -1),),
                                decoder_input_ids=inp[i:i + 16]).logits.float().log_softmax(-1)
            t = tgt[i:i + 16]
            lp = logits.gather(-1, t.clamp(min=0).unsqueeze(-1)).squeeze(-1) * (t >= 0)
            out += lp.sum(-1).tolist()
        return out


def score_lines(rows, voices, out_csv):
    hom = homophones([zh for _, _, zh in released(BATCHES)])
    common = common_syllables()
    sc = Scorer()
    res = []
    for n, (batch, asset, zh) in enumerate(rows):
        wav = os.path.join(voices or os.path.join(ROOT, 'voices', batch), asset + '.wav')
        chars = [c for c in zh if han(c)]
        ctx = lazy_pinyin(''.join(chars), style=Style.TONE3, neutral_tone_with_five=True)
        spots, texts = [], []
        k = -1
        for pos, c in enumerate(zh):
            if not han(c):
                continue
            k += 1
            want = ctx[k].rstrip('012345')
            syls = list(common.get(c) or dict.fromkeys(r.rstrip('012345') for r in readings(c)))
            if want not in syls:
                syls.append(want)
            syls = [y for y in syls if any(y + t in hom for t in '12345')]
            if c in SKIP or len(syls) < 2 or want not in syls:
                continue
            variants = [(y, hom[y + t]) for y in syls for t in '12345' if y + t in hom]
            spots.append((pos, c, want, variants, len(texts)))
            texts += [zh[:pos] + h + zh[pos + 1:] for _, h in variants]
        if not spots:
            continue
        lps = sc.logp(wav, texts)
        for pos, c, want, variants, at in spots:
            sc_ = {}
            for (y, _), v in zip(variants, lps[at:at + len(variants)]):
                sc_[y] = max(sc_.get(y, float('-inf')), v)
            best = max(sc_, key=sc_.get)
            other = max(v for y, v in sc_.items() if y != want)
            res.append({'batch': batch, 'asset': asset, 'char': c, 'context': zh[max(0, pos - 3):pos + 4], 'reading': want,
                        'best': best, 'margin': round(sc_[want] - other, 2),
                        'scores': ' '.join(f'{y}:{v:.1f}' for y, v in sc_.items()), 'zh': zh})
        if n % 200 == 0:
            print(n, len(rows), asset, flush=True)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, out_csv), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['batch', 'asset', 'char', 'context', 'reading', 'best', 'margin', 'scores', 'zh'])
        w.writeheader()
        w.writerows(res)
    print(f'{len(res)} spots, {sum(r["margin"] < 0 for r in res)} sound like another reading -> {os.path.join(OUT, out_csv)}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['all', 'lines'])
    ap.add_argument('lines', nargs='*', help='BATCH:ASSET')
    ap.add_argument('--voices', help='read <asset>.wav from this folder instead of voices/<batch>/')
    ap.add_argument('--out', default='scores.csv')
    a = ap.parse_args()
    if a.mode == 'all':
        rows = released(BATCHES)
    else:
        zh = {(b, s): t for b, s, t in released(BATCHES)}
        rows = [(*x.split(':'), zh[tuple(x.split(':'))]) for x in a.lines]
    score_lines(rows, a.voices, a.out)


if __name__ == '__main__':
    main()
