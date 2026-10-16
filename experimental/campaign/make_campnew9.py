"""Fourth campaign, index side (CampNew9): does the game take FactionIndex=3?

  python -I -X utf8 experimental/campaign/make_campnew9.py   -> Documents\\Red Alert 3\\Mods\\CampNew9

CampNew8 showed the Allies card still opens retail Allies with CNV first in the CampaignEnumerator, so the index
is not a plain enumerator position. Here the faction menu's FSCommand string itself is changed: the APT constant
'%Campaign_SetFaction?FactionIndex=' (AptConstData of data\\aptui\\fes_m_factionmenu.5, Core5.big) is pointed at
a new string '%Campaign_SetFaction?FactionIndex=3&x=' appended to the constant file, so every card asks for
campaign 3 (the card's own index lands in a dummy parameter). CampaignEnumerator = Allies, Soviet, Japan, CNV.

Constant file (inside the instance: u32 0, u32 12 = its offset (relocated), u32 size, then the file): 'Apt
constant file' + 0x1a 0 0, u32 apt data offset, u32 item count, u32 32, then items of u32 type + u32 value; type
1 = string at that offset from the file start. The bytecode refers to items by index, so appending a string and
repointing one item changes nothing else.

Result (bench, 2026-10-16): the briefing screen comes up titled 'undefined' with no intro movie and the game
crashes (0xc0000005) at ~68 s. The value reached the engine but did not resolve; CampNew10 later showed that any
extra text after the index already breaks it, so this does not settle whether index 3 itself could work.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_campnew8 as c8                      # noqa: E402
import mapxml                                   # noqa: E402

c7, c4, c2 = c8.c7, c8.c4, c8.c2
NAME = 'CampNew9'
c4.NAME = c2.NAME = NAME
c2.SRC_DIR = os.path.join(c2.SDK, 'Mods', NAME, 'data')
c2.BUILT = os.path.join(c2.SDK, 'BuiltMods', 'mods', NAME.lower(), 'data')
c2.OUT = c4.OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', NAME)
c7.MAP_MOD = NAME + 'Map'
c8.ORDER[:] = ['Allies', 'Soviet', 'Japan', 'CNV']
APT = 'data\\aptui\\fes_m_factionmenu.5.'
OLD = b'%Campaign_SetFaction?FactionIndex='
NEW = os.environ.get('CNV_FSCOMMAND', '%Campaign_SetFaction?FactionIndex=3&x=').encode('ascii')


def repoint(const):
    """The constant instance with the item holding OLD pointed at NEW (appended)."""
    base = struct.unpack_from('<I', const, 4)[0]
    f = bytearray(const[base:])
    count = struct.unpack_from('<I', f, 24)[0]
    hit = 0
    for k in range(count):
        t, v = struct.unpack_from('<II', f, 32 + 8 * k)
        if t == 1 and f[v:v + len(OLD) + 1] == OLD + b'\0':
            at = len(f) + (-len(f)) % 4
            f += b'\0' * (at - len(f)) + NEW + b'\0'
            struct.pack_into('<II', f, 32 + 8 * k, 1, at)
            hit += 1
    assert hit == 1, hit
    f += b'\0' * ((-len(f)) % 4)
    return const[:8] + struct.pack('<I', len(f)) + const[12:base] + bytes(f)


def apt_files():
    (h, E, chunks, bufs), raw = mapxml.read_stream(APT, mapxml._archive_get('Core5.big'))
    k = next(k for k, e in enumerate(E) if mapxml.sa.cstr(bufs[2], e[6]).startswith(b'AptConstData:'))
    chunks = [list(c) for c in chunks]
    chunks[k][0] = repoint(chunks[k][0])
    E = [list(e) for e in E]
    E[k][8] = len(chunks[k][0])
    files = mapxml.write_stream(h, E, chunks, bufs, (raw[1][:4], raw[2][:4], raw[3][:4]))
    print('faction menu FSCommand ->', NEW.decode())
    return [(APT + x, v) for x, v in zip(('manifest', 'bin', 'relo', 'imp'), files)]


_strings = c4.c3.strings
c4.c3.strings = lambda: _strings() + apt_files()

if __name__ == '__main__':
    c4.main()
