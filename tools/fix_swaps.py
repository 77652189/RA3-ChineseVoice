"""Dubs in the wrong voice whose own reference is too thin: borrow the same actor's best reference and redub.

  venv=third_party/index-tts/.venv/Scripts/python.exe
  $venv -I -X utf8 tools/fix_swaps.py find   A1 A2 ...      # proposes ref overrides -> work/voice_audit/swap_plan.json
  (back up, apply the overrides, dub --only, pick --only)
  $venv -I -X utf8 tools/fix_swaps.py verify BACKUP_DIR      # keep each new take only if it fixed the voice

find: in the same movie (or mission group), the reference that sounds most like this line's own (CAMPPlus >= 0.5),
is at least 1.5 s long, has a median pitch within 0.8-1.25x of the line's, and (movies) was verified to hold its
own words (work/voice_audit/ref_text_all.csv). Lines with no such reference are left for a human.
verify: against the line's own reference, the new take must have its pitch in range, be more like the actor, and
read as well as the old one (QC cer); otherwise voices/, clean/ and the QC row are restored from BACKUP_DIR.
"""
import csv
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from speakers import F0_HI, F0_LO, Fingerprint, load_16k, median_f0  # noqa: E402

PLAN = os.path.join(ROOT, 'work', 'voice_audit', 'swap_plan.json')
REF_DIR = {'movie': os.path.join(ROOT, 'original', 'movie_clean'), 'mission': os.path.join(ROOT, 'original', 'mission')}


def batch_of(asset):
    return 'movie' if asset[:2] in ('R_', 'U_') else 'mission'


def lines(batch):
    with open(os.path.join(ROOT, 'lines', batch + '.csv'), encoding='utf-8-sig') as f:
        return {r['asset']: r for r in csv.DictReader(f)}


def find(assets):
    verified = {}
    p = os.path.join(ROOT, 'work', 'voice_audit', 'ref_text_all.csv')
    if os.path.exists(p):
        verified = {r['asset']: float(r['match']) for r in csv.DictReader(open(p, encoding='utf-8-sig'))}
    fp = Fingerprint()
    cache = {}

    def info(batch, a):
        if a not in cache:
            y = load_16k(os.path.join(REF_DIR[batch], a + '.wav'))
            cache[a] = (fp(y), median_f0(y), len(y) / 16000)
        return cache[a]
    plan = {}
    for a in assets:
        b = batch_of(a)
        rows = lines(b)
        key = (lambda r: (r['games'], r['movie'])) if b == 'movie' else (lambda r: r['group'])
        e, f0, _ = info(b, a)
        cands = []
        for c, r in rows.items():
            if c == a or key(r) != key(rows[a]) or not os.path.exists(os.path.join(REF_DIR[b], c + '.wav')):
                continue
            if b == 'movie' and verified.get(c, 0) < 0.8:
                continue
            ec, fc, dc = info(b, c)
            if dc >= 1.5 and f0 and fc and 0.8 <= fc / f0 <= 1.25:
                cands.append((float(ec @ e), c))
        cands.sort(reverse=True)
        best = cands[0] if cands and cands[0][0] >= 0.5 else None
        print(f'{a}: ' + (f'-> {best[1]} ({best[0]:.2f})' if best else 'no same-actor reference found'), flush=True)
        if best:
            plan[a] = best[1]
    json.dump(plan, open(PLAN, 'w', encoding='utf-8'), indent=1)
    print(f'{len(plan)} of {len(assets)} have a replacement reference -> {PLAN}')


def verify(backup):
    plan = json.load(open(PLAN, encoding='utf-8'))
    fp = Fingerprint()
    kept, back = [], []
    for a in plan:
        b = batch_of(a)
        ref = load_16k(os.path.join(REF_DIR[b], a + '.wav'))
        er, fr = fp(ref), median_f0(ref)
        res = {}
        for k, path in (('old', os.path.join(backup, b, 'voices', a + '.wav')), ('new', os.path.join(ROOT, 'clean', b, a + '.wav'))):
            y = load_16k(path)
            res[k] = (float(fp(y) @ er), median_f0(y))
        cer = {}
        for k, path in (('old', os.path.join(backup, b + '_qc.csv')), ('new', os.path.join(ROOT, 'lines', b + '_qc.csv'))):
            cer[k] = next(float(q['cer'] or 0) for q in csv.DictReader(open(path, encoding='utf-8-sig')) if q['asset'] == a)
        in_range = fr <= 0 or res['new'][1] <= 0 or F0_LO <= res['new'][1] / fr <= F0_HI
        good = in_range and res['new'][0] > res['old'][0] and cer['new'] <= max(cer['old'], 0.2)
        print(f"{a}: like actor {res['old'][0]:.2f} -> {res['new'][0]:.2f}, pitch {res['old'][1]:.0f} -> {res['new'][1]:.0f} "
              f"(actor {fr:.0f}), cer {cer['old']:.2f} -> {cer['new']:.2f}: {'KEEP' if good else 'back to old'}")
        (kept if good else back).append(a)
    for a in back:
        b = batch_of(a)
        for d in ('voices', 'clean'):
            shutil.copy2(os.path.join(backup, b, 'voices' if d == 'voices' else 'clean', a + '.wav'), os.path.join(ROOT, d, b, a + '.wav'))
        qc_path = os.path.join(ROOT, 'lines', b + '_qc.csv')
        old = {q['asset']: q for q in csv.DictReader(open(os.path.join(backup, b + '_qc.csv'), encoding='utf-8-sig'))}
        qc = [old[q['asset']] if q['asset'] == a else q for q in csv.DictReader(open(qc_path, encoding='utf-8-sig'))]
        with open(qc_path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=list(qc[0].keys()))
            w.writeheader()
            w.writerows(qc)
    json.dump({'kept': kept, 'back': back}, open(os.path.join(ROOT, 'work', 'voice_audit', 'swap_result.json'), 'w'), indent=1)
    print(f'kept {len(kept)}, restored {len(back)}')


if __name__ == '__main__':
    {'find': lambda: find(sys.argv[2:]), 'verify': lambda: verify(sys.argv[2])}[sys.argv[1]]()
