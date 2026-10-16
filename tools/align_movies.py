"""Where the actors really start each movie line (the subtitle times are often 0.5-2.5 s early or late).

  python -I -X utf8 tools/align_movies.py transcribe [movie ...]   # GPU, honours gpu_limit.json; resumable
  python -I -X utf8 tools/align_movies.py offsets        # -> work/align/report.csv, work/align/offsets.json

transcribe: Whisper (English, word timestamps) over each dubbed movie's separated vocals (work/sep, see
separate_movies.py) -> work/align/<game>/<movie>.json.
offsets: align every subtitle line's English text to those words (difflib over normalised tokens), take the
line's first word, snap it to the start of the voiced run in the vocal (Whisper's word starts drift), and
propose start offsets where the actor speaks clearly off the subtitle time. ra3cv.movie_offsets() reads
work/movie_offsets.json; offsets.json is the proposal to review and copy there.
"""
import csv
import difflib
import json
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import movie  # noqa: E402

OUT = os.path.join(ROOT, 'work', 'align')
MODEL = 'openai/whisper-large-v3'
SR16 = 16000
MIN_SHIFT = 0.35        # smaller differences are normal subtitle lead/lag
MIN_MATCH = 0.5         # share of the line's words found in the transcript
LEAD = 0.05             # place the dub this much before the measured onset


def tokens(text):
    text = re.sub(r'\(.*?\)|\[.*?\]', ' ', text.lower().replace('’', "'"))
    return re.findall(r"[a-z0-9']+", text)


def movie_rows():
    """{(game, movie): [rows sorted by start]} for every movie with at least one dubbed line."""
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig')))
    by = {}
    for r in rows:
        by.setdefault((r['games'].split('+')[0], r['movie']), []).append(r)
    dubbed = {r['asset'] for r in rows if os.path.exists(os.path.join(ROOT, 'voices', 'movie', r['asset'] + '.wav'))}
    return {k: sorted(v, key=lambda r: float(r['start'])) for k, v in by.items() if any(r['asset'] in dubbed for r in v)}, dubbed


def vocal(game, mv):
    p = os.path.join(ROOT, 'work', 'sep', game, mv + '.npy')
    if not os.path.exists(p):
        return None
    voc = np.load(p)
    return voc[:, movie.speech_channels(voc.shape[1])].astype(np.float32).mean(1) / 32768


def transcribe():
    import torch
    from transformers import pipeline
    from ra3voice import throttle
    throttle.setup(torch)
    asr = pipeline('automatic-speech-recognition', model=MODEL, dtype=torch.float16, device='cuda:0')
    only = set(sys.argv[2:])
    todo = [k for k in sorted(movie_rows()[0]) if not only or k[1] in only]
    for i, (game, mv) in enumerate(todo, 1):
        dst = os.path.join(OUT, game, mv + '.json')
        if os.path.exists(dst):
            continue
        x = vocal(game, mv)
        if x is None:
            continue
        y = np.interp(np.arange(int(len(x) * SR16 / movie.SR)) * movie.SR / SR16, np.arange(len(x)), x).astype(np.float32)
        y = y / (np.abs(y).max() + 1e-9) * 0.9
        words = []
        # one call per stretch of speech (<= 25 s, cut in silence): word timestamps over a long file need more
        # memory than the VRAM cap allows, and a stretch that starts in silence keeps its first word's time honest
        todo_spans = list(speech_stretches(x))
        while todo_spans:
            a, b = todo_spans.pop(0)
            seg = y[int(a * SR16):int(b * SR16)]
            try:
                with throttle.work():
                    # the cap stops a hallucination loop, whose cross-attentions (kept for word timing) fill the VRAM
                    r = asr({'raw': seg, 'sampling_rate': SR16}, return_timestamps='word',
                            generate_kwargs={'language': 'en', 'task': 'transcribe', 'max_new_tokens': 200})
            except torch.OutOfMemoryError:
                torch.cuda.empty_cache()
                if b - a < 4:
                    print(f'SKIP {game} {mv} {a:.1f}-{b:.1f}: out of memory', flush=True)
                    continue
                m = (a + b) / 2
                todo_spans[:0] = [(a, m), (m, b)]
                continue
            for c in r['chunks']:
                t0, t1 = c['timestamp']
                words.append((c['text'].strip(), a + (t0 or 0.0), a + (t1 if t1 is not None else (t0 or 0.0))))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        json.dump({'words': words}, open(dst, 'w', encoding='utf-8'), ensure_ascii=False)
        if i % 25 == 0:
            print(f'PROGRESS {i}/{len(todo)}', flush=True)
    print('FINISHED transcribe', flush=True)


def speech_stretches(x, longest=25.0, pad=0.3):
    """[(start_s, end_s)] covering all voice (-45 dB under the loudest), each at most `longest`, cut in gaps."""
    hop = movie.SR // 100
    nf = len(x) // hop
    env = np.sqrt(np.mean(x[:nf * hop].reshape(nf, hop) ** 2, axis=1))
    on = np.flatnonzero(20 * np.log10(env / (env.max() + 1e-12) + 1e-12) > -45) / 100
    out = []
    for t in on:
        if out and t - out[-1][1] < 0.6 and t + pad - out[-1][0] <= longest:
            out[-1][1] = t
        else:
            out.append([t, t])
    total = nf / 100
    return [(max(0.0, a - pad), min(total, b + 0.01 + pad)) for a, b in out if b - a >= 0.05]


def voiced_runs(x):
    """[(start_s, end_s)] of voiced 10 ms frames (-30 dB under the movie's loudest vocal), 0.1 s gaps bridged."""
    hop = movie.SR // 100
    nf = len(x) // hop
    env = np.sqrt(np.mean(x[:nf * hop].reshape(nf, hop) ** 2, axis=1))
    on = 20 * np.log10(env / (env.max() + 1e-12) + 1e-12) > -30
    runs, k = [], 0
    while k < nf:
        if on[k]:
            j = k
            while j < nf and on[j]:
                j += 1
            if runs and k - runs[-1][1] <= 10:
                runs[-1][1] = j
            else:
                runs.append([k, j])
            k = j
        else:
            k += 1
    # under 0.25 s is a click, not a line starting (calls open with a radio blip ~0.2 s long)
    return [(a / 100, b / 100) for a, b in runs if b - a >= 25]


def offsets():
    groups, dubbed = movie_rows()
    report, proposal = [], {}
    for (game, mv), rows in sorted(groups.items()):
        src = os.path.join(OUT, game, mv + '.json')
        x = vocal(game, mv)
        if not os.path.exists(src) or x is None:
            continue
        words = json.load(open(src, encoding='utf-8'))['words']
        hyp, hyp_t = [], []
        for w, t0, t1 in words:
            for t in tokens(w):
                hyp.append(t)
                hyp_t.append((t0, t1 if t1 is not None else t0))
        ref, owner = [], []
        for li, r in enumerate(rows):
            for t in tokens(r['en']):
                ref.append(t)
                owner.append(li)
        match = {}
        for a, b, n in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_matching_blocks():
            for k in range(n):
                match[a + k] = b + k
        runs = voiced_runs(x)
        prev_end = 0.0
        for li, r in enumerate(rows):
            idx = [k for k, o in enumerate(owner) if o == li]
            got = [k for k in idx if k in match]
            start = float(r['start'])
            row = {'game': game, 'movie': mv, 'asset': r['asset'], 'dubbed': r['asset'] in dubbed, 'csv_start': start,
                   'words': len(idx), 'matched': len(got), 'onset': '', 'shift': '', 'applied': '', 'rejected': ''}
            if idx and got:
                first = got[0]
                ws, we = hyp_t[match[first]]
                # Whisper's words are contiguous: after a silence the first word "starts" back in the silence
                # and its end lands near where the actor really starts (a01mm01 "Hello" 0.73-3.71, voice from
                # 3.72). So the onset is the last voiced run that starts after the previous line, not long before
                # the word, and by just past the word's end.
                lo = max(prev_end, ws - 0.6)
                cand = [a for a, b in runs if lo <= a <= we + 0.15]
                if not cand:      # the first word's end came out early: the next real stretch of voice
                    cand = [a for a, b in runs if lo <= a <= we + 1.0][:1]
                onset = cand[-1] if cand else None
                if onset is not None and idx.index(first) > 0:
                    # the line's first word was not heard (a08th01 "Ah, ...", j08th03 "Well, ..."): it sits in a
                    # voiced run just before, which must not be left outside the window
                    before = [a for a, b in runs if max(prev_end, onset - 1.5) <= a < onset]
                    onset = before[0] if before else onset
                last_t = hyp_t[match[got[-1]]][1]
                prev_end = max(prev_end, last_t if last_t is not None else we)
                if onset is None:
                    report.append(row)
                    continue
                shift = onset - start
                row.update(onset=f'{onset:.2f}', shift=f'{shift:+.2f}')
                ok = (len(got) / len(idx) >= MIN_MATCH and idx.index(first) <= 1 and abs(shift) >= MIN_SHIFT
                      and r['asset'] in dubbed)
                if ok:
                    proposal[r['asset']] = round(shift - LEAD, 2)
                    row['applied'] = f'{shift - LEAD:+.2f}'
            report.append(row)
        here = [row for row in report if row['movie'] == mv and row['game'] == game]
        # a shift nothing around it agrees with is a misplaced match (afs10_01 "-8.06"): keep the subtitle time.
        # Subtitles drift smoothly (sfs00 creeps from +1.2 to +2.6 s), so a neighbour or the movie median must be close
        measured = [(i, float(row['shift'])) for i, row in enumerate(here) if row['shift']]
        med = float(np.median([s for _, s in measured])) if measured else 0.0
        for i, row in enumerate(here):
            if not row['applied']:
                continue
            s = float(row['shift'])
            near = [t for j, t in measured if j != i and abs(j - i) <= 1]
            whole = row['words'] >= 3 and row['matched'] == row['words'] and abs(s) <= 3.0   # every word heard there
            agrees = whole or (any(abs(s - t) <= 0.8 for t in near) or abs(s - med) <= 0.8 if len(measured) >= 3
                               else abs(s) <= 3.0 and row['matched'] >= 0.8 * row['words'])
            if not agrees:
                proposal.pop(row['asset'], None)
                row['applied'] = ''
                row['rejected'] = 'no neighbour agrees'
        # a dubbed line Whisper could not place, between two placed lines that moved alike, moves with them
        # (else the neighbours slide past it and squeeze its dub)
        placed = [(i, float(row['shift'])) for i, row in enumerate(here) if row['shift'] and
                  (row['applied'] or abs(float(row['shift'])) < MIN_SHIFT) and row['matched'] / max(1, row['words']) >= MIN_MATCH]
        for i, row in enumerate(here):
            if not row['dubbed'] or row['applied'] or any(j == i for j, _ in placed):
                continue
            before = [s for j, s in placed if j < i][-1:]
            after = [s for j, s in placed if j > i][:1]
            if before and after and abs(before[0] - after[0]) <= 0.4 and abs(before[0] + after[0]) / 2 >= MIN_SHIFT:
                v = round((before[0] + after[0]) / 2 - LEAD, 2)
                proposal[row['asset']] = v
                row['applied'] = f'{v:+.2f} (from neighbours)'
        # lines keep their order: a moved line may not reach within 0.3 s of the line before or after it
        for _ in range(3):
            new = [row['csv_start'] + proposal.get(row['asset'], 0.0) for row in here]
            for i, row in enumerate(here):
                if row['asset'] not in proposal:
                    continue
                if (i and new[i] <= new[i - 1] + 0.3) or (i + 1 < len(here) and new[i] >= new[i + 1] - 0.3):
                    proposal.pop(row['asset'])
                    row['applied'] = ''
                    row['rejected'] = 'would pass a neighbouring line'
                    break
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'report.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(report[0].keys()))
        w.writeheader()
        w.writerows(report)
    json.dump(proposal, open(os.path.join(OUT, 'offsets.json'), 'w', encoding='utf-8'), indent=1)
    sh = np.array(list(proposal.values()))
    print(f'{len(report)} lines, {sum(r["dubbed"] for r in report)} dubbed; {len(proposal)} offsets proposed '
          f'(later {int((sh > 0).sum())}, earlier {int((sh < 0).sum())}; |shift| > 1 s: {int((abs(sh) > 1).sum())})')


if __name__ == '__main__':
    {'transcribe': transcribe, 'offsets': offsets}[sys.argv[1]]()
