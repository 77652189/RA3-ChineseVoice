"""Final polish after tools/pipeline.py: more takes for still-flagged lines, then commas, then fx.

  python tools/finalize.py eva allied soviet empire [--takes 10]

Per batch: flagged lines get up to 10 takes -> pick -> tools/polish.py adds commas only at natural
subject|predicate breaks -> pick -> fx apply. Same logging as pipeline.py (logs/<batch>.log).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import SYS_PY, VENV_PY, flagged, run  # noqa: E402


def main(batches, takes=10):
    for b in batches:
        redo = flagged(b)
        if redo:
            print(f'[{b}] finalize: {len(redo)} flagged lines up to {takes} takes', flush=True)
            for i in range(0, len(redo), 200):
                run(b, [VENV_PY, '-I', '-X', 'utf8', 'tools/dub.py', b, '--takes', str(takes), '--only', *redo[i:i + 200]])
            run(b, [SYS_PY, '-I', '-X', 'utf8', 'tools/pick.py', b])
        if flagged(b):
            run(b, [VENV_PY, '-I', '-X', 'utf8', 'tools/polish.py', b])
            run(b, [SYS_PY, '-I', '-X', 'utf8', 'tools/pick.py', b])
        run(b, [VENV_PY, '-I', '-X', 'utf8', 'tools/fx.py', 'apply', b])
        print(f'[{b}] FINAL, still flagged: {len(flagged(b))}', flush=True)


if __name__ == '__main__':
    args = sys.argv[1:]
    n = 10
    if '--takes' in args:
        i = args.index('--takes')
        n = int(args[i + 1])
        del args[i:i + 2]
    main(args, n)
