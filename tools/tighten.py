"""Shorten the unexplained mid-sentence pauses that pick.py still flags (PAUSE) after re-dubbing.

  .venv python -I -X utf8 tools/tighten.py movie --preview 10    listening page preview/tighten/ (nothing changed)
  .venv python -I -X utf8 tools/tighten.py movie --apply         rewrite clean/movie/<asset>.wav (originals kept
                                                                 in archive/tighten_orig/movie/); then fx.py apply

Which gap is "unexplained": punctuation inside the script allows a pause there. Each inner punctuation mark is
placed at its share of the characters along the voiced span (TTS reads at a fairly even pace) and claims the
nearest gap within TOL of the line; the gaps nobody claims are cut down to KEEP seconds (half on each side, short
crossfade), so the words close up without a click and the line keeps its breathing at the commas.
Only the silent middle of a gap is removed - a gap that holds a breath or a half syllable is not silent there and
is left alone by construction (gaps are runs below pauses.REL_DB).
"""
import argparse
import csv
import html
import os
import shutil
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io, pauses  # noqa: E402

SR = 48000
KEEP = 0.10          # seconds of silence left where an unexplained pause was
FADE = 0.01
TOL = 0.12           # a punctuation mark claims a gap within this share of the line


def plan(x, sr, text):
    """[(start_s, length_s)] of the gaps to shorten."""
    g = pauses.gaps(x, sr, min_gap=pauses.min_gap_for(len(x) / sr))
    if not g:
        return []
    body = text.strip().rstrip(pauses.TRAILING)
    chars = [c for c in body if not c.isspace()]
    spoken = [i for i, c in enumerate(chars) if not pauses.INNER_PUNCT.match(c)]
    marks = [i for i, c in enumerate(chars) if pauses.INNER_PUNCT.match(c)]
    n = max(len(spoken), 1)
    # voiced span = first to last frame above the gate (same gate as pauses.gaps)
    hop = int(0.01 * sr)
    e = np.sqrt(np.mean(np.asarray(x[:len(x) // hop * hop], np.float64).reshape(-1, hop) ** 2, axis=1))
    on = np.where(e > e.max() * 10 ** (pauses.REL_DB / 20))[0]
    t0, t1 = on[0] * 0.01, (on[-1] + 1) * 0.01
    speech = (t1 - t0) - sum(b for _, b in g)
    free = list(range(len(g)))
    for m in marks:
        share = sum(1 for i in spoken if i < m) / n            # characters before the mark
        # map the share of characters to time along the speech, skipping earlier gaps
        best, best_d = None, None
        for k in free:
            s, b = g[k]
            before = sum(bb for ss, bb in g if ss < s)
            pos = ((s - t0) - before) / max(speech, 1e-6)
            d = abs(pos - share)
            if d <= TOL and (best_d is None or d < best_d):
                best, best_d = k, d
        if best is not None:
            free.remove(best)
    return [g[k] for k in free]


def shorten(x, sr, cuts):
    out, last = [], 0
    f = int(FADE * sr)
    for s, b in sorted(cuts):
        a = int((s + KEEP / 2) * sr)
        z = int((s + b - KEEP / 2) * sr)
        if z - a <= 2 * f:
            continue
        head = x[last:a].copy()
        tail = x[z:z + f].copy()
        ramp = np.linspace(1, 0, f, dtype=np.float32)
        head[-f:] = head[-f:] * ramp + tail * (1 - ramp)
        out.append(head)
        last = z + f
    out.append(x[last:])
    return np.concatenate(out)


def flagged(batch):
    with open(os.path.join(ROOT, 'lines', f'{batch}_qc.csv'), encoding='utf-8-sig') as f:
        return [r for r in csv.DictReader(f) if 'PAUSE' in r['flag']]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('batch')
    ap.add_argument('--preview', type=int, default=0)
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    rows = flagged(a.batch)
    clean = os.path.join(ROOT, 'clean', a.batch)
    done, fixed = [], 0
    for r in rows:
        p = os.path.join(clean, r['asset'] + '.wav')
        x = audio_io.load_mono(p, SR)
        cuts = plan(x, SR, r['zh'])
        if not cuts:
            continue
        y = shorten(x, SR, cuts)
        left, _ = pauses.extra(y, SR, r['zh'])
        fixed += left == 0
        done.append((r, x, y, cuts, left))
    print(f'{len(rows)} PAUSE lines, {len(done)} with gaps to shorten, {fixed} no longer flagged afterwards')
    if a.preview:
        out = os.path.join(ROOT, 'preview', 'tighten')
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        step = max(1, len(done) // a.preview)
        cards = []
        for r, x, y, cuts, left in done[::step][:a.preview]:
            n = r['asset']
            orig = os.path.join(ROOT, 'original', 'movie_clean' if a.batch == 'movie' else a.batch, n + '.wav')
            if os.path.exists(orig):
                shutil.copyfile(orig, os.path.join(out, n + '_orig.wav'))
            audio_io.save_wav(os.path.join(out, n + '_now.wav'), audio_io.to_int16(x), SR)
            audio_io.save_wav(os.path.join(out, n + '_tight.wav'), audio_io.to_int16(y), SR)
            gaps = '、'.join(f'{s:.2f} 秒处 {b:.2f} 秒' for s, b in cuts)
            cards.append(f'<div class="c"><code>{html.escape(n)}</code><div class="zh">{html.escape(r["zh"])}</div>'
                         f'<div class="en">压短的停顿：{gaps}（压到 {KEEP:.1f} 秒）</div>'
                         + ''.join(f'<div class="row"><b>{k}</b><span>{lab}</span><audio controls preload="none" src="{n}_{s}.wav"></audio></div>'
                                   for k, lab, s in (('原', '英文原声', 'orig'), ('现', '现在的配音', 'now'), ('压', '压短停顿后', 'tight'))
                                   if s != 'orig' or os.path.exists(orig))
                         + '</div>')
        page = ('<!doctype html><meta charset="utf-8"><title>停顿压缩试听</title><style>body{font:15px system-ui,sans-serif;'
                'background:#111;color:#ddd;margin:0;padding:20px;max-width:900px}.c{background:#1c1f24;border-radius:8px;'
                'padding:14px 16px;margin:12px 0}.zh{font-size:19px;color:#fff;margin:4px 0}.en{color:#999;font-size:13px}'
                '.row{display:flex;align-items:center;gap:10px;margin:6px 0}.row b{width:24px}.row span{width:140px;color:#aaa;'
                'font-size:13px}audio{height:32px}</style><h2>句中停顿：压短空白前后对比</h2>'
                f'<p>重配后仍被标出“中间有停顿”的过场台词里，均匀挑了 {len(cards)} 句。听“现”和“压”：压短后是否自然、'
                '有没有咔哒声或吞字。逗号处的停顿保留不动。</p>' + ''.join(cards))
        open(os.path.join(out, 'index.html'), 'w', encoding='utf-8').write(page)
        print('->', os.path.join(out, 'index.html'))
    if a.apply:
        bak = os.path.join(ROOT, 'archive', 'tighten_orig', a.batch)
        os.makedirs(bak, exist_ok=True)
        for r, x, y, cuts, left in done:
            p = os.path.join(clean, r['asset'] + '.wav')
            if not os.path.exists(os.path.join(bak, r['asset'] + '.wav')):
                shutil.copyfile(p, os.path.join(bak, r['asset'] + '.wav'))
            audio_io.save_wav(p, audio_io.to_int16(y), SR)
        print(f'rewrote {len(done)} files in clean/{a.batch} (originals in archive/tighten_orig/{a.batch}); run fx.py apply next')


if __name__ == '__main__':
    main()
