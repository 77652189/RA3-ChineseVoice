"""After a movie redub with new references: keep each line's new take only if it is at least as much the actor.

  third_party/index-tts/.venv/Scripts/python -I -X utf8 tools/keep_better.py TARGETS.json BACKUP_DIR
  BACKUP_DIR holds voices/, clean/ and movie_qc.csv from before the redub.

Per line, against the actor's own reference (original/movie_clean, cut from the measured onset): CAMPPlus
similarity and median pitch of the old dub and of the new one. The new take stays when it is not less like
the actor (within SLACK) and its pitch is in range, or when the old pitch was off (wrong voice) and the new is
not. Otherwise the old voice, clean file and QC row come back. Writes work/voice_audit/keep_better.csv.
"""
import csv
import json
import os
import shutil
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from speakers import F0_HI, F0_LO, Fingerprint, load_16k, median_f0  # noqa: E402

SLACK = 0.02


def main(targets_path, backup):
    targets = json.load(open(targets_path, encoding='utf-8'))
    fp = Fingerprint()
    report, reverted = [], []
    for a in targets:
        ref = os.path.join(ROOT, 'original', 'movie_clean', a + '.wav')
        old = os.path.join(backup, 'voices', a + '.wav')
        new = os.path.join(ROOT, 'clean', 'movie', a + '.wav')
        if not (os.path.exists(ref) and os.path.exists(old) and os.path.exists(new)):
            continue
        r, o, n = load_16k(ref), load_16k(old), load_16k(new)
        er = fp(r)
        so, sn = float(fp(o) @ er), float(fp(n) @ er)
        f0r, f0o, f0n = median_f0(r), median_f0(o), median_f0(n)
        ok = lambda f: not (f0r > 0 and f > 0) or F0_LO <= f / f0r <= F0_HI   # noqa: E731
        keep_new = (sn >= so - SLACK and ok(f0n)) or (not ok(f0o) and ok(f0n))
        if not keep_new:
            reverted.append(a)
        report.append({'asset': a, 'old_sim': round(so, 3), 'new_sim': round(sn, 3), 'ref_f0': round(f0r),
                       'old_f0': round(f0o), 'new_f0': round(f0n), 'kept': 'new' if keep_new else 'old'})
    for a in reverted:
        shutil.copy2(os.path.join(backup, 'voices', a + '.wav'), os.path.join(ROOT, 'voices', 'movie', a + '.wav'))
        shutil.copy2(os.path.join(backup, 'clean', a + '.wav'), os.path.join(ROOT, 'clean', 'movie', a + '.wav'))
    if reverted:   # their QC rows too
        old_qc = {q['asset']: q for q in csv.DictReader(open(os.path.join(backup, 'movie_qc.csv'), encoding='utf-8-sig'))}
        qc_path = os.path.join(ROOT, 'lines', 'movie_qc.csv')
        qc = list(csv.DictReader(open(qc_path, encoding='utf-8-sig')))
        qc = [old_qc.get(q['asset'], q) if q['asset'] in reverted else q for q in qc]
        with open(qc_path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=list(qc[0].keys()))
            w.writeheader()
            w.writerows(qc)
    os.makedirs(os.path.join(ROOT, 'work', 'voice_audit'), exist_ok=True)
    with open(os.path.join(ROOT, 'work', 'voice_audit', 'keep_better.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(report[0].keys()))
        w.writeheader()
        w.writerows(report)
    kept = [x for x in report if x['kept'] == 'new']
    print(f'{len(report)} lines: new kept {len(kept)}, old restored {len(reverted)}; '
          f'median similarity old {np.median([x["old_sim"] for x in report]):.2f} -> '
          f'final {np.median([x["new_sim"] if x["kept"] == "new" else x["old_sim"] for x in report]):.2f}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
