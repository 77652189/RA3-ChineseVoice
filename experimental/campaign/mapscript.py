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
                args.append((t, struct.unpack_from('<fff', d, p)))
                p += 12
            else:
                i, f, ln = struct.unpack_from('<ifH', d, p)
                s = d[p + 10:p + 10 + ln].decode('latin-1')
                p += 10 + ln
                # one slot set (str / float / int), or the raw (i, f, s) when an enum carries both index and name
                used = [x for x in (i, f, s) if x]
                args.append((t, (i, f, s) if len(used) > 1 else s if s else f if f else i))
        return self.key(key), args, d[p:]

    def set_string_args(self, content_name, old, new):
        """Every script content named `content_name` (e.g. MOVIE_PLAY_RADAR) gets string argument `old` replaced by
        `new`; the node is re-encoded and chunk sizes follow when the file is written. Returns how many changed."""
        changed = 0
        for _, n in self.walk():
            if n.name not in CONTENT or self.key(struct.unpack_from('<I', n.head, 4)[0]) != content_name:
                continue
            head = _replace_arg(n.head, old, new)
            if head is not None:
                n.head = head
                changed += 1
        return changed

    def duplicate_contents(self, old, new):
        """Every action with a string argument `old` (e.g. a unit name) gets a copy right after it with that
        argument set to `new` -- a new unit is moved, handed over, deleted ... wherever the old one is. Conditions
        are left alone (a copy inside an OR group would AND it in). Returns the count."""
        added = 0
        for _, n in list(self.walk()):
            kids = []
            for k in n.kids:
                kids.append(k)
                if k.name in ('ScriptAction', 'ScriptActionFalse'):
                    head = _replace_arg(k.head, old, new)
                    if head is not None:
                        kids.append(Node(k.name, k.ver, head, []))
                        added += 1
            n.kids = kids
        return added

    @staticmethod
    def string(d, p):
        ln = struct.unpack_from('<H', d, p)[0]
        return d[p + 2:p + 2 + ln].decode('latin-1'), p + 2 + ln

    # ------------------------------------------------------------- editing
    def name_id(self, name):
        """Id of `name` in the CkMp name table (chunk names and script content names share it); appended if new."""
        if name not in self.ids:
            cid = max(self.table) + 1
            self.table[cid], self.ids[name] = name, cid
            raw = name.encode('latin-1')
            count = struct.unpack_from('<I', self.names_blob, 4)[0] + 1
            self.names_blob = (self.names_blob[:4] + struct.pack('<I', count) + self.names_blob[8:]
                               + bytes([len(raw)]) + raw + struct.pack('<I', cid))
        return self.ids[name]

    def version(self, chunk):
        return next(n.ver for _, n in self.walk() if n.name == chunk)

    def new_content(self, kind, name, *values, enabled=True, inverted=False):
        """A Condition / ScriptAction / ScriptActionFalse node calling `name` (e.g. SHOW_MILITARY_CAPTION) with
        `values`; content type and argument types come from the retail catalog (script_catalog.json)."""
        entry = catalog()[name]
        assert entry['kind'] == ('Condition' if kind == 'Condition' else 'ScriptAction'), (name, entry['kind'])
        types = entry['args']
        assert len(values) == len(types), f'{name} takes {len(types)} arguments, got {len(values)}'
        body = struct.pack('<III', entry['ctype'], self.name_id(name) << 8 | 3, len(types))
        for t, v in zip(types, values):
            body += encode_arg(t, v)
        body += struct.pack('<I', enabled) + (struct.pack('<I', inverted) if kind == 'Condition' else b'')
        self.name_id(kind)
        return Node(kind, self.version(kind), body, [])

    def new_script(self, name, conditions, actions, else_actions=(), comment='', active=True, one_shot=True,
                   difficulties=(True, True, True), subroutine=False, interval=0):
        """A Script node. `conditions`: list of OR groups, each a list of Condition nodes (ANDed), or a flat list
        for one group; `actions` / `else_actions`: ScriptAction / ScriptActionFalse nodes (new_content).
        Header fields as decoded from retail v4 scripts (OpenSAGE Script.cs): 4 strings, 6 bools (active, one-shot,
        easy, normal, hard, subroutine), u32 evaluation interval, sequential / loop bools, i32 loop count, u8
        sequential target type (1 = none; 0 + '<This Team>' etc. on sequential scripts) + target name, then 'X'.
        These fields reproduce 8192 of the 8896 retail script headers; the rest are sequential scripts."""
        if conditions and isinstance(conditions[0], Node):
            conditions = [conditions]
        head = b''.join(_pstr(s) for s in (name, comment, '', ''))
        head += bytes([active, one_shot, *difficulties, subroutine])
        head += struct.pack('<IBBiB', interval, 0, 0, 0, 1) + _pstr('') + _pstr('X')
        kids = [Node('OrCondition', self.version('OrCondition'), b'', list(g)) for g in conditions]
        kids += list(actions) + list(else_actions)
        self.name_id('OrCondition')
        self.name_id('Script')
        return Node('Script', self.version('Script'), head, kids)

    def scripts(self):
        """name -> (parent node or None for a ScriptList, list holding it, index) for every Script / ScriptGroup."""
        out = {}
        for _, n in self.walk():
            for i, k in enumerate(n.kids):
                if k.name in ('Script', 'ScriptGroup'):
                    out.setdefault(self.string(k.head, 0)[0], (n, n.kids, i))
        return out

    def script(self, name):
        parent, kids, i = self.scripts()[name]
        return kids[i]

    def add_script(self, node, after=None, into=None):
        """Insert `node` after the script / group named `after`, or at the end of the group named `into`."""
        if after is not None:
            _, kids, i = self.scripts()[after]
            kids.insert(i + 1, node)
        else:
            self.script(into).kids.append(node)

    def remove_script(self, name):
        _, kids, i = self.scripts()[name]
        return kids.pop(i)

    def contents(self, script_name, content_name=None):
        """The content nodes of a script (all, or only those calling `content_name`), in file order."""
        out = [n for _, n in self.walk(self.script(script_name).kids) if n.name in CONTENT]
        return [n for n in out if content_name is None or self.content(n)[0] == content_name]

    def remove_contents(self, script_name, content_name):
        """Drop every condition / action calling `content_name` from that script; empty OR groups go too."""
        s, gone = self.script(script_name), 0

        def prune(kids):
            nonlocal gone
            keep = []
            for k in kids:
                if k.name in CONTENT and self.content(k)[0] == content_name:
                    gone += 1
                    continue
                if k.name == 'OrCondition':
                    k.kids = prune(k.kids)
                    if not k.kids:
                        continue
                keep.append(k)
            return keep
        s.kids = prune(s.kids)
        return gone

    def add_action(self, script_name, node, index=None):
        kids = self.script(script_name).kids
        kids.insert(len(kids) if index is None else index, node)

    def add_condition(self, script_name, node, group=0):
        """AND `node` into OR group `group` of the script (a new group when `group` == number of groups)."""
        s = self.script(script_name)
        ors = [k for k in s.kids if k.name == 'OrCondition']
        if group == len(ors):
            s.kids.insert(len(ors), Node('OrCondition', self.version('OrCondition'), b'', []))
            ors = [k for k in s.kids if k.name == 'OrCondition']
        ors[group].kids.append(node)

    # ------------------------------------------------------------- mission objectives
    def _objectives_node(self):
        return next(n for _, n in self.walk() if n.name == 'MissionObjectives')

    def objectives(self):
        """MissionObjectives (v3): u32 count, then per objective: name (what scripts refer to), title label,
        description label, u8 bonus, u32 flags (1 on Heidelberg's first objective only)."""
        d = self._objectives_node().head
        out, p = [], 4
        for _ in range(struct.unpack_from('<I', d, 0)[0]):
            name, p = self.string(d, p)
            title, p = self.string(d, p)
            desc, p = self.string(d, p)
            bonus, flags = struct.unpack_from('<BI', d, p)
            p += 5
            out.append(dict(name=name, title=title, desc=desc, bonus=bonus, flags=flags))
        assert p == len(d), 'MissionObjectives: trailing bytes'
        return out

    def set_objectives(self, objs):
        body = struct.pack('<I', len(objs))
        for o in objs:
            body += _pstr(o['name']) + _pstr(o['title']) + _pstr(o['desc']) + struct.pack('<BI', o['bonus'], o['flags'])
        self._objectives_node().head = body

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
                lines.append(f'{pad}{kind} {name}(' + ', '.join(repr(a[1][2] if isinstance(a[1], tuple) and a[0] != COORD3D else a[1]) for a in args) + ')'
                             + (f'  +{rest.hex()}' if rest else ''))
            elif n.name == 'OrCondition' and depth:
                lines.append(f'{pad}OR')
        return '\n'.join(lines)


def _replace_arg(d, old, new):
    """Content node bytes with string argument `old` replaced by `new`, or None when no argument matches."""
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
    return bytes(out + d[p:]) if hit else None


def _pstr(s):
    raw = s.encode('latin-1')
    return struct.pack('<H', len(raw)) + raw


def encode_arg(t, v):
    """One script argument: u32 type, then 3 x f32 (coordinate) or i32 + f32 + u16-prefixed string, the value in
    the slot its Python type picks (retail never sets more than one; selftest re-encodes every retail argument)."""
    if t == COORD3D:
        return struct.pack('<Ifff', t, *v)
    i, f, s = v if isinstance(v, tuple) else (0, 0.0, v) if isinstance(v, str) else (0, float(v), '') if isinstance(v, float) else (int(v), 0.0, '')
    return struct.pack('<Iif', t, i, f) + _pstr(s)


CATALOG_FILE = os.path.join(HERE, 'script_catalog.json')
_catalog = None


def build_catalog():
    """Every condition / action used in the retail campaign maps: name -> kind, content type, argument types."""
    arc, maps = campaign_maps()
    cat = {}
    for n in maps:
        m = MapFile(big.read_files(arc, [n])[n])
        for _, x in m.walk():
            if x.name in CONTENT:
                name, args, _ = m.content(x)
                kind = 'Condition' if x.name == 'Condition' else 'ScriptAction'
                e = cat.setdefault(name, dict(kind=kind, ctype=struct.unpack_from('<I', x.head, 0)[0],
                                              args=[t for t, _ in args], uses=0))
                assert e['args'] == [t for t, _ in args] and e['kind'] == kind, name
                e['uses'] += 1
    return dict(sorted(cat.items()))


def catalog():
    global _catalog
    if _catalog is None:
        import json
        if not os.path.exists(CATALOG_FILE):
            with open(CATALOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(build_catalog(), f, indent=0)
        with open(CATALOG_FILE, encoding='utf-8') as f:
            _catalog = json.load(f)
    return _catalog


def _encode_content(m, node):
    ctype, key, n = struct.unpack_from('<III', node.head, 0)
    return struct.pack('<III', ctype, key, n) + b''.join(encode_arg(t, v) for t, v in m.content(node)[1])


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
        # the editor's encoders reproduce every retail argument, script header and objective list
        enc = all(m.content(x)[2] == x.head[len(_encode_content(m, x)):] and x.head.startswith(_encode_content(m, x))
                  for _, x in m.walk() if x.name in CONTENT)
        objs = list(m.objectives()) if any(x.name == 'MissionObjectives' for _, x in m.walk()) else None
        if objs is not None:
            before = m._objectives_node().head
            m.set_objectives(objs)
            enc = enc and m._objectives_node().head == before
        good = same and again and enc
        print(f'{"OK " if good else "BAD"} {n.split(chr(92))[-1]:45} {scripts:4d} scripts')
        ok += good
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
