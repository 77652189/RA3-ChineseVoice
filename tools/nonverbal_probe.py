"""Extract the unit lines that catalog.py skips as non-verbal (NONVERBAL_RE) so they can be checked for words.

Run Whisper over the result before widening or narrowing NONVERBAL_RE: crash/fall/fear lines were found to be
shouted sentences this way; Die* clips are screams that Whisper only hallucinates words into.

  python tools/nonverbal_probe.py

Writes work/nonverbal/<asset>.wav and work/nonverbal/list.csv (asset, group, games, seconds).
"""
import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ra3voice import audio_io, snr                         # noqa: E402
from ra3voice.game import AudioStream, chain_for_game        # noqa: E402
from catalog import GAMES, NONVERBAL_RE, UNIT_RE             # noqa: E402

OUT = os.path.join(ROOT, 'work', 'nonverbal')


def main():
    os.makedirs(OUT, exist_ok=True)
    picked = {}
    streams = {g: AudioStream(chain_for_game(d)) for g, d in GAMES.items()}
    for g, s in streams.items():
        for a in s.assets:
            m = UNIT_RE.match(a.short_name)
            if not m or not NONVERBAL_RE.search(re.sub(r'[a-z]$', '', m['cat'])):
                continue
            e = picked.setdefault(a.short_name.lower(), {'asset': a.short_name, 'group': m['group'], 'src': {}})
            e['src'][g] = a
    rows = []
    for g in ('uprising', 'ra3'):
        todo = [e for e in picked.values() if g in e['src'] and (g == 'uprising' or 'uprising' not in e['src'])]
        blobs = streams[g].read_cdata([e['src'][g] for e in todo])
        for e in todo:
            try:
                pcm, sr = snr.decode(blobs[e['src'][g].short_name])
            except ValueError as err:
                print('skip', e['asset'], err)
                continue
            audio_io.save_wav(os.path.join(OUT, e['asset'] + '.wav'), pcm, sr)
            rows.append({'asset': e['asset'], 'group': e['group'], 'games': '+'.join(sorted(e['src'])),
                         'seconds': f'{len(pcm) / sr:.2f}'})
    rows.sort(key=lambda r: r['asset'].lower())
    with open(os.path.join(OUT, 'list.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['asset', 'group', 'games', 'seconds'])
        w.writeheader()
        w.writerows(rows)
    print(len(rows), 'clips,', len({r['group'] for r in rows}), 'groups,',
          f"{sum(float(r['seconds']) for r in rows):.0f} s total")


if __name__ == '__main__':
    main()
