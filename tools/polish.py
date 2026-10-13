"""Last-resort fix for lines whose best take still has an extra mid-sentence pause.

  third_party/index-tts/.venv/Scripts/python tools/polish.py <batch> [--dry-run]

Only a pause between subject and predicate counts as a natural break: it must fall on a word
boundary (jieba), the left part must be at least MIN_LEFT characters, and the right part must start
with a predicate word (已/准备/正在/遭到/被/完成/启动/就绪...). Then a comma is written into
lines/<batch>.csv at that spot (note: 补逗号). Anything else (e.g. 最终｜中队, 传送｜仪) stays flagged;
more takes are the fix for those.
Re-run tools/pick.py afterwards so the QC report sees the new punctuation.
"""
import argparse
import csv
import os
import re
import sys

import jieba

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io, pauses  # noqa: E402

PUNCT = re.compile(r'[，。！？、,.!?;；:：“”"\'‘’…\-—～~]')
MIN_SIDE = 2
MIN_LEFT = 3
NO_LEFT_END = ('已', '正', '将', '即', '被', '未', '尚', '经', '在')  # these belong to the predicate
PREDICATE = ('已', '准备', '正在', '遭到', '遭受', '被', '完成', '启动', '就绪', '即将', '开始', '受到')


def voiced_span(x, sr, rel_db=pauses.REL_DB):
    import numpy as np
    hop = int(0.01 * sr)
    n = len(x) // hop
    e = np.sqrt(np.mean(np.asarray(x[:n * hop], dtype=np.float64).reshape(n, hop) ** 2, axis=1))
    on = np.where(e > e.max() * 10 ** (rel_db / 20))[0]
    return on[0] * 0.01, (on[-1] + 1) * 0.01


def comma_position(text, x, sr):
    """Character index (in text) where a comma should go, or None if the pause isn't at a phrase break."""
    plain = [(i, c) for i, c in enumerate(text) if not PUNCT.match(c)]
    if len(plain) < 2 * MIN_SIDE + 1:
        return None
    g = pauses.gaps(x, sr)
    if not g:
        return None
    start, length = max(g, key=lambda t: t[1])
    v0, v1 = voiced_span(x, sr)
    speech = (v1 - v0) - sum(b for _, b in g)
    before = (start - v0) - sum(b for a, b in g if a < start)
    k = round(len(plain) * before / max(speech, 1e-6))  # pause comes after the k-th character
    words, pos = [], 0
    for w in jieba.cut(''.join(c for _, c in plain)):
        pos += len(w)
        words.append(pos)
    bounds = [b for b in words[:-1] if MIN_SIDE <= b <= len(plain) - MIN_SIDE]
    flat = ''.join(c for _, c in plain)
    near = [b for b in bounds if abs(b - k) <= 1 and b >= MIN_LEFT and flat[b:].startswith(PREDICATE)
            and not flat[:b].endswith(NO_LEFT_END)]
    if not near:
        return None
    b = min(near, key=lambda b: abs(b - k))
    idx = plain[b - 1][0] + 1
    if PUNCT.match(text[idx - 1]) or (idx < len(text) and PUNCT.match(text[idx])):
        return None
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('batch')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    qc_path = os.path.join(ROOT, 'lines', f'{a.batch}_qc.csv')
    with open(qc_path, encoding='utf-8-sig') as f:
        todo = {r['asset']: r for r in csv.DictReader(f) if r['flag'] == 'PAUSE'}
    path = os.path.join(ROOT, 'lines', f'{a.batch}.csv')
    with open(path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    fixed, kept = [], []
    for r in rows:
        q = todo.get(r['asset'])
        if not q:
            continue
        x = audio_io.load_mono(os.path.join(ROOT, 'candidates', a.batch, q['take']), 16000)
        idx = comma_position(r['zh'], x, 16000)
        if idx is None:
            kept.append(r['asset'])
            continue
        new = r['zh'][:idx] + '，' + r['zh'][idx:]
        fixed.append((r['asset'], r['zh'], new))
        if not a.dry_run:
            r['note'] = (r['note'] + '；' if r['note'] else '') + f'补逗号：配音在此自然停顿（原稿 {r["zh"]}）'
            r['zh'] = new
    if not a.dry_run and fixed:
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    for asset, old, new in fixed:
        print(f'COMMA {asset}: {old} -> {new}')
    print(f'POLISH {a.batch}: {len(fixed)} commas added, {len(kept)} left flagged: {kept}')


if __name__ == '__main__':
    main()
