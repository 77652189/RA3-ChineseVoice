"""Terrain height of a .map (HeightMapData, via mapscript).

HeightMapData v6 (Heidelberg: 627316 bytes): u32 width, height, border width (cells), u32 border count, borders
of 4 x u32, u32 cell count (= width * height), then u16 elevation per cell, row by row. A cell is 10 world units,
world (0, 0) is cell (border, border); height in world units = elevation / 16 (Heidelberg 114..629, water at 200,
GlobalWaterSettings).
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
