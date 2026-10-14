"""Put released lines back into voices/ (and clean/) from the CNVoice archives installed in the games.

  python tools/restore_from_install.py allied soviet empire --keep AUApoll_VoiCrasha SUNatas_VoiFeara ...

For every asset of the batches whose freshly built audio (dist/) differs from the installed release, the
release audio is decoded and written over voices/<batch>/<asset>.wav and clean/<batch>/<asset>.wav, except
the assets named in --keep (the lines that are meant to change). Use it when a whole-batch re-run of
pick.py re-chose takes or re-EQ'd groups of lines that players already have (pick scores depend on the
pause detector, which changed after some batches were last picked). The installed build must be the
release the next patch is based on (see Data/CNVoice_installed.json).
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ra3voice import audio_io, big, snr                      # noqa: E402
from ra3voice.game import AudioStream, chain_for_game        # noqa: E402
from catalog import GAMES                                    # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('batches', nargs='+')
    ap.add_argument('--keep', nargs='*', default=[])
    args = ap.parse_args()
    keep = {k.lower() for k in args.keep}
    done = set()
    for g in ('uprising', 'ra3'):        # Uprising's copy wins when both games have the asset, as in catalog.py
        stream = AudioStream(chain_for_game(GAMES[g]))
        by_path = {a.cdata_path.lower(): a.short_name for a in stream.assets}
        for b in args.batches:
            name = f'CNVoice_{b}.big'
            rel, cur = os.path.join(GAMES[g], 'Data', name), os.path.join(ROOT, 'dist', g, name)
            paths = [n for n, _, _ in big.read_index(cur)]
            old = dict(big.read_files(rel, [n for n, _, _ in big.read_index(rel)]))
            new = big.read_files(cur, paths)
            n_restored = 0
            for p in paths:
                asset = by_path.get(p.lower())
                if not asset or asset.lower() in keep or asset.lower() in done or p not in old or old[p] == new[p]:
                    continue
                pcm, sr = snr.decode(old[p])
                for d in ('voices', 'clean'):
                    audio_io.save_wav(os.path.join(ROOT, d, b, asset + '.wav'), pcm, sr)
                done.add(asset.lower())
                n_restored += 1
            print(f'{g} {b}: restored {n_restored} lines from the installed release')


if __name__ == '__main__':
    main()
