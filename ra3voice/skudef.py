"""Resolve a SAGE SkuDef chain into the ordered list of BIG archives (highest priority first).

A SkuDef lists `add-big` lines and may `add-config` an older SkuDef; files from BIGs listed
earlier win, and everything a newer SkuDef adds comes before what it inherits.
"""
import glob
import os
import re

SKU_RE = re.compile(r'^(?P<prefix>RA3(?:EP1)?)_(?P<lang>[a-z_]+)_(?P<major>\d+)\.(?P<minor>\d+)\.SkuDef$', re.I)


def parse_name(path):
    m = SKU_RE.match(os.path.basename(path))
    if not m:
        return None
    return m['prefix'], m['lang'].lower(), (int(m['major']), int(m['minor']))


def latest_per_lang(game_dir):
    """{lang: (version_tuple, path)} for the newest SkuDef of each language."""
    best = {}
    for p in glob.glob(os.path.join(game_dir, '*.SkuDef')):
        info = parse_name(p)
        if not info:
            continue
        _, lang, ver = info
        if lang not in best or ver > best[lang][0]:
            best[lang] = (ver, p)
    return best


def read_lines(path):
    with open(path, encoding='latin-1') as f:
        return [ln.strip() for ln in f if ln.strip()]


BACKUP_EXT = '.cnvoice-backup'   # written by the installer before it edits a SkuDef


def big_chain(skudef_path, _seen=None, original=False):
    """Ordered BIG paths (absolute) for a SkuDef, highest priority first; missing files are skipped.
    original=True reads the installer's backups, i.e. the chain as shipped, without any line the
    mod added (including non-mod archives such as ChineseT.big added for font substitution)."""
    seen = _seen if _seen is not None else set()
    game_dir = os.path.dirname(skudef_path)
    out = []
    src = skudef_path + BACKUP_EXT if original and os.path.exists(skudef_path + BACKUP_EXT) else skudef_path
    for ln in read_lines(src):
        cmd, _, arg = ln.partition(' ')
        arg = arg.strip()
        if cmd == 'add-big':
            p = os.path.join(game_dir, arg)
            if os.path.exists(p) and p.lower() not in seen:
                seen.add(p.lower())
                out.append(p)
        elif cmd == 'add-config':
            sub = os.path.join(game_dir, arg)
            if os.path.exists(sub):
                out += big_chain(sub, seen, original)
    return out


def set_exe(skudef_path):
    for ln in read_lines(skudef_path):
        if ln.startswith('set-exe '):
            return ln[len('set-exe '):].strip()
    return None
