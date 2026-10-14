"""pe_info.py <file>: print a PE file's exports, and its imports from d3d9.dll / any dll containing 'd3d'."""
import struct, sys

d = open(sys.argv[1], 'rb').read()
pe = struct.unpack_from('<I', d, 0x3c)[0]
nsec = struct.unpack_from('<H', d, pe + 6)[0]
optsz = struct.unpack_from('<H', d, pe + 20)[0]
opt = pe + 24
magic = struct.unpack_from('<H', d, opt)[0]
dd = opt + (96 if magic == 0x10b else 112)
secs = [struct.unpack_from('<8sIIII', d, opt + optsz + i * 40) for i in range(nsec)]


def off(rva):
    for name, vsize, va, rsize, raw in secs:
        if va <= rva < va + max(vsize, rsize):
            return rva - va + raw
    return None


def cstr(rva):
    o = off(rva)
    return d[o:d.index(b'\0', o)].decode('latin-1') if o is not None else '?'


exp_rva = struct.unpack_from('<I', d, dd)[0]
if exp_rva and off(exp_rva) is not None:
    o = off(exp_rva)
    n_names, names_rva = struct.unpack_from('<I', d, o + 24)[0], struct.unpack_from('<I', d, o + 32)[0]
    print('exports:', [cstr(struct.unpack_from('<I', d, off(names_rva) + 4 * i)[0]) for i in range(n_names)])
imp_rva = struct.unpack_from('<I', d, dd + 8)[0]
o = off(imp_rva) if imp_rva else None
while o is not None:
    oft, _, _, name_rva, ft = struct.unpack_from('<5I', d, o)
    if not name_rva:
        break
    dll = cstr(name_rva)
    if 'd3d' in dll.lower() or len(sys.argv) > 2:
        t = off(oft or ft)
        funcs = []
        while t is not None:
            v = struct.unpack_from('<I' if magic == 0x10b else '<Q', d, t)[0]
            if not v:
                break
            funcs.append(('#%d' % (v & 0xffff)) if v >> (31 if magic == 0x10b else 63) else cstr((v & 0x7fffffff) + 2))
            t += 4 if magic == 0x10b else 8
        print('imports', dll, funcs)
    o += 20
