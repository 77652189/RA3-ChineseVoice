"""Watch total GPU memory while a batch runs; if it passes the limit, drop the duty cycle.

  python tools/vram_guard.py [--limit-gb 15] [--duty 0.6]

Checks nvidia-smi once a minute and rewrites gpu_limit.json (read live by ra3voice/throttle.py).
Exits when no dubbing pipeline is running any more. Events go to logs/vram_guard.log.
"""
import argparse
import json
import os
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, 'gpu_limit.json')
LOG = os.path.join(ROOT, 'logs', 'vram_guard.log')


def used_gb():
    out = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
                         capture_output=True, text=True).stdout.strip().splitlines()
    return int(out[0]) / 1024 if out else 0.0


def pipeline_running():
    out = subprocess.run(['pwsh', '-NoProfile', '-Command',
                          "@(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' "
                          "-and $_.CommandLine -match 'tools.(pipeline|finalize)' }).Count"],
                         capture_output=True, text=True).stdout.strip()
    return out not in ('', '0')


def log(msg):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit-gb', type=float, default=15.0)
    ap.add_argument('--duty', type=float, default=0.6)
    a = ap.parse_args()
    log(f'guard started, limit {a.limit_gb} GB -> duty {a.duty}')
    peak = 0.0
    while pipeline_running():
        gb = used_gb()
        peak = max(peak, gb)
        cfg = json.load(open(CFG, encoding='utf-8'))
        if gb > a.limit_gb and cfg.get('duty', 1) > a.duty:
            cfg['duty'] = a.duty
            json.dump(cfg, open(CFG, 'w', encoding='utf-8'))
            log(f'VRAM {gb:.1f} GB > {a.limit_gb} GB: duty lowered to {a.duty}')
        time.sleep(60)
    log(f'guard stopped (pipeline finished), peak VRAM {peak:.1f} GB')


if __name__ == '__main__':
    main()
