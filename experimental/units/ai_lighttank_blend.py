"""Clean an AI-generated tank shape (ai_lighttank.py -> .obj) into a game unit, in Blender (headless, CPU only):

  blender.exe -b --factory-startup -P experimental/units/ai_lighttank_blend.py -- <mesh.obj> <out dir> [key=value ...]

Steps: align (ground-plane PCA puts the long axis on X, the end with the barrel forward, unless yaw= is given),
scale to the parametric tank's width (WIDTH game units, treads included), drop to the ground, decimate to the
retail budget (TRIS), split the turret off by height (turret= fraction of the height, inside the hull's middle in
y), cap both cut openings so a rotating turret never shows the inside, sharpen by angle, then material rules
(dark: low outer faces = tracks; team: turret side band) and cnv_lighttank.py's bake, previews and parts.json, so
both tanks share one look and one exporter. Pivots (turret ring, barrel pitch, muzzle) land in parts.json
'_pivots' for make_campnew24.py.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
args = sys.argv[sys.argv.index('--') + 1:]
SRC, OUT_DIR = args[0], args[1]
OPT = dict(a.split('=', 1) for a in args[2:])
sys.argv = [sys.argv[0], '--', OUT_DIR]            # cnv_lighttank reads its OUT from here
import cnv_lighttank as base                       # noqa: E402

WIDTH = float(OPT.get('width', 23.0))
TRIS = int(OPT.get('tris', 3600))
TURRET = float(OPT.get('turret', 0.62))            # cut height as a fraction of the hull-and-turret height
SHARP = math.radians(float(OPT.get('sharp', 32)))


def load():
    bpy.ops.wm.obj_import(filepath=SRC)             # OBJ is Y-up; the importer turns it Z-up
    ob = bpy.context.selected_objects[0]
    bpy.context.view_layer.objects.active = ob
    me = ob.data
    me.transform(ob.matrix_world)                    # the importer's axis turn sits in the object matrix
    ob.matrix_world = Matrix.Identity(4)
    pts = [v.co.copy() for v in me.vertices]
    # ground-plane PCA: long axis -> X
    cx = sum(p.x for p in pts) / len(pts)
    cy = sum(p.y for p in pts) / len(pts)
    sxx = sum((p.x - cx) ** 2 for p in pts)
    syy = sum((p.y - cy) ** 2 for p in pts)
    sxy = sum((p.x - cx) * (p.y - cy) for p in pts)
    yaw = math.radians(float(OPT['yaw'])) if 'yaw' in OPT else -0.5 * math.atan2(2 * sxy, sxx - syy)
    me.transform(Matrix.Translation((-cx, -cy, 0)))
    me.transform(Matrix.Rotation(yaw, 4, 'Z'))
    lo = Vector([min(v.co[i] for v in me.vertices) for i in range(3)])
    hi = Vector([max(v.co[i] for v in me.vertices) for i in range(3)])
    if 'yaw' not in OPT:
        # the barrel sticks out at turret height: whichever x end has more upper vertices is the front
        top = lo.z + 0.6 * (hi.z - lo.z)
        upper = [v.co.x for v in me.vertices if v.co.z > top]
        mid = 0.5 * (lo.x + hi.x)
        if upper and max(upper) - mid < mid - min(upper):
            me.transform(Matrix.Rotation(math.pi, 4, 'Z'))
    lo = Vector([min(v.co[i] for v in me.vertices) for i in range(3)])
    hi = Vector([max(v.co[i] for v in me.vertices) for i in range(3)])
    s = WIDTH / (hi.y - lo.y)
    me.transform(Matrix.Translation((-0.5 * (lo.x + hi.x), -0.5 * (lo.y + hi.y), -lo.z)))
    me.transform(Matrix.Scale(s, 4))
    print('CNV AI align: yaw', round(math.degrees(yaw), 1), 'scale', round(s, 2), 'size',
          tuple(round((b - a) * s, 1) for a, b in zip(lo, hi)), flush=True)
    return ob


def decimate(ob):
    faces = len(ob.data.polygons)
    if faces > TRIS:
        mod = ob.modifiers.new('dec', 'DECIMATE')
        mod.ratio = TRIS / faces
        bpy.ops.object.modifier_apply(modifier=mod.name)
    print('CNV AI decimate:', faces, '->', len(ob.data.polygons), flush=True)


def split(ob, mats):
    me = ob.data
    zs = [v.co.z for v in me.vertices]
    ys = [abs(v.co.y) for v in me.vertices]
    h = max(zs)
    cut = TURRET * h
    half = 0.5 * WIDTH
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, cut),
                           plane_no=(0, 0, 1))
    up = [f.calc_center_median().z > cut and abs(f.calc_center_median().y) < 0.8 * half for f in bm.faces]
    turret = bm.copy()                              # same face order as bm
    bmesh.ops.delete(turret, geom=[f for f, u in zip(turret.faces, up) if not u], context='FACES')
    bmesh.ops.delete(bm, geom=[f for f, u in zip(bm.faces, up) if u], context='FACES')
    parts = {}
    for name, b in (('HULL', bm), ('TURRET', turret)):
        bmesh.ops.remove_doubles(b, verts=b.verts[:], dist=1e-4)
        edges = [e for e in b.edges if e.is_boundary]
        if edges:
            bmesh.ops.holes_fill(b, edges=edges, sides=0)
        bmesh.ops.triangulate(b, faces=b.faces[:])
        bmesh.ops.recalc_face_normals(b, faces=b.faces[:])
        parts[name] = base.obj_from_bm(name, b, mats)
    bpy.data.objects.remove(ob)
    # turret ring at the turret's footprint centre on the cut plane; mesh data relative to it
    tv = [v.co for v in parts['TURRET'].data.vertices]
    ring = Vector((0.5 * (min(v.x for v in tv) + max(v.x for v in tv)), 0.0, cut))
    # muzzle: the most forward turret vertex; pitch pivot where the barrel leaves the turret body
    tip = max(tv, key=lambda v: v.x)
    body = sorted(v.x for v in tv)[int(0.8 * len(tv))]            # 80th percentile x: front of the turret body
    parts['TURRET'].data.transform(Matrix.Translation(-ring))
    parts['TURRET'].location = ring
    base.TURRET_AT = ring
    base.PITCH_AT = Vector((body - ring.x, 0.0, tip.z - ring.z))
    base.MUZZLE_AT = Vector((tip.x - body, 0.0, 0.0))
    print('CNV AI split: cut z', round(cut, 2), 'ring', tuple(round(c, 2) for c in ring), 'tip',
          tuple(round(c, 2) for c in tip), {k: len(v.data.polygons) for k, v in parts.items()}, flush=True)
    return parts, h


def paint(parts, h):
    """Material slots: 0 steel, 1 dark (tracks: low faces on the outer sides), 2 team (turret side band)."""
    half = 0.5 * WIDTH
    for name, ob in parts.items():
        off = ob.location
        for p in ob.data.polygons:
            c = p.center + off
            n = p.normal
            if name == 'HULL' and c.z < 0.33 * h and abs(c.y) > 0.62 * half:
                p.material_index = 1
            elif name == 'TURRET' and abs(n.y) > 0.6 and 0.25 < (c.z - off.z) / max(1e-3, h - off.z) < 0.55:
                p.material_index = 2
            else:
                p.material_index = 0


def sharpen(parts):
    for ob in parts.values():
        ob.data.set_sharp_from_angle(angle=SHARP)
        for p in ob.data.polygons:
            p.use_smooth = True


def main():
    sc = base.reset()
    mats = [base.material('steel', base.STEEL), base.material('dark', base.DARK),
            base.material('team', base.STEEL, team=1.0)]
    ob = load()
    decimate(ob)
    parts, h = split(ob, mats)
    paint(parts, h)
    sharpen(parts)
    color = base.bake(parts, sc)
    base.textured_materials(color)
    base.previews(sc)
    base.export(parts)
    import json
    path = os.path.join(OUT_DIR, 'parts.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    data['_pivots']['muzzle'] = tuple(base.MUZZLE_AT)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)


main()
