"""Unattended per-batch run: dub (1 take) -> pick -> re-dub flagged lines (3 takes) -> pick
-> if still > 3% flagged, up to 6 takes -> pick -> fx.

  python tools/pipeline.py eva allied soviet empire

Logs go to logs/<batch>.log; one line per stage is printed here.
"""
import csv
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PY = os.path.join(ROOT, 'third_party', 'index-tts', '.venv', 'Scripts', 'python.exe')
SYS_PY = sys.executable
KEEP = ('PROGRESS', 'FAILED', 'FINISHED', 'flagged', 'Traceback', 'Error', 'clips ->', 'POLISH')


def run(batch, cmd):
    os.makedirs(os.path.join(ROOT, 'logs'), exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    t = time.time()
    with open(os.path.join(ROOT, 'logs', f'{batch}.log'), 'a', encoding='utf-8') as log:
        log.write(f'\n$ {" ".join(cmd)}\n')
        p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding='utf-8', errors='replace')
        for line in p.stdout:
            log.write(line)
            if any(k in line for k in KEEP):
                print(f'[{batch}] {line.rstrip()}', flush=True)
        code = p.wait()
    print(f'[{batch}] {os.path.basename(cmd[4])} {" ".join(cmd[5:7])} exit={code} ({(time.time() - t) / 60:.1f} min)', flush=True)
    return code


def rows(batch):
    with open(os.path.join(ROOT, 'lines', f'{batch}.csv'), encoding='utf-8-sig') as f:
        return [r for r in csv.DictReader(f) if r['zh'].strip()]


def flagged(batch):
    path = os.path.join(ROOT, 'lines', f'{batch}_qc.csv')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8-sig') as f:
        return [r['asset'] for r in csv.DictReader(f) if r['flag']]


def main(batches):
    for b in batches:
        run(b, [VENV_PY, '-I', '-X', 'utf8', 'tools/dub.py', b, '--takes', '1'])
        run(b, [SYS_PY, '-I', '-X', 'utf8', 'tools/pick.py', b])
        total = len(rows(b))
        for takes in (3, 6):  # second round only if more than 3% are still flagged
            redo = flagged(b)
            if not redo or (takes == 6 and len(redo) <= total * 0.03):
                break
            print(f'[{b}] re-dubbing {len(redo)} flagged lines up to {takes} takes', flush=True)
            for i in range(0, len(redo), 200):  # keep the command line short
                run(b, [VENV_PY, '-I', '-X', 'utf8', 'tools/dub.py', b, '--takes', str(takes), '--only', *redo[i:i + 200]])
            run(b, [SYS_PY, '-I', '-X', 'utf8', 'tools/pick.py', b])
        run(b, [VENV_PY, '-I', '-X', 'utf8', 'tools/fx.py', 'apply', b])
        print(f'[{b}] DONE, still flagged: {len(flagged(b))}', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
