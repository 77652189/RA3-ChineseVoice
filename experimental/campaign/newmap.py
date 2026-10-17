"""Generate a map's content from scratch inside a template .map (CampNew18 uses Heidelberg's dimensions and
terrain texture set, everything else is ours): terrain, water, ground textures + blends, passability, objects,
waypoints, scripts, objectives, time of day.

Heights here are elevation / 16 (mapterrain). Heidelberg's water area says 200 but cells only stick out above
~285 on that scale -- consistent with real height = elevation * 0.04375 (= 200 at 285.7); WATERLINE uses that.
World units: a cell is 10, world (0, 0) is cell (border, border).
"""
import math
import random
import struct

import mapterrain
import mapxml
from mapscript import Node

WATERLINE = 285.7


def value_noise(seed, cells):
    """Smooth 2-D noise in [0, 1]: random values on a grid of `cells` spacing, cosine-interpolated."""
    rnd = random.Random(seed)
    grid = {}

    def at(gx, gy):
        if (gx, gy) not in grid:
            grid[(gx, gy)] = rnd.random()
        return grid[(gx, gy)]

    def f(x, y):
        gx, gy = math.floor(x / cells), math.floor(y / cells)
        fx, fy = x / cells - gx, y / cells - gy
        sx, sy = (1 - math.cos(fx * math.pi)) / 2, (1 - math.cos(fy * math.pi)) / 2
        a = at(gx, gy) + (at(gx + 1, gy) - at(gx, gy)) * sx
        b = at(gx, gy + 1) + (at(gx + 1, gy + 1) - at(gx, gy + 1)) * sx
        return a + (b - a) * sy
    return f


def island_heights(hm, seed=7, center=None, radius=1800.0):
    """Sea everywhere, one island: noisy coastline, rolling land with a few hills. Returns {(i, j): height}."""
    w, h, b = hm.width, hm.height, hm.border
    size = (w - 2 * b) * mapterrain.CELL
    cx, cy = center or (size / 2, size / 2)
    coast = value_noise(seed, 700.0)
    rough = value_noise(seed + 1, 260.0)
    hills = value_noise(seed + 2, 900.0)
    out = {}
    for j in range(h):
        for i in range(w):
            x, y = (i - b) * mapterrain.CELL, (j - b) * mapterrain.CELL
            ang = math.atan2(y - cy, x - cx)
            r = radius * (0.75 + 0.5 * coast(1000 + 600 * math.cos(ang), 1000 + 600 * math.sin(ang)))
            d = math.hypot(x - cx, y - cy) / r              # < 1 on the island
            land = max(0.0, min(1.0, (1.0 - d) / 0.12))      # 0 at sea, 1 inland, beach slope in between
            hill = max(0.0, hills(x, y) - 0.55) / 0.45       # isolated hills where the noise is high
            ht = 230.0 + land * (95.0 + 25 * rough(x, y) + 140 * hill * hill * land)
            out[(i, j)] = ht
    return out


def texture_for(height, slope, x, y, patch):
    if height < WATERLINE - 12:
        return 'Dirt_Yucatan01'                 # sea floor
    if height < WATERLINE + 10:
        return 'Sand_SantaMonica01'             # beach
    if slope > 9:
        return 'Rock_Yucatan01'
    if patch(x, y) > 0.8:
        return 'Dirt_Yucatan04'
    return 'Grass_Heidelberg02' if patch(x + 3000, y) > 0.6 else 'Grass_Heidelberg01'


# blend order: a cell takes the highest-ranked neighbouring texture above its own as its blend
RANK = ['Rock_Yucatan01', 'Grass_Heidelberg01', 'Grass_Heidelberg02', 'Dirt_Yucatan04', 'Sand_SantaMonica01',
        'Dirt_Yucatan01']


def paint_terrain(m, hm, tiles, seed=11):
    patch = value_noise(seed, 150.0)
    w, h, b = hm.width, hm.height, hm.border
    grid = {}
    for j in range(h):
        for i in range(w):
            e = hm.get(i, j)
            slope = max(abs(hm.get(min(w - 1, max(0, i + a)), min(h - 1, max(0, j + c))) - e)
                        for a, c in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            grid[(i, j)] = texture_for(e, slope, (i - b) * 10.0, (j - b) * 10.0, patch)
            # passability: steep dry ground is impassable (field 0, as on retail maps)
            tiles.set_bit(0, i, j, slope > 9 and e > WATERLINE)
    by_tex = {}
    for c, t in grid.items():
        by_tex.setdefault(t, []).append(c)
    for t, cells in by_tex.items():
        tiles.paint(cells, t)
    blended = 0
    for (i, j), own in grid.items():
        near = {}
        for d, (di, dj) in tiles.STEP.items():
            t = grid.get((i + di, j + dj))
            if t and RANK.index(t) < RANK.index(own):
                near.setdefault(t, set()).add(d)
        if not near:
            continue
        top = min(near, key=RANK.index)
        for need, (byte, flags, two) in tiles.SIDES:
            if set(need) <= near[top]:
                direction = [0, 0, 0, 0]
                direction[byte] = 1
                tiles.blend(i, j, top, direction, flags, two)
                blended += 1
                break
    return {t: len(c) for t, c in by_tex.items()}, blended


def set_water(m, x0, y0, x1, y1):
    """The (single) standing water area becomes the rectangle (x0, y0)-(x1, y1); its other settings stay."""
    node = next(n for _, n in m.walk() if n.name == 'StandingWaterAreas')
    d = node.head
    p = 8
    for _ in range(2):
        p += 2 + struct.unpack_from('<H', d, p)[0]
    p += 5
    for _ in range(2):
        p += 2 + struct.unpack_from('<H', d, p)[0]
    k = struct.unpack_from('<I', d, p)[0]
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    node.head = (d[:p] + struct.pack('<I', len(pts)) + b''.join(struct.pack('<ff', *q) for q in pts)
                 + d[p + 4 + 8 * k:])


def object_node(m, like_props, flags, template, x, y, z=0.0, angle=0.0, **props):
    """An Object node with properties copied from `like_props` ({key: (type, value)}) and overridden."""
    pr = dict(like_props)
    for k, v in props.items():
        t = pr[k][0] if k in pr else (1 if isinstance(v, int) else 3)
        pr[k] = (t, v)
    raw = template.encode('latin-1')
    head = struct.pack('<ffffI', x, y, z, angle, flags) + struct.pack('<H', len(raw)) + raw + mapxml.encode_props(m, pr)
    return Node('Object', 3, head, [])


def typed_props_of(m, node):
    ln = struct.unpack_from('<H', node.head, 20)[0]
    return mapxml._typed_props(m, node.head, 22 + ln), struct.unpack_from('<I', node.head, 16)[0]


def clear_scripts(m):
    """Empty every player's script list; returns the lists (index 2 runs our scripts, as in CampNew6)."""
    psl = next(n for _, n in m.walk() if n.name == 'PlayerScriptsList')
    for sl in psl.kids:
        sl.kids = []
    return psl.kids


COLORS = {'Dirt_Yucatan01': (40, 70, 95), 'Sand_SantaMonica01': (200, 185, 140), 'Dirt_Yucatan04': (150, 125, 85),
          'Grass_Heidelberg01': (70, 110, 50), 'Grass_Heidelberg02': (85, 120, 55), 'Rock_Yucatan01': (120, 115, 110)}


def preview_tga(hm, tiles, size, bpp):
    """Radar / preview picture of the playable area (TGA, bottom row first, as the retail map pictures):
    ground colour by texture, shaded by height; under water a flat sea colour."""
    b = hm.border
    span = hm.width - 2 * b
    names = {}
    for name, (s, cnt, _) in tiles.textures.items():
        for c in range(s, s + cnt):
            names[c] = name
    body = bytearray()
    for r in range(size):
        j = b + int(r * span / size)
        for q in range(size):
            i = b + int(q * span / size)
            e = hm.get(i, j)
            if e < WATERLINE:
                rgb = (25, 60, 90)
            else:
                base = COLORS.get(names.get(tiles.arrays[0][j * hm.width + i] // 4), (100, 100, 100))
                k = 0.8 + 0.4 * min(1.0, (e - WATERLINE) / 150)
                rgb = tuple(min(255, int(c * k)) for c in base)
            body += bytes((rgb[2], rgb[1], rgb[0])) + (b'\xff' if bpp == 32 else b'')
    head = struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, size, size, bpp, 8 if bpp == 32 else 0)
    return head + bytes(body)
