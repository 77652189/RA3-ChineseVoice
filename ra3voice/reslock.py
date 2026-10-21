"""Shared-resource locks for the two RA3 lines (voice: RA3-ChineseVoice, content: RA3-CampaignLab).

Both repositories keep an identical copy of this file. Lock files live in <LAB>\\shared\\locks\\ (<LAB> = the folder
holding both repositories, e.g. Documents\\RA3Modding; RA3_SHARED overrides the shared folder):

  bench.json        exclusive: the game / test bench (one RA3 at a time)
  gpu-<tag>.json    lease: a GPU job is running. Not exclusive -- every GPU job also obeys shared\\gpu_limit.json
                    (ra3voice.throttle writes and removes its lease by itself)

Each file: {"owner": "<line / tool>", "pid": <process>, "since": "<iso time>", "until": "<iso time>" | null,
"note": "..."}. A lock with an 'until' holds until that time, whether its process lives or not (the CLI's acquire
records a process that exits at once); a lock without one holds while its process lives. Otherwise it is stale:
ignored and overwritable.

  python -I ra3voice/reslock.py status
  python -I ra3voice/reslock.py acquire <name> <owner> [minutes] [note...]     (exit 1 if held)
  python -I ra3voice/reslock.py release <name>
"""
import atexit
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def shared_dir():
    return os.environ.get('RA3_SHARED') or os.path.join(os.path.dirname(ROOT), 'shared')


def _path(name):
    return os.path.join(shared_dir(), 'locks', name + '.json')


def _pid_alive(pid):
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259                 # STILL_ACTIVE
    except (AttributeError, OSError, ValueError):
        return True                                           # cannot tell: assume held


def read(name):
    """The lock's record if it is held (live process, not expired), else None."""
    try:
        with open(_path(name), encoding='utf-8') as f:
            info = json.load(f)
    except (OSError, ValueError):
        return None
    until = info.get('until')
    if until:       # a timed lock holds until it expires: a CLI acquire's process is gone right after it
        return info if datetime.datetime.fromisoformat(until) >= datetime.datetime.now() else None
    return info if _pid_alive(info.get('pid', 0)) else None


def acquire(name, owner, minutes=None, note='', pid=None):
    """Take the lock; False (and nothing written) if someone else holds it."""
    held = read(name)
    pid = pid or os.getpid()
    if held and held.get('pid') != pid:
        return False
    now = datetime.datetime.now()
    info = {'owner': owner, 'pid': pid, 'since': now.isoformat(timespec='seconds'),
            'until': (now + datetime.timedelta(minutes=minutes)).isoformat(timespec='seconds') if minutes else None,
            'note': note}
    os.makedirs(os.path.dirname(_path(name)), exist_ok=True)
    with open(_path(name), 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False)
    return True


def release(name, pid=None):
    held = read(name)
    if held is None or held.get('pid') == (pid or os.getpid()) or pid == 'any':
        try:
            os.remove(_path(name))
        except OSError:
            pass


def gpu_lease(owner, note=''):
    """Register this process as a GPU job until it exits (called by throttle.setup)."""
    tag = 'gpu-' + os.path.splitext(os.path.basename(sys.argv[0] or 'python'))[0] + f'-{os.getpid()}'
    if acquire(tag, owner, note=note):
        atexit.register(release, tag)
    return tag


def status():
    d = os.path.join(shared_dir(), 'locks')
    out = []
    for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if n.endswith('.json'):
            info = read(n[:-5])
            out.append((n[:-5], info))
    return out


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'status':
        for name, info in status():
            print(f'{name:28s}', 'stale' if info is None else
                  f"{info['owner']} pid {info['pid']} since {info['since']} until {info['until']} {info['note']}")
    elif cmd == 'acquire':
        name, owner = sys.argv[2], sys.argv[3]
        minutes = float(sys.argv[4]) if len(sys.argv) > 4 else None
        ok = acquire(name, owner, minutes, ' '.join(sys.argv[5:]), pid=os.getppid())
        print('acquired' if ok else f'held: {read(name)}')
        sys.exit(0 if ok else 1)
    elif cmd == 'release':
        release(sys.argv[2], pid='any')
