"""pack_shaders.py <fxo_dir> <out.big>: compiled shaders whose names exist in the game's Shaders.big -> override BIG."""
import os, sys
sys.path.insert(0, r'C:\Users\63097\Desktop\RA3-ChineseVoice')
from ra3voice import big

src, out = sys.argv[1:3]
GAME = r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\Shaders.big'
have = {n.lower(): n for n, o, s in big.read_index(GAME)}
files, skipped = [], []
for f in sorted(os.listdir(src)):
    key = 'shaders\\compiled\\' + f.lower()
    if f.lower().endswith('.fxo') and key in have:
        files.append((key, open(os.path.join(src, f), 'rb').read()))
    else:
        skipped.append(f)
big.write(out, files)
print('packed', [k.split('\\')[-1] for k, _ in files])
print('skipped (no such shader in the game)', skipped)
