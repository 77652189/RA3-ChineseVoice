"""Player's-eye check: do the dubbed lines call units / buildings / powers what the UI calls them?

  python tools/audit_names.py        -> work/terms/name_audit.json + summary

For every NAME: string (English name -> our simplified UI name), find dub-script lines (mission, movie,
unit voices, EVA, commander) whose English mentions that name, and report the ones whose Chinese does not
contain the UI name. Those are spots where a player hears one name and reads another.
"""
import csv
import json
import os
import re
import sys
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import csf, refpack                      # noqa: E402
from ra3voice.game import chain_for_game              # noqa: E402

BATCHES = ['mission', 'movie', 'allied', 'soviet', 'empire', 'eva', 'commander']
GENERIC = {'commander', 'general', 'premier', 'emperor', 'engineer', 'spy', 'mcv', 'ore', 'power', 'reactor',
           'barracks', 'refinery', 'airfield', 'harbor', 'harbour', 'dojo', 'docks', 'tower', 'wall', 'bunker'}


def main():
    spec = importlib.util.spec_from_file_location('ra3cv', os.path.join(ROOT, 'ra3cv.py'))
    ra3cv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ra3cv)
    names = {}
    for g in ra3cv.GAMES:
        en = csf.parse(chain_for_game(ra3cv.GAMES[g], 'english').read(['data\\gamestrings.csf'])['data\\gamestrings.csf'])
        ui = dict((n, b) for n, b in ra3cv._build_text(g))['data\\gamestrings.csf']
        ui = csf.parse(refpack.decompress(ui))
        for k, v in en.items():
            if not k.upper().startswith('NAME:') or k not in ui:
                continue
            e = v.strip().lstrip('*').strip()
            z = ui[k].strip()
            if (len(e) < 4 or e.lower() in GENERIC or not re.search(r'[A-Za-z]', e) or ' ' not in e and not e[0].isupper()
                    or not re.search(r'[一-鿿]', z) or len(z) > 12):
                continue
            names.setdefault(e.lower(), {'en': e, 'ui': set()})['ui'].add(z)
    rows = []
    for b in BATCHES:
        p = os.path.join(ROOT, 'lines', b + '.csv')
        with open(p, encoding='utf-8-sig') as f:
            rows += [(b, r) for r in csv.DictReader(f) if r.get('zh', '').strip()]
    report = []
    for key, n in sorted(names.items()):
        pat = re.compile(r'\b' + re.escape(n['en']) + r's?\b', re.I)
        hits = [(b, r) for b, r in rows if pat.search(r['en'])]
        if not hits:
            continue
        bad = [(b, r) for b, r in hits if not any(u in r['zh'] for u in n['ui'])]
        if bad:
            report.append({'en': n['en'], 'ui': sorted(n['ui']), 'lines': len(hits), 'mismatch': len(bad),
                           'examples': [{'batch': b, 'asset': r['asset'], 'en': r['en'][:120], 'zh': r['zh'][:80]} for b, r in bad]})
    report.sort(key=lambda x: -x['mismatch'])
    json.dump(report, open(os.path.join(ROOT, 'work', 'terms', 'name_audit.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(names)} names checked, {len(report)} with mismatching dub lines, '
          f'{sum(x["mismatch"] for x in report)} lines')
    for x in report[:40]:
        print(f"  {x['en']:28s} UI={'/'.join(x['ui']):14s} {x['mismatch']}/{x['lines']}  e.g. {x['examples'][0]['zh'][:30]}")


if __name__ == '__main__':
    main()
