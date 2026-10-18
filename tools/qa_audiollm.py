"""An audio-language model as misreading judge: Qwen2.5-Omni-3B hears a dub and is asked which of two readings a
polyphone was spoken with. Unlike Whisper, the question names both readings, so the model cannot quietly fix the
word to the familiar one.

  python -I -X utf8 tools/qa_audiollm.py bench      # forced choice, score against work/qa/misread_bench.csv
  python -I -X utf8 tools/qa_audiollm.py free       # blind pinyin transcription, same benchmark

Forced choice (A/B with both readings named) turned out useless: the model answers "B" whatever it hears. Blind
transcription works: without the text the model writes the syllables it hears (从不落空 -> "là kōng" on the
misread take, "luò kōng" on the fixed one), and the syllable aligned with the polyphone is compared with the
reading it should have.
"""
import difflib
import unicodedata
import csv
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io  # noqa: E402

MODEL = 'Qwen/Qwen2.5-Omni-3B'
SYSTEM = ('You are Qwen, a virtual human developed by the Qwen Team, Alibaba Group, capable of perceiving auditory '
          'and visual inputs, as well as generating text and speech.')
PROMPT = ('这是一段普通话配音，台词文字是：「{zh}」。\n请只根据声音判断：其中的「{ch}」字，说话人实际读成了哪个音？\n'
          'A. {a}\nB. {b}\n只回答一个字母：A 或 B。')


class Judge:
    def __init__(self):
        import torch
        from transformers import Qwen2_5OmniProcessor, Qwen2_5OmniThinkerForConditionalGeneration
        from ra3voice import throttle
        throttle.setup(torch)
        self.torch, self.throttle = torch, throttle
        self.proc = Qwen2_5OmniProcessor.from_pretrained(MODEL)
        self.model = Qwen2_5OmniThinkerForConditionalGeneration.from_pretrained(
            MODEL, dtype=torch.bfloat16, device_map='cuda').eval()
        tok = self.proc.tokenizer
        self.ids = [tok.encode(x, add_special_tokens=False)[0] for x in ('A', 'B')]

    def p_b(self, wav, prompt):
        """P(answer B) for one audio and question."""
        y = audio_io.load_mono(wav, 16000).astype(np.float32)
        conv = [{'role': 'system', 'content': [{'type': 'text', 'text': SYSTEM}]},
                {'role': 'user', 'content': [{'type': 'audio', 'audio': wav}, {'type': 'text', 'text': prompt}]}]
        text = self.proc.apply_chat_template(conv, add_generation_prompt=True, tokenize=False)
        inputs = self.proc(text=[text], audio=[y], return_tensors='pt', padding=True).to(self.model.device)
        inputs = {k: (v.to(self.torch.bfloat16) if v.dtype == self.torch.float32 else v) for k, v in inputs.items()}
        with self.throttle.work(), self.torch.no_grad():
            logits = self.model(**inputs).logits[0, -1].float()
        two = logits[self.ids].softmax(-1)
        return float(two[1])

    def wrong_prob(self, wav, zh, ch, right, wrong):
        p1 = self.p_b(wav, PROMPT.format(zh=zh, ch=ch, a=right, b=wrong))        # B = wrong
        p2 = 1 - self.p_b(wav, PROMPT.format(zh=zh, ch=ch, a=wrong, b=right))    # A = wrong
        return (p1 + p2) / 2, p1, p2


def bench():
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'work', 'qa', 'misread_bench.csv'), encoding='utf-8-sig')))
    j = Judge()
    out = []
    for r in rows:
        p, p1, p2 = j.wrong_prob(os.path.join(ROOT, r['path']), r['zh'], r['char'], r['right'], r['wrong'])
        out.append(dict(r, p_wrong=round(p, 3), p_order1=round(p1, 3), p_order2=round(p2, 3)))
        print(r['asset'], r['version'], r['char'], r['misread'], round(p, 3), flush=True)
    path = os.path.join(ROOT, 'work', 'qa', 'misread_bench_omni.csv')
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    pos = [o['p_wrong'] for o in out if o['misread'] == '1']
    neg = [o['p_wrong'] for o in out if o['misread'] == '0']
    auc = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))
    print(f'AUC {auc:.3f}  misread median {np.median(pos):.2f}  right median {np.median(neg):.2f}')
    for t in (0.3, 0.5, 0.7):
        print(f'  threshold {t}: catches {sum(p > t for p in pos)}/{len(pos)} misread, flags {sum(n > t for n in neg)}/{len(neg)} right')


FREE = '请仔细听这段普通话，把你听到的内容逐字写成拼音，每个字一个拼音，用空格分开。只输出一行拼音，不要输出别的。'


def toneless(p):
    """'xiǎng' / 'xiang3' / 'lü' -> 'xiang' / 'lv'"""
    p = unicodedata.normalize('NFD', p.lower())
    p = ''.join(c for c in p if not unicodedata.combining(c)).replace('ü', 'v').replace('u:', 'v')
    return ''.join(c for c in p if c.isalpha())


def heard_syllables(j, wav, n_chars):
    y = audio_io.load_mono(wav, 16000).astype(np.float32)
    conv = [{'role': 'system', 'content': [{'type': 'text', 'text': SYSTEM}]},
            {'role': 'user', 'content': [{'type': 'audio', 'audio': wav}, {'type': 'text', 'text': FREE}]}]
    text = j.proc.apply_chat_template(conv, add_generation_prompt=True, tokenize=False)
    inp = j.proc(text=[text], audio=[y], return_tensors='pt', padding=True).to(j.model.device)
    inp = {k: (v.to(j.torch.bfloat16) if v.dtype == j.torch.float32 else v) for k, v in inp.items()}
    with j.throttle.work(), j.torch.no_grad():
        out = j.model.generate(**inp, max_new_tokens=6 * n_chars + 10, do_sample=False)
    ans = j.proc.batch_decode(out[:, inp['input_ids'].shape[1]:], skip_special_tokens=True)[0]
    first = ans.strip().splitlines()[0] if ans.strip() else ''
    return [t for t in (toneless(x) for x in first.replace('，', ' ').replace(',', ' ').split()) if t], first


def heard_at(zh, ch, heard):
    """The heard syllable aligned with the polyphone (first occurrence of ch), or None."""
    from pypinyin import lazy_pinyin
    chars = [c for c in zh if '一' <= c <= '鿿']
    want = [toneless(p) for p in lazy_pinyin(''.join(chars))]
    k = chars.index(ch)
    sm = difflib.SequenceMatcher(None, want, heard, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if i1 <= k < i2 and tag in ('equal', 'replace') and (tag == 'equal' or i2 - i1 == j2 - j1):
            return heard[j1 + k - i1]
    return None


def free():
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'work', 'qa', 'misread_bench.csv'), encoding='utf-8-sig')))
    j = Judge()
    out = []
    for r in rows:
        heard, raw = heard_syllables(j, os.path.join(ROOT, r['path']), len(r['zh']))
        h = heard_at(r['zh'], r['char'], heard)
        verdict = 'none' if h is None else ('right' if h == toneless(r['right']) else 'off')
        out.append(dict(r, heard=raw, at=h or '', verdict=verdict))
        print(r['misread'], r['asset'], r['version'], r['char'], r['right'], '->', h, verdict, flush=True)
    path = os.path.join(ROOT, 'work', 'qa', 'misread_bench_free.csv')
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    for m, name in (('1', 'misread'), ('0', 'read right')):
        g = [o for o in out if o['misread'] == m]
        print(f"{name:10s} n={len(g)}  off={sum(o['verdict'] == 'off' for o in g)}  right={sum(o['verdict'] == 'right' for o in g)}  "
              f"unaligned={sum(o['verdict'] == 'none' for o in g)}")


if __name__ == '__main__':
    {'bench': bench, 'free': free}[sys.argv[1]]()
