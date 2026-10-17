"""SAGE name hashes, computed by EA's own EALA.Hash.FastHash (C:\\RA3ModSDK3\\tools\\EALA.Hash.dll).

Asset instance ids are FastHash(lower-case name) (TerrainTextureAtlas:360_DLC_TestMap -> 0x91bed32b,
W3DAnimation:CNTank_SPIN -> 0x793579c8), and a terrain atlas Tile's TextureID is FastHash(lower-case terrain asset
id) (Dirt_Yucatan01 -> 2470508463, as the SDK's 360_DLC_TestMap map.xml has it). FastHash is not plain
SuperFastHash (tried with seed = length and 0), so instead of re-implementing it this calls the DLL: it is a
32-bit mixed-mode assembly, so the host is the 32-bit Windows PowerShell (SysWOW64; ASCII-only command, the
reason for preferring pwsh elsewhere is the encoding of Chinese scripts). Results are cached in work/.
"""
import json
import os
import subprocess

DLL = os.path.join(os.environ.get('CNV_SDK', r'C:\RA3ModSDK3'), 'tools', 'EALA.Hash.dll')
PS32 = r'C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe'
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'work',
                     'fasthash_cache.json')


def _load():
    try:
        with open(CACHE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def fast_hash_many(names):
    """{name: FastHash(name)} (names hashed as given, so lower-case them for ids)."""
    cache = _load()
    todo = sorted({n for n in names if n not in cache})
    if todo:
        assert all(n.isascii() and '"' not in n and "'" not in n for n in todo), 'ASCII names only'
        lst = ','.join(f"'{n}'" for n in todo)
        cmd = (f'[void][Reflection.Assembly]::LoadFile("{DLL}"); foreach ($n in @({lst})) '
               '{ "{0}`t{1}" -f $n, [EALA.Hash.FastHash]::GetHashCode($n) }')
        out = subprocess.run([PS32, '-NoProfile', '-Command', cmd], capture_output=True, text=True, check=True).stdout
        for line in out.splitlines():
            if '\t' in line:
                n, h = line.rsplit('\t', 1)
                cache[n] = int(h)
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=0, sort_keys=True)
    return {n: cache[n] for n in names}


def asset_id(name):
    return fast_hash_many([name.lower()])[name.lower()]
