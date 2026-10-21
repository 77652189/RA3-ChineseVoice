"""List the sounds RA3 map scripts wait for (condition HAS_FINISHED_AUDIO) -> sync_lock.json.

Those lines must keep the original length (ra3voice/fitlen.py): in online co-op each player's game times the
script by its own audio.bin, so a different length on one side desyncs the game mid-mission.

  python -I -X utf8 tools/sync_lock.py          # scans every Data/Maps*.big of RA3 (Uprising has no online play);
                                                 # tutorials are skipped (single-player only)

Map format (CkMp): a table of chunk / key names, then chunks <id u32><version u16><size i32>. A Condition chunk
(version 6) starts <type i32><name key u32 = (index << 8) | 3><parameter count i32>, each parameter
<type i32><int i32><float f32><string: u16 length + bytes>."""
import glob
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import big, refpack                                # noqa: E402
from ra3voice.game import AudioStream, chain_for_game             # noqa: E402

GAME = r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3'
OUT = os.path.join(ROOT, 'sync_lock.json')


def load_map(d):
    for _ in range(3):
        if d[:4] == b'EAR\0':
            d = d[8:]
        if not refpack.is_refpack(d):
            break
        d = refpack.decompress(d)
    return d


def key_names(d):
    if d[:4] != b'CkMp':
        raise ValueError('not a CkMp map')
    off, out = 8, {}
    for _ in range(struct.unpack_from('<I', d, 4)[0]):
        ln = d[off]
        name = d[off + 1:off + 1 + ln].decode('latin-1')
        off += 1 + ln
        out[struct.unpack_from('<I', d, off)[0]] = name
        off += 4
    return out


def audio_waits(d):
    """Sound names in the map's HAS_FINISHED_AUDIO conditions (one entry per condition)."""
    names = key_names(d)
    ids = {v: k for k, v in names.items()}
    if 'HAS_FINISHED_AUDIO' not in ids:
        return []
    cond, want = ids['Condition'], ids['HAS_FINISHED_AUDIO']
    out = []
    for m in re.finditer(re.escape(struct.pack('<I', cond)), d):
        p = m.start()
        ver, size = struct.unpack_from('<Hi', d, p + 4)
        if not (16 <= size < 5000 and ver < 10):
            continue
        body = d[p + 10:p + 10 + size]
        _, key, n = struct.unpack_from('<iIi', body)
        if key >> 8 != want or not 0 < n < 10:
            continue
        q = 12
        _, _, _, ln = struct.unpack_from('<iifH', body, q)
        out.append(body[q + 14:q + 14 + ln].decode('latin-1'))
    return out


def main():
    stream = AudioStream(chain_for_game(GAME))
    files = {a.short_name.lower(): a.short_name for a in stream.assets}
    waits, unknown = {}, set()
    for path in sorted(glob.glob(os.path.join(GAME, 'Data', 'Maps*.big'))):
        idx = big.read_index(path)
        maps = [e[0] for e in idx if e[0].lower().endswith('.map')]
        for name, data in big.read_files(path, maps).items():
            if os.path.basename(name).lower().startswith('tutorial'):
                continue                  # tutorials are single-player only
            for s in audio_waits(load_map(data)):
                if s.lower() in files:
                    waits.setdefault(files[s.lower()], set()).add(os.path.basename(name)[:-4])
                else:
                    unknown.add(s)        # events with no AudioFile of that name (unused / misspelt in the map)
    lock = {'ra3': sorted(waits), 'maps': {k: sorted(v) for k, v in sorted(waits.items())},
            'not_audio_files': sorted(unknown)}
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(lock, f, indent=1, ensure_ascii=False)
    print(f'{len(waits)} sounds waited on by map scripts -> {OUT} ({len(unknown)} names are not AudioFiles)')


if __name__ == '__main__':
    main()
