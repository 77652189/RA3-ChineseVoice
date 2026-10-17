"""CNV light tank v2, modelled procedurally after the AI concept (work/units/lighttank_ai/concept_0.png, HunyuanDiT),
in Blender (run headless):

  "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Blender\\blender.exe" -b --factory-startup -P experimental/units/cnv_lighttank2.py -- <out dir>

Workflow decided after CampNew24 (parametric vs AI-shaped tank in game): the AI draws the concept, the model is
built by hand-written geometry, because AI meshes come out soft and dented. Concept features carried over: a
wedge nose between two track fenders reaching forward, cyan light bars on the fender fronts, exposed wide tracks
with six road wheels and cyan hubs, vent grilles on the rear flanks, a low faceted turret with a dark visor slit,
a sensor pod and an antenna on top, a long barrel with sleeve and muzzle brake. Team colour (not in the concept)
on fender flanks and turret sides. Darker steel than v1 (v1 read too white next to retail units in game).

Bake, previews and parts.json come from cnv_lighttank.py, so both versions share one look and one exporter.
"""
import math
import os
import sys

import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cnv_lighttank as base                       # noqa: E402

STEEL = (0.50, 0.53, 0.57)
DARK = (0.14, 0.15, 0.17)
GLOW = (0.20, 0.90, 1.00)
box, cylinder = base.box, base.cylinder


def prism(bm, profile, y0, y1, mat=0):
    """A side profile [(x, z), ...] (counter-clockwise seen from +y) extruded from y0 to y1."""
    a = [bm.verts.new((x, y0, z)) for x, z in profile]
    b = [bm.verts.new((x, y1, z)) for x, z in profile]
    n = len(profile)
    faces = [bm.faces.new(a), bm.faces.new(list(reversed(b)))]
    faces += [bm.faces.new([a[k], b[k], b[(k + 1) % n], a[(k + 1) % n]]) for k in range(n)]
    for f in faces:
        f.material_index = mat


def loft(bm, bottom, z0, top, z1, mat=0):
    """Two top-view outlines [(x, y), ...] with the same vertex count, at z0 and z1, joined (a tapered block)."""
    a = [bm.verts.new((x, y, z0)) for x, y in bottom]
    b = [bm.verts.new((x, y, z1)) for x, y in top]
    n = len(bottom)
    faces = [bm.faces.new(list(reversed(a))), bm.faces.new(b)]
    faces += [bm.faces.new([a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]]) for k in range(n)]
    for f in faces:
        f.material_index = mat


def build(mats):
    parts = {}

    # hull: centre body, wedge nose between the fenders, two fenders over the tracks (light bar in front, team
    # stripe and vent grille on the flank), engine deck vents, nose hatch
    bm = bmesh.new()
    prism(bm, [(-17.5, 3.2), (12.0, 3.2), (13.0, 8.0), (9.0, 9.8), (-15.0, 9.8), (-17.5, 8.6)], -7.4, 7.4)
    prism(bm, [(10.0, 3.0), (17.0, 3.6), (18.4, 5.4), (17.6, 7.2), (11.0, 9.0)], -5.2, 5.2)      # nose
    for s in (-1, 1):
        y0, y1 = (7.2, 12.8) if s > 0 else (-12.8, -7.2)
        prism(bm, [(-18.4, 6.2), (17.6, 6.2), (18.6, 7.6), (17.2, 8.8), (13.5, 9.4), (-16.0, 9.4),
                   (-18.6, 8.4)], y0, y1)                                                          # fender
        box(bm, 18.0, y0 + 0.6, 6.7, 18.75, y1 - 0.6, 7.8, mat=3)                                   # light bar
        out = y1 if s > 0 else y0
        box(bm, -5.0, out - 0.35, 7.0, 11.0, out + 0.35, 8.0, mat=2)                                # team stripe
        for k in range(4):                                                                          # flank grille
            box(bm, -15.0 + 1.5 * k, out - 0.3, 7.0, -14.2 + 1.5 * k, out + 0.3, 8.7, mat=1)
        box(bm, -2.0, 4.6 * s - 1.2, 9.6, 3.5, 4.6 * s + 1.2, 10.4, mat=0)                          # deck box
    for k in range(5):                                                                              # engine vents
        box(bm, -16.5 + 1.6 * k, -4.2, 9.7, -15.6 + 1.6 * k, 4.2, 10.3, mat=1)
    box(bm, 12.0, -2.4, 8.4, 15.0, 2.4, 8.9, mat=0)                                                 # nose hatch
    ob = base.obj_from_bm('HULL', bm, mats)
    base.bevel_and_finish(ob, width=0.6)
    parts['HULL'] = ob

    # tracks: rounded loops (dark), cleats top and bottom, six road wheels with glowing hubs, drive sprocket
    bm = bmesh.new()
    loop = [(-17.0, 1.0), (-15.0, 0.0), (13.5, 0.0), (17.0, 2.4), (17.4, 4.4), (15.5, 6.3), (-16.4, 6.3),
            (-18.4, 4.4)]
    for s in (-1, 1):
        y0, y1 = (7.6, 12.4) if s > 0 else (-12.4, -7.6)
        prism(bm, loop, y0, y1, mat=1)
        for k in range(11):                          # top run only: the bottom one is never seen
            x = -14.5 + 2.8 * k
            box(bm, x, y0 - 0.15, 6.1, x + 1.2, y1 + 0.15, 6.6, mat=1)
        out = y1 + 0.3 if s > 0 else y0 - 0.3
        for k in range(6):
            x = -12.5 + 5.0 * k
            cylinder(bm, 'y', (x, out, 2.4), 2.0, 0.6, segments=10, mat=1)
            cylinder(bm, 'y', (x, out + 0.35 * s, 2.4), 0.95, 0.3, segments=8, mat=3)                # hub glow
        cylinder(bm, 'y', (15.2, out, 3.6), 1.6, 0.6, segments=10, mat=0)                           # sprocket
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    ob = base.obj_from_bm('TREADS', bm, mats)           # no bevel: dark and small on screen, half the budget
    parts['TREADS'] = ob

    # turret: low faceted wedge, dark visor slit, team panels on the sides, rear bustle, sensor pod with a glowing
    # lens, small box and antenna on top
    bm = bmesh.new()
    loft(bm, [(6.6, -3.4), (6.6, 3.4), (2.0, 6.8), (-8.0, 6.8), (-10.0, 4.6), (-10.0, -4.6), (-8.0, -6.8),
              (2.0, -6.8)], 0.0,
         [(4.4, -2.4), (4.4, 2.4), (1.0, 5.3), (-7.0, 5.3), (-8.6, 3.6), (-8.6, -3.6), (-7.0, -5.3),
          (1.0, -5.3)], 3.4)
    box(bm, -12.2, -4.2, 0.4, -9.4, 4.2, 2.9, mat=0, taper_top=0.6)                                 # bustle
    box(bm, 4.9, -2.4, 1.2, 6.5, 2.4, 1.9, mat=1)                                                    # visor slit
    for s in (-1, 1):
        box(bm, -6.5, 6.1 * s - 0.35, 0.7, 0.5, 6.1 * s + 0.35, 1.9, mat=2)                          # team panel
    cylinder(bm, 'x', (-1.6, -2.4, 4.4), 1.0, 3.2, segments=8, mat=0)                              # sensor pod
    cylinder(bm, 'x', (0.1, -2.4, 4.4), 0.65, 0.3, segments=8, mat=3)                               # lens
    box(bm, -4.6, 1.6, 3.3, -2.2, 3.6, 4.2, mat=0)                                                   # top box
    box(bm, -7.4, 3.9, 3.3, -7.0, 4.3, 9.5, mat=1)                                                  # antenna
    ob = base.obj_from_bm('TURRET', bm, mats)
    base.bevel_and_finish(ob, width=0.45)
    parts['TURRET'] = ob

    # barrel (origin = pitch pivot at the turret front): mantlet, long tube, sleeve, muzzle brake
    bm = bmesh.new()
    box(bm, -1.4, -2.3, -1.5, 1.8, 2.3, 1.5, mat=0, taper_front=0.6)
    cylinder(bm, 'x', (12.5, 0, 0), 0.8, 22.0, segments=10, mat=0)
    cylinder(bm, 'x', (4.2, 0, 0), 1.2, 4.0, segments=10, mat=0)
    cylinder(bm, 'x', (23.0, 0, 0), 1.15, 2.2, segments=10, mat=1)
    ob = base.obj_from_bm('BARREL', bm, mats)
    base.bevel_and_finish(ob, width=0.25, segments=1)
    parts['BARREL'] = ob
    return parts


TURRET_AT = Vector((1.5, 0.0, 9.6))
PITCH_AT = Vector((6.0, 0.0, 1.7))
MUZZLE_AT = (24.2, 0.0, 0.0)        # in the pitch bone; make_campnew25.py places BONE_GUN_MUZZLE here


def main():
    base.TURRET_AT, base.PITCH_AT = TURRET_AT, PITCH_AT
    sc = base.reset()
    mats = [base.material('steel', STEEL), base.material('dark', DARK), base.material('team', STEEL, team=1.0),
            base.material('glow', GLOW, emit=4.0)]
    parts = build(mats)
    base.place(parts)
    color = base.bake(parts, sc)
    base.textured_materials(color)
    base.previews(sc)
    base.export(parts)


main()
