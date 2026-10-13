"""Pixelate the wall map behind Krukov in the Allied mission 1 briefing (A01MM01.vp6).

The game's world map draws China's borders wrongly (South Tibet), which Bilibili rejects, so the demo video
mosaics it: everything inside the movie picture is pixelated except Krukov (dark uniform and cap, the face under
the cap, skin next to them, filled row by row) and the Soviet flag.

  third_party/index-tts/.venv/Scripts/python -I -X utf8 tools/mask_map.py <in.vp6> <out.mp4> <end_s> [--preview t1,t2,..]

Writes the whole movie from 0 to end_s (so make_demo's trim times stay valid), video only.
"""
import os
import subprocess
import sys

import numpy as np
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FF = os.path.join(ROOT, 'third_party', 'ffmpeg', 'ffmpeg.exe')
W, H = 1280, 720
BLOCK = 32


def krukov(y, box, avoid=None):
    """Mask of the man: the uniform as the main dark blob (plus split-off pieces and the cap) and a face box."""
    x0, y0, x1, y1 = box
    dark = np.zeros_like(y, bool)
    dark[y0:y1, x0:x1] = y[y0:y1, x0:x1] < 28
    dark = ndimage.binary_opening(dark, iterations=2)
    # drop the map's thin dark frame line: it touches the cap and would pass for its crown
    dark = ndimage.binary_opening(dark, structure=np.ones((11, 1), bool))
    dark = ndimage.binary_opening(dark, structure=np.ones((1, 11), bool))
    lab, n = ndimage.label(dark)
    if not n:
        return np.zeros_like(dark)
    sizes = ndimage.sum(dark, lab, range(1, n + 1))
    # the dark wall beside the flag can outgrow the uniform: rank pieces by their area outside the flag zone,
    # and skip pieces that run up to the top of the picture (the wall; the man's cap never reaches it)
    rank = sizes if avoid is None else ndimage.sum(dark & ~avoid, lab, range(1, n + 1))
    tops = ndimage.minimum(np.indices(dark.shape)[0], lab, range(1, n + 1))
    rank = np.where(np.asarray(tops) > y0 + 5, rank, 0)
    blob = lab == (1 + int(np.argmax(rank)))
    # the red piping splits the uniform in two when he turns: add big dark pieces right next to the main one
    near = ndimage.binary_dilation(blob, iterations=20)
    extra = [i + 1 for i, sz in enumerate(sizes) if sz > 2000 and tops[i] > y0 + 5 and near[lab == i + 1].any()]
    blob = np.isin(lab, extra) | blob
    # the flag's dark folds can join the blob: leave them out when locating the cap
    geo = blob if avoid is None else blob & ~avoid
    # the cap can come apart from the uniform at the gold brim band: take a big dark piece sitting right above
    ys, xs = np.where(geo)
    top = ys.min()
    tx = xs[ys < top + 30]
    for i, sz in enumerate(sizes):
        if sz < 3000:
            continue
        py, px = np.where(lab == i + 1)
        if py.min() < top and py.max() > top - 200 and tx.min() - 60 < px.mean() < tx.max() + 60:
            blob |= lab == i + 1
            geo |= lab == i + 1
    # the blob itself (uniform, cap, moustache); the face and hands come from skin pixels in process(),
    # plus a face box under the cap: the shadowed half of the face is neither dark nor clearly skin
    out = ndimage.binary_dilation(blob, iterations=2)
    ys, xs = np.where(geo)
    top = ys.min()
    # cap centre from the crown, width as the median over the brim rows (the map's dark frame line can touch
    # the cap and make a single row span the whole wall)
    cy, cx = np.where(geo[top:top + 15])
    widths = [int(geo[r].sum()) for r in range(top + 15, top + 60)]
    if len(cx):
        c, w = int(cx.mean()), int(np.median(widths))
        hx0, hx1 = c - w // 2, c + w // 2
        fx0, fx1 = int(hx0), int(hx1)
        fy0, fy1 = int(top + 40), int(top + 40 + 1.35 * w)
        out[max(fy0, 0):min(fy1, out.shape[0]), max(fx0, 0):fx1] = True
    return out


def pixelate(rgb):
    h, w = rgb.shape[:2]
    small = rgb[:h - h % BLOCK, :w - w % BLOCK].reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK, 3).mean((1, 3))
    big = np.repeat(np.repeat(small, BLOCK, 0), BLOCK, 1).astype(np.uint8)
    out = rgb.copy()
    out[:big.shape[0], :big.shape[1]] = big
    return out


def picture_box(rgb):
    """The movie picture inside the HUD frame (bright area), found once from the mean frame."""
    lum = rgb.mean(2)
    rows = np.where((lum > 40).mean(1) > 0.5)[0]
    cols = np.where((lum > 40).mean(0) > 0.5)[0]
    if len(rows) < 100 or len(cols) < 100:
        return None          # black frames of the fade-in
    return int(cols.min()) + 4, int(rows.min()) + 4, int(cols.max()) - 4, int(rows.max()) - 4


def skin(rgb):
    f = rgb.astype(np.int16)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    return (r > 70) & (r > g + 8) & (g > b) & (r - b > 25) & (r - b < 120)


def flag(rgb):
    f = rgb.astype(np.int16)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    m = (r > 90) & (r > 2 * g) & (r > 2 * b)
    m = ndimage.binary_closing(m, iterations=6)
    m = ndimage.binary_fill_holes(m)
    lab, n = ndimage.label(m)
    if not n:
        return m
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    return ndimage.binary_dilation(np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s > 8000]), iterations=4)


def process(rgb, box):
    """Everything in the picture except Krukov and the Soviet flag gets the mosaic: the map is the wall."""
    y = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    fl = flag(rgb)
    man = krukov(y, box, ndimage.binary_dilation(fl, iterations=25))
    # widen around the head with skin pixels touching the man (cheeks, ears, hands)
    # only a thin band: the map's tan and orange countries are skin-coloured too and would leak in
    man = man | (skin(rgb) & ndimage.binary_dilation(man, iterations=12))
    # below the crown the body is convex row by row: fill each row between its outermost man pixels, which
    # catches the lit collar, chin and medals that are neither dark nor skin
    rows = np.where(man.any(1))[0]
    for r in rows[rows >= rows.min() + 40]:
        xs = np.where(man[r])[0]
        man[r, xs.min():xs.max() + 1] = True
    # close the uniform along the bottom edge so the medals and clasped hands count as enclosed
    x0, y0, x1, y1 = box
    xs = np.where(man[y1 - 6:y1].any(0))[0]
    if len(xs):
        man[y1 - 2:y1, xs.min():xs.max() + 1] = True
    man = ndimage.binary_fill_holes(ndimage.binary_closing(man, iterations=6))
    man = ndimage.binary_dilation(man, iterations=3)
    x0, y0, x1, y1 = box
    m = np.zeros(y.shape, bool)
    m[y0:y1, x0:x1] = True
    m &= ~man & ~fl
    p = pixelate(rgb)
    out = rgb.copy()
    out[m] = p[m]
    return out


def frames(src, end, at=None):
    vf = 'scale=1280:720' if at is None else f"select='{'+'.join(f'between(t,{t},{t + 0.04})' for t in at)}',scale=1280:720"
    proc = subprocess.Popen([FF, '-v', 'error', '-i', src, '-t', str(end), '-vf', vf, '-fps_mode', 'passthrough',
                             '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
    while True:
        buf = proc.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W, 3)


def main():
    src, out, end = sys.argv[1], sys.argv[2], float(sys.argv[3])
    if '--preview' in sys.argv:
        from PIL import Image
        at = [float(t) for t in sys.argv[sys.argv.index('--preview') + 1].split(',')]
        tiles = []
        for f in frames(src, end, at):
            box = picture_box(f)
            tiles.append(np.concatenate([f, process(f, box)], 1))
        Image.fromarray(np.concatenate(tiles, 0)).resize((1280, 360 * len(tiles))).save(out)
        print('preview ->', out)
        return
    enc = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                            '-r', '24000/1001', '-i', '-', '-c:v', 'libx264', '-crf', '12', '-preset', 'medium',
                            '-pix_fmt', 'yuv420p', out], stdin=subprocess.PIPE)
    # one picture box for the whole clip: the union over sampled frames (fade-ins make single frames too small)
    boxes = [b for b in (picture_box(f) for f in frames(src, end, [t + 0.5 for t in range(int(end))])) if b]
    box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    print('picture box', box)
    n = 0
    for f in frames(src, end):
        enc.stdin.write(process(f, box).tobytes())
        n += 1
    enc.stdin.close()
    enc.wait()
    print(f'{n} frames -> {out}')


if __name__ == '__main__':
    main()
