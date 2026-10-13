"""Separate the English vocals of every dubbed movie once (GPU, Demucs) and cache them.

  python tools/separate_movies.py [--game ra3|uprising]

Output: work/sep/<game>/<movie>.npy  int16 [samples, channels] vocals (LFE left at zero).
ra3cv build uses them to remove the dubbed lines' English from every speaker channel.
Honours gpu_limit.json (duty cycle + VRAM cap). Existing files are skipped, so it can be resumed.
"""
import argparse
import csv
import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import big, movie, separate                    # noqa: E402

GAMES = {
    'ra3': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3',
    'uprising': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3 Uprising',
}
SEP = os.path.join(ROOT, 'work', 'sep')
GROUPS = {6: [(0, 2), (3, 4), (1,)], 2: [(0, 1)], 1: [(0,)]}


def cache_path(game, name):
    return os.path.join(SEP, game, name + '.npy')


def dubbed_movies(game):
    with open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f) if r['games'] == game]
    return sorted({r['movie'] for r in rows
                   if os.path.exists(os.path.join(ROOT, 'voices', 'movie', r['asset'] + '.wav'))})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', choices=['all', *GAMES], default='all')
    a = ap.parse_args()
    for g in (GAMES if a.game == 'all' else [a.game]):
        pack = os.path.join(GAMES[g], 'Data', 'EnglishMovieAudio.big')
        os.makedirs(os.path.join(SEP, g), exist_ok=True)
        todo = [m for m in dubbed_movies(g) if not os.path.exists(cache_path(g, m))]
        print(f'{g}: {len(todo)} movies to separate', flush=True)
        for i, m in enumerate(todo, 1):
            name = 'data\\movies\\' + m + '.snd'
            x = movie.decode(big.read_files(pack, [name])[name])
            voc = np.zeros_like(x)
            for grp in GROUPS[x.shape[1]]:
                v = separate.vocals(x[:, list(grp)] if len(grp) > 1 else x[:, grp[0]], movie.SR)
                voc[:, list(grp)] = v if v.ndim == 2 else v[:, None]
            with tempfile.NamedTemporaryFile(dir=os.path.join(SEP, g), suffix='.tmp', delete=False) as f:
                np.save(f, voc)
            os.replace(f.name, cache_path(g, m))
            if i % 25 == 0:
                print(f'PROGRESS {g} {i}/{len(todo)}', flush=True)
        print(f'FINISHED {g}', flush=True)


if __name__ == '__main__':
    main()
