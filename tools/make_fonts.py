"""Build drop-in replacements for the game's Big5-only Chinese fonts (bhei00m / bhei01b).

  python tools/make_fonts.py

The game ships AR Heiti B5, which lacks ~700 simplified characters. We take Noto Sans SC (SIL OFL,
third_party/fonts/NotoSansSC-VF.ttf), pin a static weight per font, subset it to what the game can
show (all characters in the simplified and traditional string tables of both games, GB2312, Big5
level 1, ASCII and punctuation, plus everything the original font covered), and copy the original
font's names and vertical metrics so the game's FontSubstitution entries keep resolving to it.
Output: third_party/fonts/out/bhei00m.ttf, bhei01b.ttf
"""
import io
import os
import sys

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import big, csf, refpack, textpack           # noqa: E402
from ra3voice.game import chain_for_game                     # noqa: E402

SRC = os.path.join(ROOT, 'third_party', 'fonts', 'NotoSansSC-VF.ttf')
OUT = os.path.join(ROOT, 'third_party', 'fonts', 'out')
GAMES = {
    'ra3': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3',
    'uprising': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3 Uprising',
}
FONTS = {'bhei00m.ttf': 500, 'bhei01b.ttf': 700}   # AR Heiti2 Medium B5 / AR Heiti Bold B5


def charset(code, ranges):
    out = set()
    for hi in range(ranges[0][0], ranges[0][1] + 1):
        for lo in range(ranges[1][0], ranges[1][1] + 1):
            try:
                out.update(bytes((hi, lo)).decode(code))
            except UnicodeDecodeError:
                pass
    return out


def wanted_chars(original_cmaps):
    chars = set(chr(c) for c in range(0x20, 0x7F)) | set('，。！？、；：“”‘’（）《》【】…—～·「」『』')
    chars |= charset('gb2312', ((0xB0, 0xF7), (0xA1, 0xFE)))   # GB2312 hanzi
    chars |= charset('big5', ((0xA4, 0xC6), (0x40, 0xFE)))     # Big5 level 1
    for d in GAMES.values():
        chain = chain_for_game(d, 'chinese_t')
        for n in [k for k in chain.where if k.endswith('.csf')]:
            for t in csf.parse(chain.read([n])[n]).values():
                chars |= set(t) | set(textpack.to_simplified(t))
    for cmap in original_cmaps:
        chars |= {chr(c) for c in cmap}
    # everything the text component may now show instead: dub scripts (subtitles), glossary terms, UI fills
    import csv
    import glob
    import json
    for p in glob.glob(os.path.join(ROOT, 'lines', '*.csv')):
        with open(p, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                chars |= set(r.get('zh', '') or '')
    for p, key in ((os.path.join(ROOT, 'work', 'terms', 'term_map.json'), 'to'),
                   (os.path.join(ROOT, 'work', 'terms', 'untranslated_zh.json'), None)):
        if os.path.exists(p):
            d = json.load(open(p, encoding='utf-8'))
            chars |= set(''.join(t[key] for t in d) if key else ''.join(d.values()))
    return {c for c in chars if not 0xD800 <= ord(c) <= 0xDFFF}


IDENTITY_IDS = (1, 2, 3, 4, 5, 6)      # family / style / unique / full / version / PostScript name
CREDIT_IDS = (0, 7, 8, 13, 14)         # copyright, trademark, vendor, license (kept from Noto, per OFL)


def adopt_identity(font, original):
    """Make the font answer to the original's names (all platforms and languages, so the game's
    font substitution resolves to it) and present itself the same way (regular style, same
    ascent/descent ratio, so text boxes keep their layout), while keeping Noto's credits."""
    ours, theirs = font['name'], original['name']
    credits = [r for r in ours.names if r.nameID in CREDIT_IDS]
    ours.names = [r for r in theirs.names if r.nameID in IDENTITY_IDS] + credits
    os2 = font['OS/2']
    os2.usWeightClass = 400
    os2.fsSelection = (os2.fsSelection & ~0b1100001) | 0b1000000     # REGULAR, not BOLD/ITALIC
    font['head'].macStyle = 0
    upm = font['head'].unitsPerEm
    o_upm = original['head'].unitsPerEm
    asc = round(original['hhea'].ascent * upm / o_upm)
    desc = round(-original['hhea'].descent * upm / o_upm)
    font['hhea'].ascent, font['hhea'].descent, font['hhea'].lineGap = asc, -desc, 0
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = asc, -desc, 0
    os2.usWinAscent, os2.usWinDescent = asc, desc


def main():
    os.makedirs(OUT, exist_ok=True)
    pack = os.path.join(GAMES['ra3'], 'Data', 'ChineseT.big')
    names = {f: 'data\\fonts\\' + f for f in FONTS}
    originals = {f: TTFont(io.BytesIO(refpack.decompress(b))) for f, b in
                 ((f, big.read_files(pack, [names[f]])[names[f]]) for f in FONTS)}
    chars = wanted_chars([o.getBestCmap() for o in originals.values()])
    for fname, weight in FONTS.items():
        font = instancer.instantiateVariableFont(TTFont(SRC), {'wght': weight})
        opts = subset.Options()
        opts.layout_features = ['*']
        opts.name_IDs = ['*']
        opts.notdef_outline = True
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=[ord(c) for c in chars])
        sub.subset(font)
        adopt_identity(font, originals[fname])
        out = os.path.join(OUT, fname)
        font.save(out)
        cmap = TTFont(out).getBestCmap()
        print(f'{fname}: weight {weight}, {len(cmap)} glyphs, {os.path.getsize(out) / 1e6:.1f} MB, '
              f'family "{TTFont(out)["name"].getDebugName(1)}"')


if __name__ == '__main__':
    main()
