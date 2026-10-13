"""In-game probe: can streamed (EALayer3) mission dialogue be replaced with XAS?

  python tools/probe_mission.py <wav dir> [--game ra3]

Takes <Asset>.wav files (e.g. MA01_AlliedIntel01.wav), writes them as header-less XAS blocks into
Data\\CNVoice_mprobe.big and rewrites their in-bin SNR headers. The installed core archive is
replaced by one that carries the full release (all four components) plus these probe lines, and
the probe archive is added to the same SkuDefs the installer patched. Run the normal installer
afterwards to remove the probe (it deletes every CNVoice*.big and restores the SkuDefs).
"""
import argparse
import glob
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import audio_io, big, snr                      # noqa: E402
from ra3voice.game import AudioStream, chain_for_game         # noqa: E402
import ra3cv                                                  # noqa: E402

PROBE_BIG = 'CNVoice_mprobe.big'


def release_lengths(stream, game):
    """Sample counts of every clip in the built component archives (so the core stays consistent)."""
    by_cdata = {a.cdata_path.lower(): a for a in stream.assets}
    lengths = {}
    for comp in ra3cv.COMPONENTS:
        path = os.path.join(ROOT, 'dist', game, ra3cv.COMP_BIG.format(comp))
        names = [n for n, _, _ in big.read_index(path)]
        for n, blob in big.read_files(path, names).items():
            lengths[by_cdata[n.lower()].short_name] = snr.parse(blob)['num_samples']
    return lengths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('wavs')
    ap.add_argument('--game', default='ra3', choices=list(ra3cv.GAMES))
    a = ap.parse_args()
    game_dir = ra3cv.GAMES[a.game]
    stream = AudioStream(chain_for_game(game_dir))
    probe = {}
    for p in sorted(glob.glob(os.path.join(a.wavs, '*.wav'))):
        asset = stream.get(os.path.splitext(os.path.basename(p))[0])
        assert stream.header_in_bin(asset) is not None, f'{asset.short_name} is not a streamed AudioFile'
        sr = stream._layout(asset)[0]
        probe[asset.short_name] = audio_io.to_int16(audio_io.load_mono(p, sr) * 0.9)
    lengths = release_lengths(stream, a.game)
    lengths.update({n: len(x) for n, x in probe.items()})
    data = os.path.join(game_dir, 'Data')
    big.write(os.path.join(data, PROBE_BIG), stream.cdata_files(probe))
    big.write(os.path.join(data, ra3cv.CORE_BIG), [stream.bin_file(lengths)])
    for c in ra3cv.COMPONENTS:  # make sure all four components are installed alongside
        shutil.copyfile(os.path.join(ROOT, 'dist', a.game, ra3cv.COMP_BIG.format(c)),
                        os.path.join(data, ra3cv.COMP_BIG.format(c)))
    line = f'add-big Data\\{PROBE_BIG}'
    patched = 0
    for sku in glob.glob(os.path.join(game_dir, '*.SkuDef')):
        text = open(sku, encoding='latin-1', newline='').read()
        if 'CNVoice_core.big' not in text or PROBE_BIG in text:
            continue
        eol = '\r\n' if '\r\n' in text else '\n'
        text = re.sub(r'(?m)^(add-big Data\\CNVoice_core\.big)', line.replace('\\', '\\\\') + eol + r'\1', text, count=1)
        open(sku, 'w', encoding='latin-1', newline='').write(text)
        patched += 1
    print(f'probe: {sorted(probe)} -> {PROBE_BIG}; core rebuilt with {len(lengths)} lengths; {patched} SkuDefs patched')


if __name__ == '__main__':
    main()
