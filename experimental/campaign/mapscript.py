"""Our own RA3 map / script tooling (no WorldBuilder): read a .map into a chunk tree, write it back byte for byte,
and turn its scripts into readable text.

  python -I -X utf8 experimental/campaign/mapscript.py selftest          # round-trip every retail campaign map
  python -I -X utf8 experimental/campaign/mapscript.py dump <archive> <map path> [out.txt]

Chunk file (after the RefPack / 'EAR' layers, see mapfile.py): 'CkMp', name table, then chunks of
u32 id, u16 version, u32 size, payload. A node keeps the bytes before its first child chunk as `head` (for leaf
chunks: the whole payload), so writing back needs no knowledge of the fields; decoding is a separate view.
Script content (Condition / ScriptAction / ScriptActionFalse): u32 content type, u32 name key (u8 3 + u24 index into
the name table, e.g. CONDITION_TRUE), u32 argument count, arguments: u32 type, then 3 x f32 for a 3D coordinate
(type 16) or i32 + f32 + u16-prefixed string.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mapfile                                    # noqa: E402
from ra3voice import big, refpack                 # noqa: E402

# chunks whose payload is: some header fields, then child chunks (the rest are leaves or pure containers)
MIXED = {'Script', 'ScriptGroup'}
CONTAINERS = {'PlayerScriptsList', 'ScriptList', 'OrCondition', 'MPPositionList', 'LibraryMapLists',
              'WaypointsList', 'ObjectsList', 'TriggerAreas', 'BuildLists', 'SidesList'}
CONTENT = {'Condition', 'ScriptAction', 'ScriptActionFalse'}
COORD3D = 16


class Node:
    __slots__ = ('name', 'ver', 'head', 'kids')

    def __init__(self, name, ver, head, kids):
        self.name, self.ver, self.head, self.kids = name, ver, head, kids


def _children(d, start, end, table):
    """Parse [start, end) as chunks; None unless it parses exactly."""
    out, p = [], start
    while p < end:
        if p + 10 > end:
            return None
        cid, ver, size = struct.unpack_from('<IHI', d, p)
        if cid not in table or p + 10 + size > end:
            return None
        out.append((table[cid], ver, p + 10, p + 10 + size))
        p += 10 + size
    return out


def _first_child(d, start, end, table):
    """Offset where a valid chunk sequence covering the rest of [start, end) begins (for MIXED chunks)."""
    for q in range(start, end - 9):
        kids = _children(d, q, end, table)
        if kids:
            return q, kids
    return end, []


def parse_nodes(d, start, end, table):
    nodes = []
    for name, ver, a, b in _children(d, start, end, table) or []:
        nodes.append(parse_node(d, name, ver, a, b, table))
    return nodes


def parse_node(d, name, ver, a, b, table):
    if name in CONTAINERS:
        kids = _children(d, a, b, table)
        if kids is not None:
            return Node(name, ver, b'', [parse_node(d, n, v, x, y, table) for n, v, x, y in kids])
    if name in MIXED:
        q, kids = _first_child(d, a, b, table)
        return Node(name, ver, d[a:q], [parse_node(d, n, v, x, y, table) for n, v, x, y in kids])
    return Node(name, ver, d[a:b], [])


class MapFile:
    def __init__(self, raw):
        self.raw = raw
        d = mapfile.unwrap(raw)
        self.table, p = mapfile.names(d)
        self.names_blob = d[:p]
        self.ids = {v: k for k, v in self.table.items()}
        self.nodes = parse_nodes(d, p, len(d), self.table)
        self.chunk_bytes = d

    def _write(self, node):
        body = node.head + b''.join(self._write(k) for k in node.kids)
        return struct.pack('<IHI', self.ids[node.name], node.ver, len(body)) + body

    def chunk_file(self):
        return self.names_blob + b''.join(self._write(n) for n in self.nodes)

    def map_file(self):
        """The .map the game reads: RefPack('EAR\\0' + u32 size + RefPack(chunk file)), stored (not compressed).
        The size is that of the uncompressed chunk file (retail: 0x51d5c6 for Heidelberg's 5363142 bytes); with the
        compressed length there instead the game hangs at ~60 % of the loading screen."""
        chunks = self.chunk_file()
        inner = refpack.compress_literal(chunks)
        return refpack.compress_literal(b'EAR\0' + struct.pack('<I', len(chunks)) + inner)

    def walk(self, nodes=None, depth=0):
        for n in self.nodes if nodes is None else nodes:
            yield depth, n
            yield from self.walk(n.kids, depth + 1)

    # ------------------------------------------------------------- readable view of the scripts
    def key(self, v):
        return self.table.get(v >> 8, f'?{v:#x}') if v & 0xFF == 3 else f'{v:#x}'

    def content(self, node):
        d = node.head
        ctype, key, n = struct.unpack_from('<III', d, 0)
        p, args = 12, []
        for _ in range(n):
            t = struct.unpack_from('<I', d, p)[0]
            p += 4
            if t == COORD3D:
                args.append(('coord', struct.unpack_from('<fff', d, p)))
                p += 12
            else:
                i, f, ln = struct.unpack_from('<ifH', d, p)
                s = d[p + 10:p + 10 + ln].decode('latin-1')
                p += 10 + ln
                args.append((t, s if s else (f if f else i)))
        return self.key(key), args, d[p:]

    def set_string_args(self, content_name, old, new):
        """Every script content named `content_name` (e.g. MOVIE_PLAY_RADAR) gets string argument `old` replaced by
        `new`; the node is re-encoded and chunk sizes follow when the file is written. Returns how many changed."""
        changed = 0
        for _, n in self.walk():
            if n.name not in CONTENT or self.key(struct.unpack_from('<I', n.head, 4)[0]) != content_name:
                continue
            d = n.head
            ctype, key, cnt = struct.unpack_from('<III', d, 0)
            out, p, hit = bytearray(d[:12]), 12, False
            for _ in range(cnt):
                t = struct.unpack_from('<I', d, p)[0]
                if t == COORD3D:
                    out += d[p:p + 16]
                    p += 16
                    continue
                i, f, ln = struct.unpack_from('<ifH', d, p + 4)
                s = d[p + 14:p + 14 + ln]
                if s.decode('latin-1') == old:
                    s, hit = new.encode('latin-1'), True
                out += struct.pack('<IifH', t, i, f, len(s)) + s
                p += 14 + ln
            if hit:
                n.head = bytes(out + d[p:])
                changed += 1
        return changed

    @staticmethod
    def string(d, p):
        ln = struct.unpack_from('<H', d, p)[0]
        return d[p + 2:p + 2 + ln].decode('latin-1'), p + 2 + ln

    def script_text(self):
        lines = []
        for depth, n in self.walk():
            pad = '  ' * depth
            if n.name in ('ScriptGroup', 'Script'):
                title, _ = self.string(n.head, 0)
                lines.append(f'{pad}{n.name}: {title}')
            elif n.name in CONTENT:
                name, args, rest = self.content(n)
                kind = {'Condition': 'IF', 'ScriptAction': 'DO', 'ScriptActionFalse': 'ELSE'}[n.name]
                lines.append(f'{pad}{kind} {name}(' + ', '.join(repr(a[1]) for a in args) + ')'
                             + (f'  +{rest.hex()}' if rest else ''))
            elif n.name == 'OrCondition' and depth:
                lines.append(f'{pad}OR')
        return '\n'.join(lines)


def campaign_maps():
    p = os.path.join(mapfile.DATA, 'MapsCampaign.big')
    return p, [n for n, _, _ in big.read_index(p) if n.lower().endswith('.map')]


def selftest():
    arc, maps = campaign_maps()
    ok = 0
    for n in maps:
        m = MapFile(big.read_files(arc, [n])[n])
        same = m.chunk_file() == m.chunk_bytes
        again = MapFile(m.map_file()).chunk_file() == m.chunk_bytes
        scripts = sum(1 for _, x in m.walk() if x.name == 'Script')
        print(f'{"OK " if same and again else "BAD"} {n.split(chr(92))[-1]:45} {scripts:4d} scripts')
        ok += same and again
    print(f'{ok}/{len(maps)} maps round-trip byte for byte')
    return ok == len(maps)


def main():
    if sys.argv[1] == 'selftest':
        sys.exit(0 if selftest() else 1)
    if sys.argv[1] == 'dump':
        arc = os.path.join(mapfile.DATA, sys.argv[2]) if not os.path.isabs(sys.argv[2]) else sys.argv[2]
        m = MapFile(big.read_files(arc, [sys.argv[3]])[sys.argv[3]])
        text = m.script_text()
        if len(sys.argv) > 4:
            open(sys.argv[4], 'w', encoding='utf-8').write(text)
        else:
            print(text[:6000])


if __name__ == '__main__':
    main()
