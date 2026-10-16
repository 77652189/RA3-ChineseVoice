"""Chinese EVA under the Corona mod, without touching Corona's encrypted package.

  python -I -X utf8 tools/corona_eva.py stats
  python -I -X utf8 tools/corona_eva.py probe [ASSET ...]     # a few lines, to hear whether the override works
  python -I -X utf8 tools/corona_eva.py remove                # take every file this tool wrote back out

Corona brings its own EVA, and its own length table for it, which loads before our CNVoice archives. Its launcher
puts CoronaData\\mods\\corona first on the game's search path, so a loose data\\audio\\cdata\\<file>.cdata there
is found before the copy inside Corona's .lyi. We cannot change Corona's sample counts, so each Chinese EVA line is
fitted to exactly the original English line's sample count: silence after a shorter line, a slight speed-up for a
longer one. Files written are listed in CoronaData\\mods\\corona\\CNVoice_eva.txt for removal.

STATUS 2026-10-15: blocked. Corona launcher 3.12.9710.1 deletes and recreates CoronaData\\mods every launch, so the
loose files are gone before the game starts (probe lines stayed English). Waiting on the Corona team for an option
to load an extra archive before Corona's, or to keep mods\\corona\\data\\audio. Their .lyi is encrypted: not touched.
The fitting itself (419 of 426 lines exactly as long as the original, 7 over 1.35x left to Corona) is ready.
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io, stretch                          # noqa: E402
from ra3voice.game import AudioStream, chain_for_game            # noqa: E402

GAME = r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3'
CORONA = os.path.join(os.environ['APPDATA'], 'CoronaLauncher', 'CoronaData', 'mods', 'corona')
LIST = os.path.join(CORONA, 'CNVoice_eva.txt')
EVA = os.path.join(ROOT, 'voices', 'eva')
MAX_RATE = 1.35          # faster than this sounds rushed; such lines are left to Corona (reported)


def eva_assets(stream):
    names = sorted(os.path.splitext(n)[0] for n in os.listdir(EVA) if n.endswith('.wav'))
    return [(n, stream.get(n.split('@')[0])) for n in names if n.split('@')[0].lower() in stream.by_name and '@uprising' not in n]


def fitted(stream, asset, wav):
    """Our line at the asset's rate, exactly as long as the original. None if it would need > MAX_RATE."""
    sr, _ = stream._layout(asset)
    n = stream.num_samples(asset)
    x = audio_io.load_mono(wav, sr).astype(np.float64)
    if len(x) > n:
        rate = len(x) / n
        if rate > MAX_RATE:
            return None, rate
        x = stretch.wsola(x, rate, sr)
    y = np.zeros(n)
    y[:min(n, len(x))] = x[:n]
    y[-min(n, int(0.005 * sr)):] *= np.linspace(1, 0, min(n, int(0.005 * sr)))     # no click at a cut
    ref, _ = stream.decode(asset)
    return audio_io.to_int16(audio_io.match_level(y, ref)), len(x) / n if len(x) > n else 1.0


def main():
    cmd = sys.argv[1]
    if cmd == 'remove':
        if os.path.exists(LIST):
            for rel in open(LIST, encoding='utf-8').read().split():
                p = os.path.join(CORONA, rel)
                if os.path.exists(p):
                    os.remove(p)
            os.remove(LIST)
        print('removed')
        return
    stream = AudioStream(chain_for_game(GAME))
    items = eva_assets(stream)
    if cmd == 'stats':
        rates = []
        for name, a in items:
            sr, _ = stream._layout(a)
            n = stream.num_samples(a)
            x = audio_io.load_mono(os.path.join(EVA, name + '.wav'), sr)
            rates.append(len(x) / n)
        r = np.array(rates)
        print(f'{len(r)} EVA lines: shorter or equal {int((r <= 1).sum())}, up to 1.15x {int(((r > 1) & (r <= 1.15)).sum())}, '
              f'1.15-{MAX_RATE}x {int(((r > 1.15) & (r <= MAX_RATE)).sum())}, over {MAX_RATE}x {int((r > MAX_RATE).sum())}')
        return
    want = {s.lower() for s in sys.argv[2:]}
    written, skipped = [], []
    for name, a in items:
        if want and name.split('@')[0].lower() not in want:
            continue
        pcm, rate = fitted(stream, a, os.path.join(EVA, name + '.wav'))
        if pcm is None:
            skipped.append(f'{name} ({rate:.2f}x)')
            continue
        (path, blob), = stream.cdata_files({a.short_name: pcm})
        rel = path.replace('/', '\\')
        dst = os.path.join(CORONA, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(blob)
        written.append(rel)
    old = open(LIST, encoding='utf-8').read().split() if os.path.exists(LIST) else []
    with open(LIST, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sorted(set(old) | set(written))))
    print(f'{len(written)} files -> {CORONA}' + (f'; too long, left to Corona: {", ".join(skipped)}' if skipped else ''))


if __name__ == '__main__':
    main()
