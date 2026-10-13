"""Access a game's audio asset stream through its BIG chain and build the override archive."""
import os
import struct
import numpy as np
from . import big, manifest, refpack, snr, skudef

# AudioFile instance layout (offsets inside its instance data)
AF_NUM_SAMPLES = 12
AF_SAMPLE_RATE = 16
AF_CHANNELS = 28
STREAM_BLOCK_SAMPLES = 1024   # originals use 1152-sample EALayer3 blocks; XAS needs multiples of 128
AF_HEADER_PTR = 20   # streamed files (mission dialogue): offset + length of an SNR header kept in the .bin
AF_HEADER_LEN = 24


def _unpack(d):
    return refpack.decompress(d) if refpack.is_refpack(d) else d


class BigChain:
    """Files looked up across BIG archives, first archive wins (like the game's file system)."""

    def __init__(self, bigs):
        self.bigs = list(bigs)
        self.where = {}
        for b in reversed(self.bigs):
            for n, _, _ in big.read_index(b):
                self.where[n.lower()] = b

    def has(self, name):
        return name.lower() in self.where

    def read(self, names):
        by_big = {}
        for n in names:
            by_big.setdefault(self.where[n.lower()], []).append(n)
        out = {}
        for b, ns in by_big.items():
            out.update(big.read_files(b, ns))
        return out


MOD_PREFIXES = ('cnvoice', 'chinesevoice')   # every archive this mod has ever installed


def is_mod_big(path):
    return os.path.basename(path).lower().startswith(MOD_PREFIXES)


def chain_for_game(game_dir, lang=None):
    """BIG chain of the game's newest SkuDef (preferring `lang`) with all of this mod's archives
    removed, so reads always see the original game data even while the mod is installed.
    The SkuDef files may contain our add-big lines; they are skipped here too."""
    best = skudef.latest_per_lang(game_dir)
    lang = lang if lang in best else ('english' if 'english' in best else next(iter(best)))
    bigs = [b for b in skudef.big_chain(best[lang][1], original=True) if not is_mod_big(b)]
    return BigChain(bigs)


class AudioStream:
    """One asset stream (e.g. data\\audio.manifest + .bin + data\\audio\\cdata\\*)."""

    def __init__(self, source, stream='audio'):
        self.chain = source if isinstance(source, BigChain) else BigChain([os.path.join(source, 'EnglishAudio.big')])
        self.stream = stream
        self.bin_name = f'data\\{stream}.bin'
        files = self.chain.read([f'data\\{stream}.manifest', self.bin_name])
        self.bin = bytearray(_unpack(files[self.bin_name]))
        self.assets = manifest.parse(_unpack(files[f'data\\{stream}.manifest']))
        if stream != 'audio':
            for a in self.assets:
                a.stream = stream
        self.by_name = {a.short_name.lower(): a for a in self.assets}

    def find(self, pattern):
        p = pattern.lower()
        return [a for a in self.assets if p in a.short_name.lower()]

    def get(self, short_name):
        return self.by_name[short_name.lower()]

    def read_cdata(self, assets):
        files = self.chain.read([a.cdata_path for a in assets])
        return {a.short_name: files[a.cdata_path] for a in assets}

    def num_samples(self, asset):
        return struct.unpack_from('<I', self.bin, asset.bin_offset + AF_NUM_SAMPLES)[0]

    def header_in_bin(self, asset):
        """Absolute .bin offset of the 8-byte SNR header for streamed AudioFiles, else None.

        Unit voices carry their SNR header at the start of the cdata (these words are 0). Mission
        dialogue (EALayer3) keeps it inside the AudioFile instance instead and the cdata holds only
        SNS blocks."""
        off, ln = struct.unpack_from('<II', self.bin, asset.bin_offset + AF_HEADER_PTR)
        return asset.bin_offset + off if ln == 8 and off else None

    def decode(self, asset, blob=None):
        """Original audio of any AudioFile -> (int16 mono array, sample_rate). XAS clips are decoded
        here; streamed EALayer3 clips go through vgmstream (bin header + decompressed SNS blocks)."""
        from . import vgm
        blob = self.read_cdata([asset])[asset.short_name] if blob is None else blob
        hp = self.header_in_bin(asset)
        if hp is None:
            return snr.decode(blob)
        sns = refpack.decompress(blob) if refpack.is_refpack(blob) else blob
        x, sr = vgm.decode_snr_sns(bytes(self.bin[hp:hp + 8]), sns)
        return vgm.to_mono(x), sr

    def decode_replacement(self, asset, blob):
        """One of our cdata_files blobs -> (int16 mono, sample_rate). Streamed clips carry no header
        (it lives in our patched audio.bin), so rebuild the XAS header from the asset's layout."""
        if self.header_in_bin(asset) is None:
            return snr.decode(blob)
        sns = refpack.decompress(blob)
        n, p = 0, 0
        while p < len(sns):
            n += struct.unpack_from('>I', sns, p + 4)[0]
            p += int.from_bytes(sns[p + 1:p + 4], 'big')
        sr, ch = self._layout(asset)
        header = struct.pack('>II', (snr.CODEC_XAS1 << 24) | ((ch - 1) << 18) | sr, n)
        return snr.decode(header + sns)

    def _layout(self, a):
        sr = struct.unpack_from('<I', self.bin, a.bin_offset + AF_SAMPLE_RATE)[0]
        ch = struct.unpack_from('<I', self.bin, a.bin_offset + AF_CHANNELS)[0]
        return sr, ch

    def cdata_files(self, replacements):
        """{short_name: int16 mono array} -> [(cdata path, blob)], XAS-encoded with the asset's rate/channels.
        Streamed AudioFiles get header-less SNS blocks (their header lives in the .bin, see bin_file),
        cut into small blocks and RefPack-wrapped like the originals (the engine decompresses them)."""
        files = []
        for name, pcm in sorted(replacements.items()):
            a = self.get(name)
            sr, ch = self._layout(a)
            pcm = np.asarray(pcm, dtype=np.int16)
            if self.header_in_bin(a) is None:
                files.append((a.cdata_path, snr.build(pcm, sr, ch)))
            else:
                blob = snr.build(pcm, sr, ch, block_samples=STREAM_BLOCK_SAMPLES)[8:]
                files.append((a.cdata_path, refpack.compress_literal(blob)))
        return files

    def bin_file(self, lengths):
        """{short_name: sample count} -> (bin path, RefPack blob) with those AudioFiles' sample counts patched.

        Every AudioFile whose cdata is replaced must get its new count here, and no other: the
        engine trusts this count when it streams the clip."""
        new_bin = bytearray(self.bin)
        for name, n in lengths.items():
            a = self.get(name)
            struct.pack_into('<I', new_bin, a.bin_offset + AF_NUM_SAMPLES, int(n))
            hp = self.header_in_bin(a)
            if hp is not None:
                # rewrite the in-bin SNR header: same flags, now XAS with the new length
                sr, ch = self._layout(a)
                flags = struct.unpack_from('>I', self.bin, hp + 4)[0] >> 30
                struct.pack_into('>II', new_bin, hp, (snr.CODEC_XAS1 << 24) | ((ch - 1) << 18) | sr,
                                 (flags << 30) | int(n))
        return self.bin_name, refpack.compress_literal(bytes(new_bin))

    def override_files(self, replacements):
        """replacements: {short_name: int16 mono numpy array at the asset's sample rate}.

        Returns [(path, bytes)]: the patched .bin (sample counts) and the new cdata files.
        Asset names and hashes are untouched, so the original manifest keeps resolving them.
        """
        return [self.bin_file({n: len(p) for n, p in replacements.items()})] + self.cdata_files(replacements)

    def build_override(self, out_big, replacements):
        files = self.override_files(replacements)
        big.write(out_big, files)
        return len(files) - 1
