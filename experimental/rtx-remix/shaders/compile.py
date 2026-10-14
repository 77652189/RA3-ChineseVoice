"""compile.py <src_dir> <out_dir> [names...]: compile RA3 .fx with EA's flags (from the game's .dep files)."""
import os, subprocess, sys

S = os.path.dirname(os.path.abspath(__file__))
FXC = os.path.join(S, 'fxc.exe')          # Microsoft-signed DirectX SDK (June 2010) fxc, copied from the PBR repo
TARGETS = ['BuildingsAllied', 'BuildingsGeneric', 'BuildingsJapan', 'BuildingsJapanBuildup', 'BuildingsSoviet',
           'ObjectsAllied', 'ObjectsAlliedTread', 'ObjectsFormationPreview', 'ObjectsGeneric', 'ObjectsGenericLightmap',
           'ObjectsJapan', 'ObjectsRoads', 'ObjectsSoviet', 'ObjectsTerrain', 'ObjectsTesla', 'Terrain']

src, out = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
names = sys.argv[3:] or TARGETS
os.makedirs(out, exist_ok=True)
bad = 0
for n in names:
    fo = os.path.join(out, n.lower() + '.fxo')
    # source must be run through fix_noinit.py first (this fxc rejects empty macro arguments)
    cmd = [FXC, '/nologo', '/DEA_PLATFORM_WINDOWS', '/D_WW3D_', '/D_WW3D_VERSION_=1', '/I', src, '/Tfx_2_0',
           '/Fo', fo, os.path.join(src, n + '.fx')]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=src)
    msg = (r.stdout + r.stderr).strip()
    errs = [l for l in msg.splitlines() if 'error' in l.lower()]
    print(('OK  ' if r.returncode == 0 else 'FAIL') + ' ' + n + ('' if r.returncode == 0 else '\n    ' + '\n    '.join(errs[:6])))
    bad += r.returncode != 0
sys.exit(bad)
