"""Read compiled W3D assets (BinaryAssetBuilder output / retail streams) back into plain geometry.

W3DMesh instance (decoded against our own CNTANK.HULL, whose source we know): f32 bounding box min / max at
12..35, sphere radius at 36 and centre at 40..51, u32 triangle count at 52, then pointers (relocated: offsets
from the instance start) -- +4 the vertex block. The vertex block holds the stream name, u32 vertex count,
u32 stride, u32 pointer to the vertex data; a 36-byte vertex is position (3 f32), normal (3 f32), colour (u32),
texture coordinate (2 f32). Retail meshes use other strides too (skinned ones carry bone data); read_mesh only
trusts the layouts it recognises.
"""
import struct


def mesh_info(d):
    lo = struct.unpack_from('<3f', d, 12)
    hi = struct.unpack_from('<3f', d, 24)
    tris = struct.unpack_from('<I', d, 52)[0]
    vb = struct.unpack_from('<I', d, 4)[0]
    count, stride, ptr = struct.unpack_from('<3I', d, vb + 8)
    return dict(min=lo, max=hi, size=tuple(round(b - a, 1) for a, b in zip(lo, hi)), triangles=tris,
                vertices=count, stride=stride, data=ptr)
