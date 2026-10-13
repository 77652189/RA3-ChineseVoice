"""Read / write EA .csf string tables (label -> text). Text is UTF-16LE with every byte inverted."""
import struct
from . import refpack


def parse_full(data):
    """-> (header fields, [(label, text, extra-or-None)]) keeping order and any WRTS extra value."""
    if refpack.is_refpack(data):
        data = refpack.decompress(data)
    assert data[:4] == b' FSC', 'not a CSF file'
    version, n_labels, n_strings, unused, lang = struct.unpack_from('<IIIII', data, 4)
    p = 24
    entries = []
    for _ in range(n_labels):
        tag, n_str, ln = struct.unpack_from('<4sII', data, p); p += 12
        assert tag == b' LBL', f'bad label tag at {p}'
        name = data[p:p + ln].decode('latin-1'); p += ln
        text, extra = '', None
        for i in range(n_str):
            stag, sl = struct.unpack_from('<4sI', data, p); p += 8
            raw = bytes(b ^ 0xFF for b in data[p:p + sl * 2]); p += sl * 2
            ex = None
            if stag == b'WRTS':  # extra ASCII value attached to the string
                el, = struct.unpack_from('<I', data, p); p += 4
                ex = data[p:p + el]; p += el
            if i == 0:
                text, extra = raw.decode('utf-16le', 'replace'), ex
        entries.append((name, text, extra, n_str))
    return dict(version=version, unused=unused, lang=lang), entries


def parse(data):
    return {name: text for name, text, _, _ in parse_full(data)[1]}


def write(header, entries):
    """Inverse of parse_full (labels with no string are written with no string)."""
    body = bytearray()
    n_strings = 0
    for name, text, extra, n_str in entries:
        nb = name.encode('latin-1')
        body += struct.pack('<4sII', b' LBL', 1 if n_str else 0, len(nb)) + nb
        if n_str:
            t = text.encode('utf-16le')
            body += struct.pack('<4sI', b'WRTS' if extra is not None else b' RTS', len(t) // 2)
            body += bytes(b ^ 0xFF for b in t)
            if extra is not None:
                body += struct.pack('<I', len(extra)) + extra
            n_strings += 1
    head = b' FSC' + struct.pack('<IIIII', header['version'], len(entries), n_strings, header['unused'], header['lang'])
    return head + bytes(body)
