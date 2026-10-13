"""Catalog movie dialogue (EnglishMovieAudio.big *.snd) of both games as batch `movie`.

  python tools/catalog_movie.py

Each movie's dialogue track is the centre channel of 6-channel movies (verified: the other channels
carry music/effects) or the mono mix of stereo talking heads. It is cut into lines:
  - movies with official subtitles: one line per timed subtitle segment "[start:dur]text" (labels
    SUBTITLE:<MOVIE> or SUBTITLE:<MOVIE>_NN, times relative to the movie start);
  - movies without (skirmish commander videos ...): split at pauses; `en` left empty for Whisper.
Asset names: <R|U>_<movie>_<NN> (R = Red Alert 3, U = Uprising; a few movie names exist in both games
with different content). Outputs original/movie/<asset>.wav (the line's slice of the dialogue track),
original/movie_full/<R|U>_<movie>.wav (whole dialogue track, for assembly) and lines/movie.csv with
start/dur/movie columns; existing zh/note are kept.
"""
import csv
import json
import os
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io, big, csf, eaxa, textpack, vgm   # noqa: E402
from ra3voice.game import chain_for_game                      # noqa: E402

GAMES = {
    'ra3': (r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3', 'R'),
    'uprising': (r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3 Uprising', 'U'),
}
BATCH = 'movie'
SKIP_RE = re.compile(r'ea_logo', re.I)
SEG_RE = re.compile(r'\[\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*\]')
FIELDS = ['asset', 'group', 'games', 'seconds', 'en', 'zh_official', 'zh', 'note', 'movie', 'start', 'dur']
SR = 48000
PAD_BEFORE, PAD_AFTER = 0.15, 0.30


def segments(text):
    """'*[2.3:1.8]Hello![4.6:1.5]I am...' -> [(start, dur, text)]"""
    text = text.lstrip('*')
    marks = list(SEG_RE.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        t = text[m.end():end].strip()
        if t:
            out.append((float(m[1]), float(m[2]), t))
    return out


def movie_subtitles(game_dir, lang):
    """{MOVIE: [(start, dur, text)]} from SUBTITLE:<MOVIE>[_NN] labels."""
    chain = chain_for_game(game_dir, lang)
    by = {}
    for n in ('data\\gamestrings.csf', 'data\\gamestrings_temp.csf'):
        if n not in chain.where:
            continue
        for k, v in csf.parse(chain.read([n])[n]).items():
            if not k.upper().startswith('SUBTITLE:'):
                continue
            name = k.split(':', 1)[1].upper()
            m = re.match(r'^(.*?)(?:_(\d+))?$', name)
            by.setdefault(m[1], {}).setdefault(int(m[2] or 0), v)
    return {mv: sorted((s for _, v in sorted(parts.items()) for s in segments(v)), key=lambda s: s[0])
            for mv, parts in by.items()}


def dialogue_track(snd):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'm.snd')
        open(p, 'wb').write(snd)
        x, sr = vgm.decode_file(p)
    assert sr == SR, sr
    x = x.reshape(len(x), -1)
    if x.shape[1] == 6:
        return x[:, 1].copy()
    return vgm.to_mono(x) if x.shape[1] > 1 else x[:, 0]


def pause_split(x, min_gap=0.45, min_len=0.4):
    """Speech spans [(start, dur)] of a track without subtitles."""
    f = SR // 50
    e = np.sqrt(np.mean(x[:len(x) // f * f].astype(np.float64).reshape(-1, f) ** 2, axis=1))
    if not len(e) or e.max() == 0:
        return []
    on = 20 * np.log10(e / e.max() + 1e-9) > -35
    spans, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and (on[j] or (j + int(min_gap * 50) < len(on) and on[j:j + int(min_gap * 50)].any())):
                j += 1
            if (j - i) / 50 >= min_len:
                spans.append((i / 50, (j - i) / 50))
            i = j
        else:
            i += 1
    return spans


def match_zh(en_segs, zh_segs):
    """Pair each English segment with the Traditional Chinese segment(s) starting nearest to it."""
    if not zh_segs:
        return [''] * len(en_segs)
    if len(zh_segs) == len(en_segs):
        return [t for _, _, t in zh_segs]
    out = [''] * len(en_segs)
    for s, _, t in zh_segs:
        k = min(range(len(en_segs)), key=lambda i: abs(en_segs[i][0] - s))
        out[k] += t
    return out


def main():
    old = {}
    path = os.path.join(ROOT, 'lines', f'{BATCH}.csv')
    if os.path.exists(path):
        with open(path, encoding='utf-8-sig') as f:
            old = {r['asset']: r for r in csv.DictReader(f)}
    seg_dir = os.path.join(ROOT, 'original', BATCH)
    full_dir = os.path.join(ROOT, 'original', BATCH + '_full')
    os.makedirs(seg_dir, exist_ok=True)
    os.makedirs(full_dir, exist_ok=True)
    rows = []
    for game, (gdir, tag) in GAMES.items():
        en_subs = movie_subtitles(gdir, 'english')
        zh_subs = movie_subtitles(gdir, 'chinese_t')
        pack = os.path.join(gdir, 'Data', 'EnglishMovieAudio.big')
        names = [n for n, _, _ in big.read_index(pack) if n.endswith('.snd') and not SKIP_RE.search(n)]

        def work(n):
            movie = os.path.basename(n)[:-4]
            snd = big.read_files(pack, [n])[n]
            x = dialogue_track(snd)
            base = f'{tag}_{movie}'
            audio_io.save_wav(os.path.join(full_dir, base + '.wav'), x, SR)
            subs = en_subs.get(movie.upper(), [])
            zh = match_zh(subs, zh_subs.get(movie.upper(), [])) if subs else []
            spans = [(s, d, t) for s, d, t in subs] if subs else [(s, d, '') for s, d in pause_split(x)]
            out = []
            for i, (s, d, t) in enumerate(spans, 1):
                a = max(0, int((s - PAD_BEFORE) * SR))
                b = min(len(x), int((s + d + PAD_AFTER) * SR))
                if b - a < SR // 10:
                    continue
                asset = f'{base}_{i:02d}'
                audio_io.save_wav(os.path.join(seg_dir, asset + '.wav'), x[a:b], SR)
                o = old.get(asset, {})
                out.append({'asset': asset, 'group': base, 'games': game, 'seconds': f'{d:.2f}',
                            'en': t or o.get('en', ''), 'zh_official': textpack.to_simplified(zh[i - 1]).strip() if zh else '',
                            'zh': o.get('zh', ''), 'note': o.get('note', ''), 'movie': movie, 'start': f'{s:.2f}',
                            'dur': f'{d:.2f}'})
            return eaxa.channels(snd), out

        with ThreadPoolExecutor(8) as ex:
            results = list(ex.map(work, names))
        for _, out in results:
            rows += out
        print(f'{game}: {len(names)} movies ({sum(1 for c, _ in results if c == 6)} six-channel), '
              f'{sum(len(o) for _, o in results)} lines, {sum(1 for _, o in results for r in o if r["zh_official"])} with subtitles')
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    units_path = os.path.join(ROOT, 'units.json')
    units = json.load(open(units_path, encoding='utf-8'))
    units[BATCH] = {'name_zh': '过场视频', 'prefixes': sorted({r['group'] for r in rows}), 'fx': {}}
    json.dump(units, open(units_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'{BATCH}: {len(rows)} lines, {sum(float(r["seconds"]) for r in rows) / 60:.0f} min of speech')


if __name__ == '__main__':
    main()
