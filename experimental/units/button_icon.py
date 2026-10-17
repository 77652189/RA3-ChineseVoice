"""Production button and selection portrait for a CNV unit, in the retail style.

RA3 buttons (PackedTextureImage Button_<unit>_on, 106 x 106) and portraits (Portrait_<unit>, 101 x 76) are crops
of shared 256 x 256 atlases (Texture:PackedImages_NNN / PackedImagesPortraits_NNN) in the static stream: buttons a
blue rounded frame over a teal gradient, portraits a dark rounded plate with a cyan glow, the unit rendered from
above at three-quarter view. background() rebuilds the empty plate from the retail images themselves: per pixel the
most common colour over all of them (units sit in different places and differ in colour; frame and background are
the same on every image), the centre (a unit nearly everywhere) from a smooth fit. compose() lays a transparent
render of our unit (cnv_lighttank.py icon()) on it.

  python -I -X utf8 experimental/units/button_icon.py background button|portrait   -> work/reference/<kind>_frame.png
  python -I -X utf8 experimental/units/button_icon.py compose button|portrait <render.png> <out.tga>
"""
import io
import os
import struct
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'campaign'))
from PIL import Image                           # noqa: E402

# kind: (size, retail name prefix, suffix, inset of the inner area, fill, contrast, agreement for a clean pixel)
# (portraits: the unit fills nearly the whole plate, so a quarter of them agreeing already marks background)
KINDS = {'button': ((106, 106), b'packedtextureimage:button_', b'_on', 7, 1.18, 1.12, 0.5),
         'portrait': ((101, 76), b'packedtextureimage:portrait_allied', b'', 4, 0.9, 1.12, 0.25)}  # Allied plates only
STATIC = [('StaticStream.big', 'data\\static.')] + [(f'Core{v}.big', f'data\\static.{v}.') for v in (5, 6, 8, 9, 10, 11, 12)]


def frame_path(kind):
    return os.path.join(ROOT, 'work', 'reference', f'{kind}_frame.png')


def retail_images(kind):
    """All retail images of this kind and size from the static stream, as RGBA."""
    import mapxml
    size, prefix, suffix = KINDS[kind][:3]
    lib = mapxml.layered(STATIC)
    ids = {k[1]: i for k, i in lib.items()}
    atlases, out = {}, []
    for (t, _), inst in lib.items():
        name = inst.name.lower()
        if not (name.startswith(prefix) and name.endswith(suffix)):
            continue
        d = bytes(inst.chunks[0])
        w, h, x, y, tw, th = struct.unpack_from('<6I', d, 8)
        if (w, h) != size or not inst.refs:
            continue
        tex = ids.get(inst.refs[0][1])
        if tex is None:
            continue
        if tex.name not in atlases:
            raw = bytes(tex.chunks[0])
            atlases[tex.name] = Image.open(io.BytesIO(raw[raw.find(b'DDS '):])).convert('RGBA')
        out.append(atlases[tex.name].crop((x, y, x + w, y + h)))
    return out


def background(kind):
    import numpy as np
    (W, H), inset, agree = KINDS[kind][0], KINDS[kind][3] + 2, KINDS[kind][6]
    imgs = retail_images(kind)
    px = [im.load() for im in imgs]
    bg = Image.new('RGBA', (W, H))
    o = bg.load()
    sure = []                                       # (x, y, colour) where most images agree
    for y in range(H):
        for x in range(W):
            votes = Counter()
            full = {}
            for p in px:
                c = p[x, y]
                key = (c[0] // 12, c[1] // 12, c[2] // 12, c[3] // 64)
                votes[key] += 1
                full.setdefault(key, []).append(c)
            key, n = votes.most_common(1)[0]
            cs = full[key]
            o[x, y] = tuple(sum(c[i] for c in cs) // len(cs) for i in range(4))
            if n >= agree * len(px):
                sure.append((x, y, o[x, y]))
    # the centre is a unit on nearly every image: fill the inner area where they disagree from a smooth (cubic in
    # x, y) fit to the agreeing inner pixels -- the background is a soft gradient / glow
    inner = [(x, y, c) for x, y, c in sure if inset <= x < W - inset and inset <= y < H - inset]

    def terms(x, y):
        u, v = x / W, y / H
        return [u ** i * v ** j for i in range(4) for j in range(4 - i)]
    A = np.array([terms(x, y) for x, y, _ in inner])
    fits = [np.linalg.lstsq(A, np.array([c[ch] for _, _, c in inner], float), rcond=None)[0] for ch in range(3)]
    good = {(x, y) for x, y, _ in sure}
    for y in range(inset, H - inset):
        for x in range(inset, W - inset):
            if (x, y) not in good:
                t = np.array(terms(x, y))
                o[x, y] = tuple(int(np.clip(t @ f, 0, 255)) for f in fits) + (255,)
    bg.save(frame_path(kind))
    print(len(imgs), 'retail', kind, 'images ->', frame_path(kind))


def compose(kind, render, out):
    """Our transparent render over the rebuilt plate, inside its inner area. fill > 1 lets the unit run past the
    inner area (cropped there), as the retail tanks do (the Guardian's barrel leaves the frame); contrast deepens the
    render toward the retail look (dark tracks and seams, bright edges)."""
    from PIL import ImageEnhance
    (W, H), _, _, inset, fill, contrast, _ = KINDS[kind]
    bg = Image.open(frame_path(kind)).convert('RGBA')
    unit = Image.open(render).convert('RGBA')
    unit = unit.crop(unit.getbbox())
    alpha = unit.getchannel('A')
    unit = ImageEnhance.Contrast(unit.convert('RGB')).enhance(contrast).convert('RGBA')
    unit.putalpha(alpha)
    s = fill * min((W - 2 * inset) / unit.width, (H - 2 * inset) / unit.height * 1.25)
    unit = unit.resize((max(1, round(unit.width * s)), max(1, round(unit.height * s))), Image.LANCZOS)
    layer = Image.new('RGBA', (W, H))
    layer.paste(unit, ((W - unit.width) // 2, (H - unit.height) // 2 + 2), unit)
    inner = Image.new('L', (W, H), 0)
    inner.paste(255, (inset - 2, inset - 2, W - inset + 2, H - inset + 2))     # keep the frame on top
    layer.putalpha(Image.composite(layer.getchannel('A'), inner, inner))
    icon = Image.alpha_composite(bg, layer)
    icon.save(out)
    icon.save(os.path.splitext(out)[0] + '_preview.png')
    print(kind, out)


if __name__ == '__main__':
    if sys.argv[1] == 'background':
        background(sys.argv[2])
    else:
        compose(sys.argv[2], sys.argv[3], sys.argv[4])
