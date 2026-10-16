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
        self.textures = self._textures(d)

    @staticmethod
    def _textures(d):
        import re
        first = re.search(rb'\x12\x00Grass_|[\x04-\x40]\x00[A-Z][a-z]+_[A-Za-z]', d[4:])     # the first name
        p = 4 + first.start() - 16
        while True:         # walk back to the texture count: entries are 16 bytes + u16-prefixed name
            count = struct.unpack_from('<I', d, p - 4)[0]
            if 0 < count < 256:
                break
            p -= 4
        out, q = {}, p
        for _ in range(count):
            start, cells, size, _ = struct.unpack_from('<4I', d, q)
            ln = struct.unpack_from('<H', d, q + 16)[0]
            out[d[q + 18:q + 18 + ln].decode('latin-1')] = (start, cells, size)
            q += 18 + ln
        return out

    def paint(self, cells, texture):
        start, _, size = self.textures[texture]
        tile, blend, three, _ = self.arrays
        for i, j in cells:
            c = start + (i // 2) % size + ((j // 2) % size) * size
            k = j * self.width + i
            tile[k] = 4 * c + i % 2 + 2 * (j % 2)
            blend[k] = three[k] = 0
        return len(cells)

    def store(self):
        d = self.node.head
        self.node.head = (d[:4] + b''.join(struct.pack(f'<{self.n}H', *a) for a in self.arrays) + d[self.rest_at:])
