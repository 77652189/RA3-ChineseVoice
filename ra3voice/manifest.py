"""SAGE (RA3 / Uprising) asset stream manifest, versions 6 and 7.

Header: version 7 (Uprising) = 13 x uint32 (52 bytes); version 6 (RA3) = 12 x uint32 (48 bytes, no leading u32).
Entry:  12 x uint32 LE (48 bytes):
  0 TypeId, 1 InstanceId, 2 TypeHash, 3 InstanceHash, 6 NameOffset, 8 InstanceDataSize, 9 RelocationDataSize
The .bin starts with a 4-byte (v6) / 8-byte (v7) header, then each asset's data in manifest order.
cdata files are named TypeId.TypeHash.InstanceId.InstanceHash.cdata (hex).
"""
import struct
from dataclasses import dataclass


@dataclass
class Asset:
    name: str          # e.g. "AudioFile:IUGigaF_voiSelecta"
    type_id: int
    inst_id: int
    type_hash: int
    inst_hash: int
    inst_size: int
    bin_offset: int    # offset of the instance data inside the decompressed .bin
    stream: str = 'audio'

    @property
    def short_name(self):
        return self.name.split(':', 1)[1]

    @property
    def cdata_path(self):
        return (f'data\\{self.stream}\\cdata\\{self.type_id:08x}.{self.type_hash:08x}.'
                f'{self.inst_id:08x}.{self.inst_hash:08x}.cdata')


def version(raw):
    """RA3 1.x streams are version 6 (u8 bigEndian, u8 linked, u16 version); Uprising is 7 (extra leading u32)."""
    v6 = struct.unpack_from('<H', raw, 2)[0]
    if v6 in (5, 6):
        return v6
    v7 = struct.unpack_from('<H', raw, 4)[0]
    if v7 == 7:
        return 7
    raise ValueError(f'unknown manifest version ({v6}, {v7})')


def parse(raw):
    v6 = version(raw) <= 6
    base = 4 if v6 else 8                         # offset of StreamChecksum
    count = struct.unpack_from('<I', raw, base + 8)[0]
    ref_size, ref_manifest_size, name_size = struct.unpack_from('<3I', raw, base + 28)
    ent_off = base + 44
    # after the entries: asset-reference buffer, referenced-manifest-name buffer (linked patch
    # streams such as audio.5), then the asset-name buffer
    names_off = ent_off + count * 48 + ref_size + ref_manifest_size
    names = raw[names_off:names_off + name_size]
    assets, bin_off = [], (4 if v6 else 8)        # .bin header: 4 bytes (v6) / 8 bytes (v7)
    for i in range(count):
        f = struct.unpack_from('<12I', raw, ent_off + i * 48)
        end = names.index(b'\0', f[6])
        assets.append(Asset(names[f[6]:end].decode('latin-1'), f[0], f[1], f[2], f[3], f[8], bin_off))
        bin_off += f[8]
    return assets
