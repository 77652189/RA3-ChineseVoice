"""CNV light tank, built procedurally in Blender (run headless):

  "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Blender\\blender.exe" -b -P experimental/units/cnv_lighttank.py -- <out dir>

Style follows the retail Allied vehicles (work/reference: Guardian, Riptide, Mirage textures and box art): chunky,
wide and low, heavily bevelled edges catching highlights, big segmented tracks under side skirts, a low faceted
turret, silver-white / cool grey metal with dark seams, a few cyan glows, team colour only on stripes. Size close
to the Riptide (45 x 25 x 21 game units) with the Guardian's budget (~3.7k triangles over hull, treads, glows).

Outputs in <out dir>: preview_*.png (CPU Cycles renders from three angles), CNTankL.png (diffuse, baked: base
colour x ambient occlusion + edge highlight), CNTankL_mask.png (team colour mask, baked), parts.json (per part:
bone, vertices, normals, uvs, triangles) for w3x.rig_model. Everything runs on the CPU (the user may be playing).
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

OUT = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else os.path.abspath('cnv_lighttank_out')
os.makedirs(OUT, exist_ok=True)
TEX = 512

STEEL = (0.62, 0.66, 0.70)       # cool silver-grey
DARK = (0.18, 0.19, 0.21)        # tracks, vents
GLOW = (0.20, 0.90, 1.00)        # cyan sensor


# ------------------------------------------------------------------ scene
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 48
    sc.cycles.use_denoising = False
    sc.unit_settings.system = 'NONE'
    return sc


def material(name, color, team=0.0, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m['team'] = team
    m['emit'] = emit
    m['color'] = color
    bsdf = m.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1.0)
    bsdf.inputs['Metallic'].default_value = 0.6
    bsdf.inputs['Roughness'].default_value = 0.35
    if emit:
        bsdf.inputs['Emission Color'].default_value = (*color, 1.0)
        bsdf.inputs['Emission Strength'].default_value = emit
    return m


def obj_from_bm(name, bm, mats):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    for m in mats:
        me.materials.append(m)
    return ob


def box(bm, x0, y0, z0, x1, y1, z1, mat=0, taper_front=0.0, taper_top=0.0):
    """A box; taper_front pulls the top front edge back (sloped glacis), taper_top shrinks the top face in y."""
    vs = [bm.verts.new(p) for p in [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0 + taper_top, z1), (x1 - taper_front, y0 + taper_top, z1),
        (x1 - taper_front, y1 - taper_top, z1), (x0, y1 - taper_top, z1)]]
    for f in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
        face = bm.faces.new([vs[k] for k in f])
        face.material_index = mat
    return vs


def cylinder(bm, axis, center, radius, length, segments=12, mat=0, cap_scale=1.0):
    """A cylinder along 'x' or 'y' or 'z' through center."""
    cx, cy, cz = center
    rings = []
    for side in (-0.5, 0.5):
        ring = []
        for k in range(segments):
            a = 2 * math.pi * k / segments
            r = radius * (cap_scale if side > 0 else 1.0)
            u, v = r * math.cos(a), r * math.sin(a)
            t = side * length
            p = {'x': (cx + t, cy + u, cz + v), 'y': (cx + u, cy + t, cz + v), 'z': (cx + u, cy + v, cz + t)}[axis]
            ring.append(bm.verts.new(p))
        rings.append(ring)
    for k in range(segments):
        a, b = k, (k + 1) % segments
        f = bm.faces.new([rings[0][a], rings[0][b], rings[1][b], rings[1][a]])
        f.material_index = mat
    for ring, rev in ((rings[0], True), (rings[1], False)):
        f = bm.faces.new(list(reversed(ring)) if rev else ring)
        f.material_index = mat
    return rings


def bevel_and_finish(ob, width=0.7, segments=2, angle=40):
    mod = ob.modifiers.new('bevel', 'BEVEL')
    mod.width = width
    mod.segments = segments
    mod.limit_method = 'ANGLE'
    mod.angle_limit = math.radians(angle)
    mod.harden_normals = True
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.modifier_apply(modifier='bevel')
    me = ob.data
    bmx = bmesh.new()
    bmx.from_mesh(me)
    bmesh.ops.recalc_face_normals(bmx, faces=bmx.faces)
    bmx.to_mesh(me)
    bmx.free()
    ob.select_set(False)


# ------------------------------------------------------------------ parts (units: game units, +X forward, Z up)
def build(mats):
    steel, dark, team, glow = mats
    parts = {}

    # hull: lower body with a stepped glacis, engine deck, skirts over the upper tracks with team stripes on
    # their outer faces, headlights, exhausts, side stowage boxes
    bm = bmesh.new()
    box(bm, -17, -8.6, 3.2, 14, 8.6, 8.2, mat=0, taper_front=5.0, taper_top=1.2)       # main body
    box(bm, 9.5, -7.6, 3.4, 18, 7.6, 6.2, mat=0, taper_front=3.0, taper_top=0.8)       # lower front plate
    box(bm, -18, -8.0, 7.6, -7, 8.0, 9.6, mat=0, taper_top=1.0)                         # engine deck
    for k in range(4):                                                                 # engine vents
        box(bm, -17 + 2.4 * k, -5.2, 9.5, -15.6 + 2.4 * k, 5.2, 10.1, mat=1)
    for s in (-1, 1):
        y0, y1 = (8.6, 12.8) if s > 0 else (-12.8, -8.6)
        box(bm, -17.5, y0, 4.6, 16.5, y1, 7.4, mat=0, taper_front=2.2)                  # skirt (upper half)
        sy0, sy1 = (y1 - 0.05, y1 + 0.45) if s > 0 else (y0 - 0.45, y0 + 0.05)          # stripe, outer face
        box(bm, -13, sy0, 5.3, 9, sy1, 6.6, mat=2)
        box(bm, -6, 6.4 * s - 1.4, 8.0, 2, 6.4 * s + 1.4, 9.6, mat=0)                    # stowage box
        box(bm, 15.2, 5.6 * s - 1.0, 5.0, 16.6, 5.6 * s + 1.0, 6.2, mat=3)               # headlight (glow)
        cylinder(bm, 'x', (-18.6, 4.5 * s, 8.6), 0.7, 1.6, segments=8, mat=1)            # exhaust
    ob = obj_from_bm('HULL', bm, mats)
    bevel_and_finish(ob, width=0.7)
    parts['HULL'] = ob

    # treads: wide dark bands with chunky segments, big road wheels and sprockets visible below the skirts
    bm = bmesh.new()
    for s in (-1, 1):
        y0, y1 = (8.2, 12.6) if s > 0 else (-12.6, -8.2)
        box(bm, -18.5, y0, 0.0, 17.5, y1, 5.2, mat=1, taper_front=2.0)                  # tread band
        for k in range(12):                                                             # tread cleats
            x = -17.5 + 3.0 * k
            box(bm, x, y0 - 0.2, -0.25, x + 1.4, y1 + 0.2, 0.35, mat=1)
        for k in range(5):
            cylinder(bm, 'y', (-13.5 + 6.6 * k, y1 + 0.15 if s > 0 else y0 - 0.15, 2.4), 2.1, 0.6,
                     segments=10, mat=0)
    ob = obj_from_bm('TREADS', bm, mats)
    bevel_and_finish(ob, width=0.35, segments=1)
    parts['TREADS'] = ob

    # turret: big, low, faceted (8 sides), team-colour panels on the flanks, cyan sensor dome, rear bustle
    bm = bmesh.new()
    n = 8
    bottom, top = [], []
    for k in range(n):
        a = 2 * math.pi * (k + 0.5) / n
        bottom.append(bm.verts.new((8.6 * math.cos(a) - 0.5, 7.4 * math.sin(a), 0.0)))
        top.append(bm.verts.new((6.4 * math.cos(a) - 1.2, 5.4 * math.sin(a), 5.0)))
    for k in range(n):
        bm.faces.new([bottom[k], bottom[(k + 1) % n], top[(k + 1) % n], top[k]]).material_index = 0
    bm.faces.new(list(reversed(bottom))).material_index = 0
    bm.faces.new(top).material_index = 0
    box(bm, -11.5, -5.6, 0.6, -6.5, 5.6, 4.0, mat=0, taper_top=0.8)                    # rear bustle
    for s in (-1, 1):                                                                   # team panels
        box(bm, -6.0, 6.9 * s - 0.4, 1.2, 1.5, 6.9 * s + 0.4, 3.4, mat=2)
    cylinder(bm, 'z', (-3.0, -2.8, 5.4), 1.4, 1.6, segments=10, mat=3, cap_scale=0.7)  # sensor dome (glow)
    box(bm, -9.5, 1.5, 4.0, -7.0, 3.5, 5.6, mat=1)                                      # hatch
    ob = obj_from_bm('TURRET', bm, mats)
    bevel_and_finish(ob, width=0.55)
    parts['TURRET'] = ob

    # barrel: chunky mantlet, thick shorter tube, fume extractor, big muzzle brake (origin = pitch pivot)
    bm = bmesh.new()
    box(bm, -2.0, -3.2, -2.2, 2.8, 3.2, 2.4, mat=0, taper_front=0.8)
    cylinder(bm, 'x', (8.5, 0, 0.1), 1.25, 13.0, segments=12, mat=0)
    cylinder(bm, 'x', (8.0, 0, 0.1), 1.75, 2.4, segments=12, mat=1)
    cylinder(bm, 'x', (16.3, 0, 0.1), 2.0, 3.2, segments=12, mat=0)
    ob = obj_from_bm('BARREL', bm, mats)
    bevel_and_finish(ob, width=0.35, segments=1)
    parts['BARREL'] = ob
    return parts


# pivot layout (also used by the w3x export): turret ring on the hull, barrel pitch pivot in the turret
TURRET_AT = Vector((0.5, 0.0, 9.0))
PITCH_AT = Vector((7.4, 0.0, 2.6))


def place(parts):
    parts['TURRET'].location = TURRET_AT
    parts['BARREL'].location = TURRET_AT + PITCH_AT


# ------------------------------------------------------------------ texture: UVs, bake colour and team mask
def bake(parts, sc):
    obs = list(parts.values())
    for ob in obs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(55), island_margin=0.02, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode='OBJECT')

    color_img = bpy.data.images.new('CNTankL', TEX, TEX)
    mask_img = bpy.data.images.new('CNTankL_mask', TEX, TEX)

    def setup(target, kind):
        # every material becomes an emission shader computing what we want baked, with the target image active
        for m in bpy.data.materials:
            nt = m.node_tree
            for nd in list(nt.nodes):
                nt.nodes.remove(nd)
            out = nt.nodes.new('ShaderNodeOutputMaterial')
            em = nt.nodes.new('ShaderNodeEmission')
            nt.links.new(em.outputs[0], out.inputs[0])
            if kind == 'mask':
                v = float(m['team'])
                em.inputs['Color'].default_value = (v, v, v, 1)
            else:
                base = nt.nodes.new('ShaderNodeRGB')
                base.outputs[0].default_value = (*m['color'], 1)
                ao = nt.nodes.new('ShaderNodeAmbientOcclusion')
                ao.inputs['Distance'].default_value = 4.0
                geo = nt.nodes.new('ShaderNodeNewGeometry')
                edge = nt.nodes.new('ShaderNodeMapRange')               # pointiness -> edge highlight 0..0.35
                edge.inputs['From Min'].default_value = 0.5
                edge.inputs['From Max'].default_value = 0.62
                edge.inputs['To Max'].default_value = 0.35 if sum(m['color']) > 1.0 else 0.06   # dark parts stay dark
                nt.links.new(geo.outputs['Pointiness'], edge.inputs['Value'])
                mul = nt.nodes.new('ShaderNodeMix')
                mul.data_type = 'RGBA'
                mul.blend_type = 'MULTIPLY'
                mul.inputs['Factor'].default_value = 0.85
                nt.links.new(base.outputs[0], mul.inputs['A'])
                nt.links.new(ao.outputs['AO'], mul.inputs['B'])
                # panel seams: axis-aligned grid lines (every PANEL units), each axis only on faces it crosses
                # (weighted by 1 - |normal component|), so panels read as machined plates, not cracks
                coord = nt.nodes.new('ShaderNodeTexCoord')
                xyz = nt.nodes.new('ShaderNodeSeparateXYZ')
                nt.links.new(coord.outputs['Object'], xyz.inputs['Vector'])
                nrm = nt.nodes.new('ShaderNodeSeparateXYZ')
                nt.links.new(geo.outputs['Normal'], nrm.inputs['Vector'])
                seam_prev = None
                for axis, size in (('X', 11.0), ('Y', 8.0), ('Z', 5.5)):
                    fr = nt.nodes.new('ShaderNodeMath')            # distance to the nearest grid line, 0..0.5
                    fr.operation = 'PINGPONG'
                    fr.inputs[1].default_value = 0.5
                    sc_ = nt.nodes.new('ShaderNodeMath')
                    sc_.operation = 'DIVIDE'
                    sc_.inputs[1].default_value = size
                    nt.links.new(xyz.outputs[axis], sc_.inputs[0])
                    nt.links.new(sc_.outputs[0], fr.inputs[0])
                    line = nt.nodes.new('ShaderNodeMapRange')       # 1 on the line, 0 elsewhere
                    line.inputs['From Min'].default_value = 0.02
                    line.inputs['From Max'].default_value = 0.035
                    line.inputs['To Min'].default_value = 1.0
                    line.inputs['To Max'].default_value = 0.0
                    nt.links.new(fr.outputs[0], line.inputs['Value'])
                    an = nt.nodes.new('ShaderNodeMath')
                    an.operation = 'ABSOLUTE'
                    nt.links.new(nrm.outputs[axis], an.inputs[0])
                    w = nt.nodes.new('ShaderNodeMath')
                    w.operation = 'SUBTRACT'
                    w.inputs[0].default_value = 1.0
                    nt.links.new(an.outputs[0], w.inputs[1])
                    lw = nt.nodes.new('ShaderNodeMath')
                    lw.operation = 'MULTIPLY'
                    nt.links.new(line.outputs[0], lw.inputs[0])
                    nt.links.new(w.outputs[0], lw.inputs[1])
                    if seam_prev is None:
                        seam_prev = lw.outputs[0]
                    else:
                        mx = nt.nodes.new('ShaderNodeMath')
                        mx.operation = 'MAXIMUM'
                        nt.links.new(seam_prev, mx.inputs[0])
                        nt.links.new(lw.outputs[0], mx.inputs[1])
                        seam_prev = mx.outputs[0]
                seam = nt.nodes.new('ShaderNodeMapRange')            # line -> darken to 0.45
                seam.inputs['To Min'].default_value = 1.0
                seam.inputs['To Max'].default_value = 0.6
                nt.links.new(seam_prev, seam.inputs['Value'])
                grime = nt.nodes.new('ShaderNodeMapRange')
                grime.inputs['From Min'].default_value = 0.0
                grime.inputs['From Max'].default_value = 9.0
                grime.inputs['To Min'].default_value = 0.68
                grime.inputs['To Max'].default_value = 1.0
                nt.links.new(xyz.outputs['Z'], grime.inputs['Value'])
                noise = nt.nodes.new('ShaderNodeTexNoise')
                noise.inputs['Scale'].default_value = 0.35
                nt.links.new(coord.outputs['Object'], noise.inputs['Vector'])
                var = nt.nodes.new('ShaderNodeMapRange')
                var.inputs['From Min'].default_value = 0.3
                var.inputs['From Max'].default_value = 0.7
                var.inputs['To Min'].default_value = 0.88
                var.inputs['To Max'].default_value = 1.0
                nt.links.new(noise.outputs['Fac'], var.inputs['Value'])
                prev = mul.outputs['Result']
                for fac in (seam, grime, var):
                    mm = nt.nodes.new('ShaderNodeMix')
                    mm.data_type = 'RGBA'
                    mm.blend_type = 'MULTIPLY'
                    mm.inputs['Factor'].default_value = 1.0
                    nt.links.new(prev, mm.inputs['A'])
                    nt.links.new(fac.outputs[0], mm.inputs['B'])
                    prev = mm.outputs['Result']
                add = nt.nodes.new('ShaderNodeMix')
                add.data_type = 'RGBA'
                add.blend_type = 'ADD'
                nt.links.new(edge.outputs[0], add.inputs['Factor'])
                nt.links.new(prev, add.inputs['A'])
                add.inputs['B'].default_value = (1, 1, 1, 1)
                nt.links.new(add.outputs['Result'], em.inputs['Color'])
            img = nt.nodes.new('ShaderNodeTexImage')
            img.image = target
            nt.nodes.active = img
    sc.cycles.samples = 32
    for target, kind in ((color_img, 'color'), (mask_img, 'mask')):
        setup(target, kind)
        bpy.ops.object.bake(type='EMIT', margin=4)
        target.filepath_raw = os.path.join(OUT, target.name + '.png')
        target.file_format = 'PNG'
        target.save()
    for ob in obs:
        ob.select_set(False)
    return color_img


def textured_materials(color_img):
    """Preview look: the baked colour on a metallic BSDF."""
    for m in bpy.data.materials:
        nt = m.node_tree
        for nd in list(nt.nodes):
            nt.nodes.remove(nd)
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        img = nt.nodes.new('ShaderNodeTexImage')
        img.image = color_img
        nt.links.new(img.outputs['Color'], bsdf.inputs['Base Color'])
        bsdf.inputs['Metallic'].default_value = 0.5
        bsdf.inputs['Roughness'].default_value = 0.4
        if m['team']:                    # show team colour (blue) in the preview where the mask is
            bsdf.inputs['Base Color'].default_value = (0.1, 0.3, 0.9, 1)
            nt.links.remove(bsdf.inputs['Base Color'].links[0])
        if m['emit']:
            bsdf.inputs['Emission Color'].default_value = (*m['color'], 1)
            bsdf.inputs['Emission Strength'].default_value = m['emit']
        nt.links.new(bsdf.outputs[0], out.inputs[0])


# ------------------------------------------------------------------ previews and export
def previews(sc):
    world = bpy.data.worlds.new('w')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.05, 0.12, 0.18, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.6
    sc.world = world
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN'))
    sun.data.energy = 4.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    bpy.context.collection.objects.link(sun)
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
    cam.data.lens = 70
    bpy.context.collection.objects.link(cam)
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = 640, 480
    sc.cycles.samples = 48
    for name, az, el, dist in (('threequarter', 35, 35, 95), ('side', 90, 12, 95), ('rts', 20, 60, 140)):
        a, e = math.radians(az), math.radians(el)
        target = Vector((0, 0, 6))
        cam.location = target + Vector((dist * math.cos(e) * math.cos(a), -dist * math.cos(e) * math.sin(a),
                                        dist * math.sin(e)))
        cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(OUT, f'preview_{name}.png')
        bpy.ops.render.render(write_still=True)


def export(parts):
    """parts.json: geometry per part in its bone's space (hull and treads on BODY, turret, barrel on pitch)."""
    out = {}
    for name, ob in parts.items():
        me = ob.data
        me.calc_loop_triangles()
        uv = me.uv_layers.active.data
        # per-corner normals as Blender shades them (bevel's hardened normals); MeshLoop.normal is not filled in
        # Blender 4.1+ and came out zero / vertex-averaged (black and blotchy faces in game, CampNew23 run 2)
        corner = [c.vector.copy() for c in me.corner_normals]
        origin = ob.location.copy()
        verts, normals, uvs, tris, index = [], [], [], [], {}
        for lt in me.loop_triangles:
            tri = []
            for li in lt.loops:
                loop = me.loops[li]
                co = me.vertices[loop.vertex_index].co
                n = corner[li] if corner[li].length > 1e-6 else lt.normal       # degenerate corners
                u = uv[li].uv
                key = (tuple(round(c, 4) for c in co), tuple(round(c, 3) for c in n), (round(u[0], 4), round(u[1], 4)))
                if key not in index:
                    index[key] = len(verts)
                    verts.append(tuple(co))
                    normals.append(tuple(n))
                    # Blender's v as is: with 1 - v most faces sampled the unbaked background in game
                    # (CNV_UV_DEBUG magenta run) -- the textures w3x.tga writes end up read bottom-up
                    uvs.append((u[0], u[1]))
                tri.append(index[key])
            tris.append(tri)
        out[name] = dict(origin=tuple(origin), vertices=verts, normals=normals, uvs=uvs, triangles=tris)
    out['_pivots'] = dict(turret=tuple(TURRET_AT), pitch=tuple(PITCH_AT))
    with open(os.path.join(OUT, 'parts.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f)
    total = sum(len(v['triangles']) for k, v in out.items() if not k.startswith('_'))
    print('CNV export:', {k: len(v['triangles']) for k, v in out.items() if not k.startswith('_')}, 'total', total)


def main():
    sc = reset()
    mats = [material('steel', STEEL), material('dark', DARK), material('team', STEEL, team=1.0),
            material('glow', GLOW, emit=4.0)]
    parts = build(mats)
    place(parts)
    color = bake(parts, sc)
    textured_materials(color)
    previews(sc)
    export(parts)


if __name__ == '__main__':          # Blender -P runs this as __main__; ai_lighttank_blend.py imports the bake / export
    main()
