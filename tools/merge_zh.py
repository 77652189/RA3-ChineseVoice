"""Merge translations from lines/<batch>_zh*.json into lines/<batch>.csv and lint them.

  python tools/merge_zh.py allied [soviet ...]

JSON format: {"<asset>": {"zh": "...", "note": "..."}} (or {"<asset>": "..."}).
Existing zh is overwritten only for assets present in the JSON. Lint warnings are printed:
Latin letters / digits in zh, and lines much longer than the original clip.
"""
import csv
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUNCT = re.compile(r'[\s，。！？、,.!?;；:：“”"\'‘’…\-—]')


def lint(row):
    zh, warn = row['zh'], []
    if re.search(r'[A-Za-z0-9]', zh):
        warn.append('含英文或数字')
    n = len(PUNCT.sub('', zh))
    sec = float(row['seconds'] or 0)
    if zh and n > sec * 6 + 2:
        warn.append(f'偏长 {n} 字 / {sec:.2f}s')
    return warn


def merge(batch):
    path = os.path.join(ROOT, 'lines', f'{batch}.csv')
    with open(path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    data = {}
    for jpath in sorted(glob.glob(os.path.join(ROOT, 'lines', f'{batch}_zh*.json'))):
        data.update(json.load(open(jpath, encoding='utf-8')))
    by = {r['asset'].lower(): r for r in rows}
    unknown = [k for k in data if k.lower() not in by]
    for k, v in data.items():
        r = by.get(k.lower())
        if not r:
            continue
        if isinstance(v, str):
            v = {'zh': v}
        r['zh'] = (v.get('zh') or '').strip()
        if v.get('note'):
            r['note'] = v['note'].strip()
    missing = [r['asset'] for r in rows if r['asset'].lower() not in {k.lower() for k in data} and not r['zh']]
    warns = [(r['asset'], w) for r in rows for w in lint(r)]
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    filled = sum(1 for r in rows if r['zh'])
    print(f'{batch}: {filled}/{len(rows)} with zh, {len(rows) - filled} left original; '
          f'unknown keys {len(unknown)}, untranslated {len(missing)}, lint {len(warns)}')
    for a, w in warns[:40]:
        print('  lint', a, w)
    if unknown:
        print('  unknown:', unknown[:10])
    if missing:
        print('  untranslated:', missing[:10])
    return not unknown and not missing


if __name__ == '__main__':
    ok = all([merge(b) for b in sys.argv[1:]])
    sys.exit(0 if ok else 1)
