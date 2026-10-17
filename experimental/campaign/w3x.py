"""Write W3X models (the SDK's XML model format that BinaryAssetBuilder compiles) from plain geometry.

A static model is: W3DHierarchy (ROOTTRANSFORM + one pivot), W3DMesh (vertices, normals, texture coordinates,
shade indices, triangles with face normal + plane distance, an FXShader), W3DContainer (sub-object -> bone). The
layout follows the SDK samples (Art/AU/AUGunshipProjectile.w3x; the gunship body uses ObjectsAllied.fx with
DiffuseTexture / NormalMap / SpecMap). Textures are Texture assets: <Texture id=".." File="..tga"/> next to the
model under C:\\RA3ModSDK\\Art\\<first two letters of the name>\\.
"""
import math
import os
import struct

ART = os.path.join(os.environ.get('CNV_SDK', r'C:\RA3ModSDK3'), 'Art')
FIXUP = ('\t\t\t<FixupMatrix M00="1.000000" M10="0.000000" M20="0.000000" M30="0.000000" M01="0.000000" '
         'M11="1.000000" M21="0.000000" M31="0.000000" M02="0.000000" M12="0.000000" M22="1.000000" M32="0.000000"/>')


def _f(x):
    return f'{x:.6f}'


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(sum(x * x for x in a)) or 1.0
    return tuple(x / n for x in a)


def model(name, verts, normals, uvs, tris, diffuse, normal_map, spec_map, shader='ObjectsAllied.fx'):
    """W3X text of a one-mesh static model `name` (container id name.upper(), mesh id <NAME>.MESH)."""
    up = name.upper()
    lo = [min(v[k] for v in verts) for k in range(3)]
    hi = [max(v[k] for v in verts) for k in range(3)]
    center = [(a + b) / 2 for a, b in zip(lo, hi)]
    radius = max(math.dist(center, v) for v in verts)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<AssetDeclaration xmlns="uri:ea.com:eala:asset" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
           '\t<Includes>'] + [f'\t\t<Include type="all" source="ART:{t}.xml"/>' for t in (diffuse, normal_map, spec_map)]
    out += ['\t</Includes>',
            f'\t<W3DHierarchy id="{up}_SKL">',
            '\t\t<Pivot Name="ROOTTRANSFORM" Parent="-1">',
            '\t\t\t<Translation X="0.000000" Y="0.000000" Z="0.000000"/>',
            '\t\t\t<Rotation X="0.000000" Y="0.000000" Z="0.000000" W="1.000000"/>',
            FIXUP,
            '\t\t</Pivot>',
            '\t\t<Pivot Name="MESH" Parent="0">',
            '\t\t\t<Translation X="0.000000" Y="0.000000" Z="0.000000"/>',
            '\t\t\t<Rotation X="0.000000" Y="0.000000" Z="0.000000" W="1.000000"/>',
            FIXUP,
            '\t\t</Pivot>',
            '\t</W3DHierarchy>',
            f'\t<W3DMesh id="{up}.MESH" CastShadow="true" GeometryType="Normal">',
            '\t\t<BoundingBox>',
            f'\t\t\t<Min X="{_f(lo[0])}" Y="{_f(lo[1])}" Z="{_f(lo[2])}"/>',
            f'\t\t\t<Max X="{_f(hi[0])}" Y="{_f(hi[1])}" Z="{_f(hi[2])}"/>',
            '\t\t</BoundingBox>',
            f'\t\t<BoundingSphere Radius="{_f(radius)}">',
            f'\t\t\t<Center X="{_f(center[0])}" Y="{_f(center[1])}" Z="{_f(center[2])}"/>',
            '\t\t</BoundingSphere>',
            '\t\t<Vertices>'] + [f'\t\t\t<V X="{_f(x)}" Y="{_f(y)}" Z="{_f(z)}"/>' for x, y, z in verts]
    out += ['\t\t</Vertices>', '\t\t<Normals>'] + [f'\t\t\t<N X="{_f(x)}" Y="{_f(y)}" Z="{_f(z)}"/>'
                                                   for x, y, z in normals]
    out += ['\t\t</Normals>', '\t\t<TexCoords>'] + [f'\t\t\t<T X="{_f(u)}" Y="{_f(v)}"/>' for u, v in uvs]
    out += ['\t\t</TexCoords>', '\t\t<ShadeIndices>'] + [f'\t\t\t<I>{k}</I>' for k in range(len(verts))]
    out += ['\t\t</ShadeIndices>', '\t\t<Triangles>']
    for a, b, c in tris:
        n = _norm(_cross(_sub(verts[b], verts[a]), _sub(verts[c], verts[a])))
        dist = sum(x * y for x, y in zip(n, verts[a]))
        out += ['\t\t\t<T>', f'\t\t\t\t<V>{a}</V>', f'\t\t\t\t<V>{b}</V>', f'\t\t\t\t<V>{c}</V>',
                f'\t\t\t\t<Nrm X="{_f(n[0])}" Y="{_f(n[1])}" Z="{_f(n[2])}"/>', f'\t\t\t\t<Dist>{_f(dist)}</Dist>',
                '\t\t\t</T>']
    out += ['\t\t</Triangles>',
            f'\t\t<FXShader ShaderName="{shader}" TechniqueIndex="0">',
            '\t\t\t<Constants>',
            f'\t\t\t\t<Texture Name="DiffuseTexture"><Value>{diffuse}</Value></Texture>',
            f'\t\t\t\t<Texture Name="NormalMap"><Value>{normal_map}</Value></Texture>',
            f'\t\t\t\t<Texture Name="SpecMap"><Value>{spec_map}</Value></Texture>',
            '\t\t\t\t<Float Name="EnvMult"><Value>1.000000</Value></Float>',
            '\t\t\t\t<Bool Name="AlphaTestEnable"><Value>false</Value></Bool>',
            '\t\t\t</Constants>',
            '\t\t</FXShader>',
            '\t</W3DMesh>',
            f'\t<W3DContainer id="{up}" Hierarchy="{up}_SKL">',
            '\t\t<SubObject SubObjectID="MESH" BoneIndex="1">',
            f'\t\t\t<RenderObject><Mesh>{up}.MESH</Mesh></RenderObject>',
            '\t\t</SubObject>',
            '\t</W3DContainer>',
            '</AssetDeclaration>']
    return '\n'.join(out) + '\n'


def lathe(profile, segments=32):
    """A solid of revolution around Z: `profile` is [(radius, z)] from top to bottom. Returns verts, normals,
    uvs (u around, v along the profile), triangles. Each ring is duplicated at the seam for the texture."""
    verts, normals, uvs, tris = [], [], [], []
    n = len(profile)
    # profile normals from neighbouring points (perpendicular to the profile line, pointing outwards)
    pn = []
    for k in range(n):
        r0, z0 = profile[max(k - 1, 0)]
        r1, z1 = profile[min(k + 1, n - 1)]
        dr, dz = r1 - r0, z1 - z0
        pn.append(_norm((-dz, 0.0, dr)) if (dr or dz) else (0.0, 0.0, 1.0))
    for k, (r, z) in enumerate(profile):
        for s in range(segments + 1):
            a = 2 * math.pi * s / segments
            ca, sa = math.cos(a), math.sin(a)
            verts.append((r * ca, r * sa, z))
            nx, _, nz = pn[k]
            normals.append(_norm((nx * ca, nx * sa, nz)) if abs(nx) > 1e-6 else (0.0, 0.0, 1.0 if nz >= 0 else -1.0))
            uvs.append((s / segments, k / (n - 1)))
    row = segments + 1
    for k in range(n - 1):
        for s in range(segments):
            a, b = k * row + s, k * row + s + 1
            c, d = a + row, b + row
            tris += [(a, c, b), (b, c, d)]
    return verts, normals, uvs, tris


def tga(path, w, h, pixel):
    """Uncompressed 32-bit TGA; pixel(x, y) -> (r, g, b, a), y = 0 at the top."""
    head = struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 8 | 0x20)
    body = bytearray()
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixel(x, y)
            body += bytes((b, g, r, a))
    with open(path, 'wb') as f:
        f.write(head + bytes(body))


def write_texture(name, w, h, pixel):
    folder = os.path.join(ART, name[:2].upper())
    os.makedirs(folder, exist_ok=True)
    tga(os.path.join(folder, name + '.tga'), w, h, pixel)
    with open(os.path.join(folder, name + '.xml'), 'w', encoding='utf-8', newline='\r\n') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<AssetDeclaration xmlns="uri:ea.com:eala:asset" '
                f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n\t<Texture id="{name}" File="{name}.tga" />\n'
                '</AssetDeclaration>\n')


def write_model(name, text):
    folder = os.path.join(ART, name[:2].upper())
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name + '.w3x'), 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(text)


# ------------------------------------------------------------------ rigid multi-part models and animations
def _mesh_xml(mesh_id, verts, normals, uvs, tris, textures, shader='ObjectsAllied.fx', shadow=True):
    lo = [min(v[k] for v in verts) for k in range(3)]
    hi = [max(v[k] for v in verts) for k in range(3)]
    center = [(a + b) / 2 for a, b in zip(lo, hi)]
    radius = max(math.dist(center, v) for v in verts)
    out = [f'\t<W3DMesh id="{mesh_id}" CastShadow="{"true" if shadow else "false"}" GeometryType="Normal">',
           '\t\t<BoundingBox>', f'\t\t\t<Min X="{_f(lo[0])}" Y="{_f(lo[1])}" Z="{_f(lo[2])}"/>',
           f'\t\t\t<Max X="{_f(hi[0])}" Y="{_f(hi[1])}" Z="{_f(hi[2])}"/>', '\t\t</BoundingBox>',
           f'\t\t<BoundingSphere Radius="{_f(radius)}">',
           f'\t\t\t<Center X="{_f(center[0])}" Y="{_f(center[1])}" Z="{_f(center[2])}"/>', '\t\t</BoundingSphere>',
           '\t\t<Vertices>'] + [f'\t\t\t<V X="{_f(x)}" Y="{_f(y)}" Z="{_f(z)}"/>' for x, y, z in verts]
    out += ['\t\t</Vertices>', '\t\t<Normals>'] + [f'\t\t\t<N X="{_f(x)}" Y="{_f(y)}" Z="{_f(z)}"/>' for x, y, z in normals]
    out += ['\t\t</Normals>', '\t\t<TexCoords>'] + [f'\t\t\t<T X="{_f(u)}" Y="{_f(v)}"/>' for u, v in uvs]
    out += ['\t\t</TexCoords>', '\t\t<ShadeIndices>'] + [f'\t\t\t<I>{k}</I>' for k in range(len(verts))]
    out += ['\t\t</ShadeIndices>', '\t\t<Triangles>']
    for a, b, c in tris:
        n = _norm(_cross(_sub(verts[b], verts[a]), _sub(verts[c], verts[a])))
        dist = sum(x * y for x, y in zip(n, verts[a]))
        out += ['\t\t\t<T>', f'\t\t\t\t<V>{a}</V>', f'\t\t\t\t<V>{b}</V>', f'\t\t\t\t<V>{c}</V>',
                f'\t\t\t\t<Nrm X="{_f(n[0])}" Y="{_f(n[1])}" Z="{_f(n[2])}"/>', f'\t\t\t\t<Dist>{_f(dist)}</Dist>',
                '\t\t\t</T>']
    diffuse, normal_map, spec_map = textures
    out += ['\t\t</Triangles>', f'\t\t<FXShader ShaderName="{shader}" TechniqueIndex="0">', '\t\t\t<Constants>',
            f'\t\t\t\t<Texture Name="DiffuseTexture"><Value>{diffuse}</Value></Texture>',
            f'\t\t\t\t<Texture Name="NormalMap"><Value>{normal_map}</Value></Texture>',
            f'\t\t\t\t<Texture Name="SpecMap"><Value>{spec_map}</Value></Texture>',
            '\t\t\t\t<Float Name="EnvMult"><Value>1.000000</Value></Float>',
            '\t\t\t\t<Bool Name="AlphaTestEnable"><Value>false</Value></Bool>',
            '\t\t\t</Constants>', '\t\t</FXShader>', '\t</W3DMesh>']
    return out


def rig_model(name, pivots, parts, textures):
    """W3X text of a rigid model: `pivots` = [(pivot name, parent index, (x, y, z))] after ROOTTRANSFORM (index 0;
    parents refer to these indices, translations are relative to the parent), `parts` = [(mesh name, pivot index,
    (verts, normals, uvs, tris))] in that pivot's space. Container id NAME, hierarchy NAME_SKL."""
    up = name.upper()
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<AssetDeclaration xmlns="uri:ea.com:eala:asset" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
           '\t<Includes>'] + [f'\t\t<Include type="all" source="ART:{t}.xml"/>' for t in textures] + ['\t</Includes>',
                                                                                                  f'\t<W3DHierarchy id="{up}_SKL">']
    for pname, parent, (x, y, z) in [('ROOTTRANSFORM', -1, (0.0, 0.0, 0.0))] + list(pivots):
        out += [f'\t\t<Pivot Name="{pname.upper()}" Parent="{parent}">',
                f'\t\t\t<Translation X="{_f(x)}" Y="{_f(y)}" Z="{_f(z)}"/>',
                '\t\t\t<Rotation X="0.000000" Y="0.000000" Z="0.000000" W="1.000000"/>', FIXUP, '\t\t</Pivot>']
    out.append('\t</W3DHierarchy>')
    for mesh, _, geo in parts:
        out += _mesh_xml(f'{up}.{mesh.upper()}', *geo, textures)
    out.append(f'\t<W3DContainer id="{up}" Hierarchy="{up}_SKL">')
    for mesh, bone, _ in parts:
        out += [f'\t\t<SubObject SubObjectID="{mesh.upper()}" BoneIndex="{bone}">',
                f'\t\t\t<RenderObject><Mesh>{up}.{mesh.upper()}</Mesh></RenderObject>', '\t\t</SubObject>']
    out += ['\t</W3DContainer>', '</AssetDeclaration>']
    return '\n'.join(out) + '\n'


def spin_animation(anim, model, pivot_index, frames=60, turns=1.0, fps=30, still=()):
    """A looping W3DAnimation turning one pivot about Z `turns` times over `frames` frames; `still` pivots get a
    constant identity orientation channel."""
    up = model.upper()
    channels = []
    for p in [pivot_index] + list(still):
        channels.append(f'\t\t\t<ChannelQuaternion Pivot="{p}" Type="Orientation" FirstFrame="0">')
        for k in range(frames):
            a = 2 * math.pi * turns * k / frames if p == pivot_index else 0.0
            channels.append(f'\t\t\t\t<Frame X="0.000000" Y="0.000000" Z="{_f(math.sin(a / 2))}" W="{_f(math.cos(a / 2))}"/>')
        channels.append('\t\t\t</ChannelQuaternion>')
    return '\n'.join(['<?xml version="1.0" encoding="UTF-8"?>',
                      '<AssetDeclaration xmlns="uri:ea.com:eala:asset" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
                      '\t<Includes>', f'\t\t<Include type="all" source="ART:{model}.w3x"/>', '\t</Includes>',
                      f'\t<W3DAnimation id="{anim.upper()}" Hierarchy="{up}_SKL" NumFrames="{frames}" FrameRate="{fps}">',
                      '\t\t<Channels>'] + channels + ['\t\t</Channels>', '\t</W3DAnimation>', '</AssetDeclaration>']) + '\n'


def box(x0, y0, z0, x1, y1, z1, top_shrink=0.0, uv=(0.0, 0.0, 1.0, 1.0)):
    """A box (top face optionally shrunk in x for sloped sides); 24 vertices with flat normals."""
    s = top_shrink
    c = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0 + s, y0 + s, z1), (x1 - s, y0 + s, z1), (x1 - s, y1 - s, z1), (x0 + s, y1 - s, z1)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    u0, v0, u1, v1 = uv
    verts, normals, uvs, tris = [], [], [], []
    for f in faces:
        p = [c[k] for k in f]
        n = _norm(_cross(_sub(p[1], p[0]), _sub(p[2], p[0])))
        base = len(verts)
        verts += p
        normals += [n] * 4
        uvs += [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        tris += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    return verts, normals, uvs, tris


def merge(*geos):
    verts, normals, uvs, tris = [], [], [], []
    for v, n, u, t in geos:
        base = len(verts)
        verts += v
        normals += n
        uvs += u
        tris += [(a + base, b + base, c + base) for a, b, c in t]
    return verts, normals, uvs, tris


def transform(geo, rot=None, move=(0.0, 0.0, 0.0)):
    """Rotate (3x3 rows) then translate a geometry."""
    v, n, u, t = geo
    r = rot or ((1, 0, 0), (0, 1, 0), (0, 0, 1))

    def ap(p):
        return tuple(sum(r[i][k] * p[k] for k in range(3)) for i in range(3))
    return [tuple(a + b for a, b in zip(ap(p), move)) for p in v], [_norm(ap(q)) for q in n], u, t
