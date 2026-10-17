"""Terrain height of a .map (HeightMapData, via mapscript).

HeightMapData v6 (Heidelberg: 627316 bytes): u32 width, height, border width (cells), u32 border count, borders
of 4 x u32, u32 cell count (= width * height), then u16 elevation per cell, row by row. A cell is 10 world units,
world (0, 0) is cell (border, border); height in world units = elevation / 16 (Heidelberg 114..629, water at 200,
GlobalWaterSettings and the StandingWaterAreas entry). But on the bench (make_campnew14, CNV_BANDS=1) only cells
above ~285 by that scale stick out of Heidelberg's river, so either the scale or the water height means something
else; treat 285 as the measured waterline there.
"""
import math
import struct

CELL = 10.0
MAGIC = b'\xff\xff\xff\xff\x00\x00\xda\x7a'      # the end of every blend description
SCALE = 16.0


class HeightMap:
    def __init__(self, m):
        self.node = next(n for _, n in m.walk() if n.name == 'HeightMapData')
        d = self.node.head
        self.width, self.height, self.border, nb = struct.unpack_from('<4I', d, 0)
        self.at = 20 + 16 * nb
        assert struct.unpack_from('<I', d, self.at - 4)[0] == self.width * self.height
        self.head = d[:self.at]
        self.elev = list(struct.unpack_from(f'<{self.width * self.height}H', d, self.at))

    def cell(self, x, y):
        return int(round(x / CELL)) + self.border, int(round(y / CELL)) + self.border

    def get(self, i, j):
        return self.elev[j * self.width + i] / SCALE

    def set(self, i, j, h):
        self.elev[j * self.width + i] = max(0, min(65535, int(round(h * SCALE))))

    def raise_hill(self, x, y, top, radius):
        """A smooth round hill at world (x, y): cells within `radius` world units rise towards height `top`
        (cosine falloff); terrain already higher stays. Returns the cells changed."""
        ci, cj = self.cell(x, y)
        r = int(math.ceil(radius / CELL))
        changed = 0
        for j in range(cj - r, cj + r + 1):
            for i in range(ci - r, ci + r + 1):
                if not (0 <= i < self.width and 0 <= j < self.height):
                    continue
                dist = math.hypot(i - ci, j - cj) * CELL
                if dist > radius:
                    continue
                base = self.get(i, j)
                h = base + (top - base) * 0.5 * (1 + math.cos(math.pi * dist / radius))
                if h > base:
                    self.set(i, j, h)
                    changed += 1
        return changed

    def store(self):
        self.node.head = self.head + struct.pack(f'<{len(self.elev)}H', *self.elev)


class Tiles:
    """Ground textures (BlendTileData v27, Heidelberg 3.4 MB): u32 N (= width * height), then four u16 arrays of N
    (tile, blend, three-way blend, cliff texture), more per-cell data, then u32 texture cells, u32 blended tiles,
    u32 cliff infos, u32 texture count and textures (u32 cell start, cell count, cell size, magic, name). A
    texture tiles in size x size cells of 2 x 2 tiles; tile value = 4 * cell + quadrant, cell = start +
    (x // 2) % size + ((y // 2) % size) * size, quadrant = x % 2 + 2 * (y % 2) (reads 0 1 4 5 8 9 12 13 ...
    along the first row)."""

    def __init__(self, m, width):
        self.node = next(n for _, n in m.walk() if n.name == 'BlendTileData')
        d = self.node.head
        self.n = struct.unpack_from('<I', d, 0)[0]
        self.width = width
        self.arrays = [list(struct.unpack_from(f'<{self.n}H', d, 4 + 2 * self.n * k)) for k in range(4)]
        self.rest_at = 4 + 8 * self.n
        self.tex_at, self.textures, tex_end = self._textures(d, self.rest_at)
        # between the u16 arrays and the counts: 8 bit fields of ceil(width / 8) bytes per row, then one byte per
        # cell (length height * (width + width rounded up to 8) on all 27 campaign maps). Field 0 is set on steep
        # dry cells (impassability), field 4 on ~94 % of Heidelberg, field 5 on ~2 %; the byte array is all zero.
        self.extra = bytearray(d[self.rest_at:self.tex_at - 16])
        self.height = self.n // width
        self.row_bytes = (width + 7) // 8
        assert len(self.extra) == self.height * (width + 8 * self.row_bytes), 'per-cell data layout'
        # counts before the texture list: texture cells, blends (descriptions + 1), cliff infos, textures
        self.counts = list(struct.unpack_from('<4I', d, self.tex_at - 16))
        # after it 8 bytes, then the blend descriptions: u32 secondary tile, 4 direction bytes, u8 flags,
        # u8 two-sided, u32 (0xFFFFFFFF nearly always), u32 0x7ADA0000; a cell's blend value is 1 + description index
        self.desc_at = tex_end + 8
        self.descs = [d[self.desc_at + 18 * k:self.desc_at + 18 * (k + 1)] for k in range(self.counts[1] - 1)]
        assert all(x[14:] == MAGIC[4:] for x in self.descs), 'blend description layout'     # Havana: 2 with another u32 before it
        self.after_descs = self.desc_at + 18 * len(self.descs)
        self._known = {x: k + 1 for k, x in enumerate(self.descs)}

    @staticmethod
    def _textures(d, start_at):
        """(offset of the first texture entry, {name: (cell start, cell count, cell size)}, end of the list).
        Found by scanning after the per-cell arrays for counts (cells, blends, cliffs, textures) followed by
        entries that start at cell 0, follow on from each other and add up to the cell count."""
        for x in range(start_at, len(d) - 40):        # bit arrays before it: not 4-aligned
            cells, _, _, count = struct.unpack_from('<4I', d, x)
            if not 0 < count < 256 or not 0 < cells < 65536 or struct.unpack_from('<I', d, x + 16)[0] != 0:
                continue
            out, q, nxt = {}, x + 16, 0
            try:
                for _ in range(count):
                    start, n, size, _ = struct.unpack_from('<4I', d, q)
                    ln = struct.unpack_from('<H', d, q + 16)[0]
                    name = d[q + 18:q + 18 + ln]
                    if start != nxt or not 0 < size <= 16 or not 0 < ln < 80 or not name.isascii():
                        raise ValueError
                    out[name.decode('ascii')] = (start, n, size)
                    nxt, q = start + n, q + 18 + ln
            except (ValueError, struct.error):
                continue
            if nxt == cells:
                return x + 16, out, q
        raise ValueError('BlendTileData: texture list not found')

    def tile_of(self, texture, i, j):
        start, _, size = self.textures[texture]
        return 4 * (start + (i // 2) % size + ((j // 2) % size) * size) + i % 2 + 2 * (j % 2)

    def blend(self, i, j, texture, direction, flags=0, two_sided=0):
        """Blend `texture` over cell (i, j) (whose own tile stays) with a description of that direction
        (4 bytes) and flags; returns the blend value set."""
        x = (struct.pack('<I', self.tile_of(texture, i, j)) + bytes(direction) + bytes([flags, two_sided])
             + MAGIC)
        if x not in self._known:
            self.descs.append(x)
            self._known[x] = len(self.descs)
        self.arrays[1][j * self.width + i] = self._known[x]
        return self._known[x]

    def paint(self, cells, texture):
        tile, blend, three, _ = self.arrays
        for i, j in cells:
            k = j * self.width + i
            tile[k] = self.tile_of(texture, i, j)
            blend[k] = three[k] = 0
        return len(cells)

    def set_bit(self, field, i, j, on):
        k = field * self.row_bytes * self.height + j * self.row_bytes + i // 8
        if on:
            self.extra[k] |= 1 << (i % 8)
        else:
            self.extra[k] &= ~(1 << (i % 8)) & 0xFF

    def fill_field(self, field, on):
        size = self.row_bytes * self.height
        self.extra[field * size:(field + 1) * size] = bytes([0xFF if on else 0]) * size

    def texture_at(self, i, j):
        c = self.arrays[0][j * self.width + i] // 4
        return next((n for n, (s, cnt, _) in self.textures.items() if s <= c < s + cnt), None)

    # blend direction (byte set, flags, two-sided) by where the blended-in texture lies, j growing = north;
    # inferred from retail maps (for each blended cell, which neighbour has the secondary texture): byte 0 =
    # east (flag 1: west), byte 1 = north (south), byte 2 = north-east corner (south-east), byte 3 = north-west
    # (south-west); two-sided byte 2 / 3 = the inner corner of both sides (N+E, S+E, N+W, S+W)
    SIDES = [(('N', 'E'), (2, 0, 1)), (('S', 'E'), (2, 1, 1)), (('N', 'W'), (3, 0, 1)), (('S', 'W'), (3, 1, 1)),
             (('E',), (0, 0, 0)), (('W',), (0, 1, 0)), (('N',), (1, 0, 0)), (('S',), (1, 1, 0)),
             (('NE',), (2, 0, 0)), (('SE',), (2, 1, 0)), (('NW',), (3, 0, 0)), (('SW',), (3, 1, 0))]
    STEP = {'E': (1, 0), 'W': (-1, 0), 'N': (0, 1), 'S': (0, -1),
            'NE': (1, 1), 'SE': (1, -1), 'NW': (-1, 1), 'SW': (-1, -1)}

    def autoblend(self, texture, cells):
        """Soften the edge of `texture` around the given cells: each of them that is not `texture` but touches
        it gets `texture` blended in from that side, the way retail maps do. Returns the cells blended."""
        done = 0
        for i, j in cells:
            if self.texture_at(i, j) == texture:
                continue
            near = {d for d, (di, dj) in self.STEP.items() if self.texture_at(i + di, j + dj) == texture}
            for need, (byte, flags, two) in self.SIDES:
                if set(need) <= near:
                    direction = [0, 0, 0, 0]
                    direction[byte] = 1
                    self.blend(i, j, texture, direction, flags, two)
                    done += 1
                    break
        return done

    def store(self):
        d = self.node.head
        self.counts[1] = len(self.descs) + 1
        self.node.head = (d[:4] + b''.join(struct.pack(f'<{self.n}H', *a) for a in self.arrays)
                          + bytes(self.extra) + struct.pack('<4I', *self.counts)
                          + d[self.tex_at:self.desc_at] + b''.join(self.descs) + d[self.after_descs:])
