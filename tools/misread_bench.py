"""Misreading benchmark from lines a person has already judged: each row is one polyphone spot in one recording,
with the reading it should have, the wrong reading it may have, and whether the recording actually says the wrong
one (1) or not (0). A judge (tools/qa_audiollm.py) is scored against it.

  python -I -X utf8 tools/misread_bench.py   -> work/qa/misread_bench.csv

Misread (1): the takes replaced in the polyphone fix (archive/polyphone_redub, user-confirmed: 戛纳 ga, 海参崴 wai,
落 lao, 重 chong, 朝 zhao, 模 mo) and the 弹 tan takes players reported (维和步兵, 世纪轰炸机; archive/dan4_redub).
Read right (0): the same lines as released now, and the polyphone candidates the user heard and passed.
"""
import csv
import os

from pypinyin import Style, pinyin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'work', 'qa', 'misread_bench.csv')
# asset: (batch, char, right, wrong)
FIXED = {
    'MA02_AlliedIntel01': ('mission', '戛', 'jia2', 'ga1'), 'MA02_AlliedIntel32': ('mission', '戛', 'jia2', 'ga1'),
    'MA02_Spy16': ('mission', '戛', 'jia2', 'ga1'), 'R_a02th07_02': ('movie', '戛', 'jia2', 'ga1'),
    'MI03_ImperialIntel42': ('mission', '崴', 'wei1', 'wai3'), 'MS03_CoZhan02': ('mission', '崴', 'wei1', 'wai3'),
    'MS03_SovietIntel01': ('mission', '崴', 'wei1', 'wai3'), 'R_sfs03_06': ('movie', '崴', 'wei1', 'wai3'),
    'R_smb03_01': ('movie', '崴', 'wei1', 'wai3'), 'U_jfs03_04': ('movie', '崴', 'wei1', 'wai3'),
    'U_jfs04_02': ('movie', '崴', 'wei1', 'wai3'),
    'SUNatas_VoiSele': ('soviet', '落', 'luo4', 'lao4'), 'SUNatas_VoiSelecte': ('soviet', '落', 'luo4', 'lao4'),
    'SUReape_voiAttSpeca': ('soviet', '落', 'luo4', 'lao4'), 'AUMirag_VoiSelUndFira': ('allied', '重', 'zhong4', 'chong2'),
    'MSIn_Desolator1': ('mission', '朝', 'chao2', 'zhao1'),
}
DAN = {'AUPeace_VoiSelUndFirb': 'allied', 'AUCentu_VoiSelUndc': 'allied'}
CONFIRMED = set(FIXED) | {'U_yth03sh04_04', 'R_afs02_18'}   # R_afs02_18's old take is unclear (heard 加拿): left out


def zh_of(batch):
    return {r['asset']: r['zh'] for r in csv.DictReader(open(os.path.join(ROOT, 'lines', batch + '.csv'), encoding='utf-8-sig'))}


def main():
    rows = []
    texts = {}
    for asset, (batch, ch, right, wrong) in FIXED.items():
        texts.setdefault(batch, zh_of(batch))
        zh = texts[batch][asset]
        rows.append(dict(asset=asset, version='old', path=f'archive/polyphone_redub/{batch}/clean/{asset}.wav', zh=zh,
                         char=ch, right=right, wrong=wrong, misread=1))
        rows.append(dict(asset=asset, version='now', path=f'voices/{batch}/{asset}.wav', zh=zh, char=ch, right=right,
                         wrong=wrong, misread=0))
    for asset, batch in DAN.items():
        texts.setdefault(batch, zh_of(batch))
        zh = texts[batch][asset]
        rows.append(dict(asset=asset, version='old', path=f'archive/dan4_redub/{batch}/voices/{asset}.wav', zh=zh,
                         char='弹', right='dan4', wrong='tan2', misread=1))
        rows.append(dict(asset=asset, version='now', path=f'voices/{batch}/{asset}.wav', zh=zh, char='弹', right='dan4',
                         wrong='tan2', misread=0))
    # the other polyphone candidates the user heard and passed; their wrong reading = the one the scorer suspected
    scores = {}
    for r in csv.DictReader(open(os.path.join(ROOT, 'work', 'polyphone', 'scores.csv'), encoding='utf-8-sig')):
        scores.setdefault((r['asset'], r['char']), r)
    for r in csv.DictReader(open(os.path.join(ROOT, 'work', 'polyphone', 'candidates.csv'), encoding='utf-8-sig')):
        if r['asset'] in CONFIRMED:
            continue
        texts.setdefault(r['batch'], zh_of(r['batch']))
        ch, right = r['force'].split()[0].split('=')
        s = scores.get((r['asset'], ch))
        if not s:
            continue
        other = s['best'] if s['best'] != s['reading'] else None
        opts = [p for p in pinyin(ch, style=Style.TONE3, heteronym=True)[0] if p.rstrip('12345') != right.lower().rstrip('12345')]
        wrong = next((p for p in opts if other and p.rstrip('12345') == other), opts[0] if opts else None)
        if not wrong:
            continue
        rows.append(dict(asset=r['asset'], version='now', path=f"voices/{r['batch']}/{r['asset']}.wav",
                         zh=texts[r['batch']][r['asset']], char=ch, right=right.lower(), wrong=wrong, misread=0))
    with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(OUT, len(rows), 'rows,', sum(r['misread'] for r in rows), 'misread')


if __name__ == '__main__':
    main()
