"""Share the GPU with whatever else the user is running (e.g. a game).

gpu_limit.json, re-read before every work item so it can be changed live:
  {"duty": 0.4, "vram_gb": 7}
  duty     fraction of wall time spent on GPU work (1 = full speed); the rest is spent sleeping
  vram_gb  cap for PyTorch's allocator in this process (applied once at start-up)
The one both RA3 lines share is <LAB>\\shared\\gpu_limit.json (see reslock); a project-root copy is the fallback.
Missing file = full speed, no cap. The process also drops itself to below-normal priority and registers a GPU
lease in shared\\locks\\ until it exits.
"""
import json
import os
import time

from . import reslock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHARED_CFG = os.path.join(reslock.shared_dir(), 'gpu_limit.json')
CFG = _SHARED_CFG if os.path.exists(_SHARED_CFG) else os.path.join(ROOT, 'gpu_limit.json')


def config():
    try:
        with open(CFG, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def setup(torch=None, owner='RA3-ChineseVoice'):
    """Lower process priority, apply the VRAM cap and register a GPU lease. Call before loading models."""
    try:
        reslock.gpu_lease(owner, note=f"duty {config().get('duty', 1.0)}")
    except OSError:
        pass
    try:
        import ctypes
        BELOW_NORMAL = 0x4000
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL)
    except (AttributeError, OSError):
        pass
    gb = config().get('vram_gb')
    if torch is not None and gb and torch.cuda.is_available():
        total = torch.cuda.get_device_properties(0).total_memory / 2 ** 30
        torch.cuda.set_per_process_memory_fraction(min(1.0, gb / total), 0)
        print(f'[throttle] VRAM cap {gb} GB of {total:.1f} GB', flush=True)


class work:
    """with throttle.work(): <one GPU work item>  -> sleeps afterwards to honour the duty cycle."""

    def __enter__(self):
        self.t = time.time()
        return self

    def __exit__(self, *exc):
        duty = float(config().get('duty', 1.0))
        if 0 < duty < 1:
            busy = time.time() - self.t
            time.sleep(busy * (1 - duty) / duty)
        return False
