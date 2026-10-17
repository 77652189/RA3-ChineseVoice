"""Find polyphones the dub may have read wrong: every polyphonic character in the released lines, its reading in
context (pypinyin's phrase dictionary) and what Whisper heard at that spot in the released take (qc csv 'heard').

  python -I -X utf8 tools/polyphone_audit.py      -> work/polyphone/occurrences.csv, work/polyphone/groups.csv

A spot is suspect when Whisper heard a syllable other than the context reading (e.g. 中弹 heard as 中谈: dan vs tan).
Tone-only slips (wei2 / wei4) are invisible to Whisper; groups.csv lists them by how far the context reading is
from the character's everyday one, for a person to judge.
"""
import csv
import difflib
import os
from collections import defaultdict

from pypinyin import Style, lazy_pinyin, pinyin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'work', 'polyphone')
BATCHES = ['allied', 'soviet', 'empire', 'eva', 'commander', 'mission', 'movie']


def readings(ch):
    """Distinct toned readings of one character (pypinyin heteronyms), most common first."""
    return list(dict.fromkeys(pinyin(ch, style=Style.TONE3, heteronym=True, neutral_tone_with_five=True)[0]))


def han(s):
    return [c for c in s if '一' <= c <= '鿿']


def toneless(r):
    return r.rstrip('012345')


def main():
    os.makedirs(OUT, exist_ok=True)
    occ = []
    for batch in BATCHES:
        qc = os.path.join(ROOT, 'lines', batch + '_qc.csv')
        if not os.path.exists(qc):
            continue
        for r in csv.DictReader(open(qc, encoding='utf-8-sig')):
            if not os.path.exists(os.path.join(ROOT, 'voices', batch, r['asset'] + '.wav')):
                continue          # not shipped (kept English, silent, ...)
            text, heard = han(r['zh']), han(r['heard'])
            if not text:
                continue
            want = lazy_pinyin(''.join(text), style=Style.TONE3, neutral_tone_with_five=True)
            got = lazy_pinyin(''.join(heard), style=Style.TONE3, neutral_tone_with_five=True) if heard else []
            # align on toneless syllables, so a heard homophone counts as a match
            sm = difflib.SequenceMatcher(None, [toneless(x) for x in want], [toneless(x) for x in got], autojunk=False)
            heard_at = {}
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == 'equal' or (tag == 'replace' and i2 - i1 == j2 - j1):
                    for k in range(i2 - i1):
                        heard_at[i1 + k] = (heard[j1 + k], got[j1 + k])
            for i, ch in enumerate(text):
                opts = readings(ch)
                if len({toneless(o) for o in opts}) < 2 and len(opts) < 2:
                    continue
                h = heard_at.get(i)
                occ.append({
                    'batch': batch, 'asset': r['asset'], 'char': ch, 'context': ''.join(text[max(0, i - 2):i + 3]),
                    'reading': want[i], 'everyday': opts[0], 'all': '/'.join(opts),
                    'heard_char': h[0] if h else '', 'heard': h[1] if h else '',
                    'suspect': int(bool(h) and toneless(h[1]) != toneless(want[i])),
                    'zh': r['zh'], 'heard_text': r['heard']})
    with open(os.path.join(OUT, 'occurrences.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(occ[0]))
        w.writeheader()
        w.writerows(occ)
    groups = defaultdict(list)
    for o in occ:
        groups[(o['char'], o['reading'])].append(o)
    rows = []
    for (ch, rd), os_ in groups.items():
        sus = [o for o in os_ if o['suspect']]
        rows.append({'char': ch, 'reading': rd, 'everyday': os_[0]['everyday'], 'all': os_[0]['all'],
                     'n': len(os_), 'suspect': len(sus), 'not_everyday': int(toneless(rd) != toneless(os_[0]['everyday'])),
                     'heard_as': ' '.join(sorted({o['heard_char'] for o in sus})),
                     'examples': ' | '.join(dict.fromkeys(o['context'] for o in (sus or os_)))[:200]})
    rows.sort(key=lambda r: (-r['suspect'], -r['not_everyday'], -r['n']))
    with open(os.path.join(OUT, 'groups.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = {(o['batch'], o['asset']) for o in occ}
    sus_lines = {(o['batch'], o['asset']) for o in occ if o['suspect']}
    print(f'{len(occ)} polyphone spots in {len(lines)} lines; {sum(o["suspect"] for o in occ)} suspect spots in {len(sus_lines)} lines; '
          f'{len(rows)} (char, reading) groups -> {OUT}')


if __name__ == '__main__':
    main()
