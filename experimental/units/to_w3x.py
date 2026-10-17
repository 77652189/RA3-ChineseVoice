"""Turn a Blender unit export (cnv_lighttank.py: parts.json + baked PNGs) into W3X model, textures and a still
animation under the SDK's Art folder, rigged with the bone names a retail logic XML expects.

  convert(src_dir, model, pivots, part_bones, spec=110)

pivots: [(name, parent pivot name or None for ROOTTRANSFORM, (x, y, z) relative to the parent)]
part_bones: {part name in parts.json: pivot name}. Textures: <model>.tga (diffuse), <model>_NRM.tga (flat),
<model>_SPM.tga (R specular, G glow 0, B team colour mask from <model>_mask.png). Writes <model>_IDLE.w3x, a
one-frame animation of this hierarchy, so no retail animation (other hierarchy) is ever played on it.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'campaign'))
import w3x                                      # noqa: E402
from PIL import Image                           # noqa: E402


def convert(src, model, pivots, part_bones, src_name='CNTankL', spec=0.45, scale=1.0):
    """spec: specular (SPM red) as a fraction of the diffuse luminance -- retail Allied SPM red averages ~21;
    a flat 110 made the whole tank mirror the warm environment map (tan / pink in game, CampNew23 first run).
    scale: uniform size factor for vertices and pivots (the first in-game run read ~0.6 of a Guardian)."""
    with open(os.path.join(src, 'parts.json'), encoding='utf-8') as f:
        parts = json.load(f)
    index = {name: k + 1 for k, (name, _, _) in enumerate(pivots)}          # ROOTTRANSFORM is 0
    piv = [(name, 0 if parent is None else index[parent], tuple(c * scale for c in at)) for name, parent, at in pivots]
    geo = []
    for part, bone in part_bones.items():
        p = parts[part]
        verts = [tuple(c * scale for c in v) for v in p['vertices']]
        geo.append((part, index[bone], (verts, p['normals'], p['uvs'], p['triangles'])))
    diffuse = Image.open(os.path.join(src, src_name + '.png')).convert('RGBA')
    mask = Image.open(os.path.join(src, src_name + '_mask.png')).convert('L').resize(diffuse.size)
    w, h = diffuse.size
    dp, mp = diffuse.load(), mask.load()
    debug = os.environ.get('CNV_UV_DEBUG') == '1'     # unbaked background (pure black) shown magenta in game

    def diffuse_px(x, y):
        r, g, b, _ = dp[x, y]
        return (255, 0, 255, 255) if debug and r == g == b == 0 else (r, g, b, 255)
    w3x.write_texture(model, w, h, diffuse_px)
    def spm(x, y):
        r, g, b, _ = dp[x, y]
        return int(spec * (0.3 * r + 0.59 * g + 0.11 * b)), 0, 255 if mp[x, y] > 127 else 0, 255
    w3x.write_texture(model + '_SPM', w, h, spm)
    w3x.write_texture(model + '_NRM', 16, 16, lambda x, y: (128, 128, 255, 255))
    w3x.write_model(model, w3x.rig_model(model, piv, geo, (model, model + '_NRM', model + '_SPM')))
    w3x.write_model(model + '_IDLE', w3x.spin_animation(model + '_IDLE', model, 1, frames=1, turns=0.0))
    return sum(len(g[2][3]) for g in geo)
