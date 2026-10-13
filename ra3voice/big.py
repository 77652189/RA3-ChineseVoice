"""Read / write EA BIG archives (BIG4 / BIGF)."""
import struct


def read_index(path):
    """Return list of (name, offset, size)."""
    with open(path, 'rb') as f:
        f.read(4)
        f.read(4)
        count, _ = struct.unpack('>II', f.read(8))
        entries = []
        for _ in range(count):
            off, size = struct.unpack('>II', f.read(8))
            name = bytearray()
            while (c := f.read(1)) != b'\0':
                name += c
            entries.append((name.decode('latin-1'), off, size))
    return entries


def read_files(path, names):
    """Read the named entries (case-insensitive). Returns {name_as_requested: bytes}."""
    want = {n.lower(): n for n in names}
    out = {}
    with open(path, 'rb') as f:
        for n, off, size in read_index(path):
            key = n.lower()
            if key in want:
                f.seek(off)
                out[want[key]] = f.read(size)
    return out


def write(path, files):
    """files: list of (name, bytes). Names use backslashes like the game's archives.
    Entries are written in EA's order: lower-case, with the path separator sorting before every
    other character (so data\\audio\\cdata\\* comes before data\\audio.bin, as in EnglishAudio.big)."""
    files = sorted(files, key=lambda f: f[0].lower().replace('\\', '\x01'))
    enc = [(n.encode('latin-1'), d) for n, d in files]
    index_size = sum(8 + len(n) + 1 for n, _ in enc)
    header_size = 16 + index_size + 8  # trailing 8-byte pad like EA tools write
    offsets, pos = [], header_size
    for _, d in enc:
        offsets.append(pos)
        pos += len(d)
    with open(path, 'wb') as f:
        f.write(b'BIG4')
        f.write(struct.pack('<I', pos))
        f.write(struct.pack('>II', len(enc), header_size))
        for (n, d), off in zip(enc, offsets):
            f.write(struct.pack('>II', off, len(d)))
            f.write(n + b'\0')
        f.write(b'L280\x15\x05\x00\x01')  # same trailer as the game's archives
        for _, d in enc:
            f.write(d)
