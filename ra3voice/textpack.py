"""Simplified-Chinese text component: string tables converted from the official Traditional Chinese
release (Taiwan phrasing -> mainland phrasing via OpenCC tw2sp) plus fonts that contain simplified
characters.

Two layers on top of the plain conversion, so what players read matches what they hear:
  - terms: unit / building / power names follow the dubbing glossary (work/terms/term_map.json:
    "global" pairs are substring replacements applied longest first, "exact" pairs only replace a
    whole string);
  - subtitles: DIALOGEVENT:<asset> (mission dialogue) and SUBTITLE:<movie>[_NN] (movies) are replaced
    by the dub scripts. Movie subtitles use the English timing tags, which is what the dubs were
    placed on (the official Chinese tags are often about a second late).
"""
import json
import os
import re
from functools import lru_cache

from . import csf, refpack

FONT_FILES = ('bhei00m.ttf', 'bhei01b.ttf')
SEG_RE = re.compile(r'\[\s*(\d+(?:\.\d+)?)\s*:\s*-?\d+(?:\.\d+)?\s*\]')


@lru_cache(maxsize=1)
def _converter():
    from opencc import OpenCC
    return OpenCC('tw2sp')


def to_simplified(text):
    return _converter().convert(text)


class Terms:
    def __init__(self, path=None):
        self.globals, self.exact = [], {}
        if path and os.path.exists(path):
            for t in json.load(open(path, encoding='utf-8')):
                if t['scope'] == 'global':
                    self.globals.append((t['from'], t['to']))
                else:
                    self.exact[t['from']] = t['to']
        self.globals.sort(key=lambda p: -len(p[0]))
        # one pass, longest match first, so a replacement is never replaced again
        self._re = re.compile('|'.join(re.escape(a) for a, _ in self.globals)) if self.globals else None
        self._map = dict(self.globals)

    def apply(self, text):
        if text.strip() in self.exact:
            return text.replace(text.strip(), self.exact[text.strip()])
        return self._re.sub(lambda m: self._map[m.group(0)], text) if self._re else text


def subtitle_overrides(en_entries, mission_rows, movie_rows):
    """{label: text} for DIALOGEVENT/SUBTITLE labels from the dub scripts of one game.
    en_entries: {label: English text} of the same string table (for movie timing tags)."""
    out = {}
    dub = {r['asset'].upper(): r['zh'] for r in mission_rows if r['zh'].strip()}
    seg = {}
    for r in movie_rows:
        text = r['zh'].strip() or r.get('zh_official', '').strip()
        if text:
            seg.setdefault(r['movie'].upper(), []).append((float(r['start']), text))
    for label, en in en_entries.items():
        up = label.upper()
        if up.startswith('DIALOGEVENT:'):
            z = dub.get(up[len('DIALOGEVENT:'):])
            if z:
                out[label] = z
        elif up.startswith('SUBTITLE:'):
            movie = re.sub(r'_\d+$', '', up[len('SUBTITLE:'):])
            lines = seg.get(movie)
            tags = list(SEG_RE.finditer(en))
            if not lines or not tags:
                continue
            parts = []
            for m in tags:
                s = float(m.group(1))
                hit = next((t for st, t in lines if abs(st - s) < 0.011), None)
                if hit is None:
                    parts = None
                    break
                parts.append(m.group(0) + hit)
            if parts:
                out[label] = ''.join(parts)
    return out


def convert_csf(data, terms=None, overrides=None):
    """Traditional .csf bytes (RefPack or raw) -> simplified .csf bytes (raw), same labels and order."""
    header, entries = csf.parse_full(data)
    terms, overrides = terms or Terms(), overrides or {}
    return csf.write(header, [(n, overrides[n] if n in overrides else terms.apply(to_simplified(t)), ex, k)
                              for n, t, ex, k in entries])


def text_files(chain, font_dir, terms=None, en_chain=None, mission_rows=(), movie_rows=(), extra=None):
    """[(path, bytes)] for CNVoice_text.big: every string table of the chinese_t chain, simplified,
    plus the replacement fonts. Files are RefPack-wrapped like the originals.
    extra: {label: zh} for strings the official release left in English (used only where it still is)."""
    files = []
    for name in sorted(n for n in chain.where if n.endswith('.csf')):
        overrides = {}
        if extra:
            official = csf.parse(chain.read([name])[name])
            overrides.update({k: v for k, v in extra.items()
                              if k in official and not re.search(r'[一-鿿]', official[k])})
        if en_chain is not None and name in en_chain.where:
            overrides.update(subtitle_overrides(csf.parse(en_chain.read([name])[name]), mission_rows, movie_rows))
        files.append((name, refpack.compress_literal(convert_csf(chain.read([name])[name], terms, overrides))))
    for f in FONT_FILES:
        with open(os.path.join(font_dir, f), 'rb') as fh:
            files.append(('data\\fonts\\' + f, refpack.compress_literal(fh.read())))
    return files
