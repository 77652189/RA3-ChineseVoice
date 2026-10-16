"""Speaker / emotion references for movie lines, cut from the separated English vocals.

  python tools/clean_refs.py [movie ...]      (default: every dubbed movie)

Lines with a trusted measured onset (work/align/report.csv) are cut from where the actor starts to the next
line's onset; the rest by subtitle time as before.

The plain references (original/movie/<asset>.wav, from tools/catalog_movie.py) are slices of the mixed
dialogue track: music and effects underneath, and in fast exchanges the tail of the previous speaker.
IndexTTS2 copies whatever it hears, so multi-speaker cutscenes came out with blended voices.
Here each reference is the Demucs vocals (work/sep, tools/separate_movies.py) of the dialogue channel(s),
limited to this line: never earlier than the previous line's end, never later than the next line's start,
then trimmed to where there is actual speech. Output: original/movie_clean/<asset>.wav
"""
import csv
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io, movie                   # noqa: E402

OUT = os.path.join(ROOT, 'original', 'movie_clean')
PAD_BEFORE, PAD_AFTER, GAP = 0.10, 0.25, 0.03


def main(only):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    by = {}
    for r in rows:
        by.setdefault((r['games'], r['movie']), []).append(r)
    # measured onsets (tools/align_movies.py); only trusted ones: the offset was applied or the line was on time
    onset = {}
    report = os.path.join(ROOT, 'work', 'align', 'report.csv')
    if os.path.exists(report):
        with open(report, encoding='utf-8-sig') as f:
            for q in csv.DictReader(f):
                if q['onset'] and not q['rejected'] and (q['applied'] or abs(float(q['shift'])) < 0.35):
                    onset[q['asset']] = float(q['onset'])
    made = 0
    for (game, mv), rs in sorted(by.items()):
        if only and mv not in only:
            continue
        sep = os.path.join(ROOT, 'work', 'sep', game, mv + '.npy')
        if not os.path.exists(sep):
            continue
        voc = np.load(sep)
        chans = movie.dialogue_channels(voc.shape[1])
        v = voc[:, chans].astype(np.float64).mean(axis=1)
        rs.sort(key=lambda r: float(r['start']))
        for i, r in enumerate(rs):
            s, d = float(r['start']), float(r['dur'])
            if r['asset'] in onset:
                # where the actor really speaks: the subtitle runs ~1.3 s ahead in full-screen movies, so a slice at
                # the subtitle time was mostly the previous speaker (R_afs05_04 Bingham came out in Eva's voice)
                lo = onset[r['asset']] - PAD_BEFORE
                later = [onset[q['asset']] for q in rs[i + 1:] if q['asset'] in onset]
                hi = min([onset[r['asset']] + d + 1.0] + [t - GAP for t in later[:1]])
            else:
                lo = s - PAD_BEFORE
                if i:
                    lo = max(lo, float(rs[i - 1]['start']) + float(rs[i - 1]['dur']) + GAP)
                hi = s + d + PAD_AFTER
                if i + 1 < len(rs):
                    hi = min(hi, float(rs[i + 1]['start']) - GAP)
            a, b = max(0, int(lo * movie.SR)), min(len(v), int(hi * movie.SR))
            if b - a < movie.SR // 5:
                continue
            clip = movie.trim(v[a:b] / 32768, thresh_db=-35)
            if not len(clip):
                continue
            audio_io.save_wav(os.path.join(OUT, r['asset'] + '.wav'), audio_io.to_int16(clip), movie.SR)
            made += 1
    print(f'{made} clean references -> {OUT}')


if __name__ == '__main__':
    main(set(sys.argv[1:]))
