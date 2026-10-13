"""Compile the GUI installer (installer/gui/Installer.cs) with the C# compiler that ships with Windows.

  python tools/build_installer.py        -> installer/gui/out/CNVoiceSetup.exe (+ icon.ico)
  python tools/build_installer.py --test -> installer/gui/out/CNVoiceSetup_test.exe (no admin prompt, for automated tests)

No download needed: .NET Framework 4.x csc + WPF assemblies are part of Windows 10/11.
"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI = os.path.join(ROOT, 'installer', 'gui')
OUT = os.path.join(GUI, 'out')
FW = r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319'
REFS = [os.path.join(FW, 'WPF', n) for n in ('PresentationFramework.dll', 'PresentationCore.dll', 'WindowsBase.dll')] + \
       [os.path.join(FW, n) for n in ('System.Xaml.dll', 'System.Web.Extensions.dll', 'System.Windows.Forms.dll', 'System.Core.dll')]
EXE = 'CNVoiceSetup.exe'


def star(cx, cy, r_out, r_in):
    import math
    pts = []
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def make_icon(path):
    """Dark rounded tile with a red star (rendered large, downsampled for clean edges)."""
    S = 1024
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, S - 40, S - 40), radius=200, fill=(24, 27, 32, 255), outline=(60, 64, 72, 255), width=16)
    d.polygon(star(S / 2, S / 2 + 30, 360, 145), fill=(215, 38, 46, 255))
    img.save(path, sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])


def main():
    test = '--test' in sys.argv
    os.makedirs(OUT, exist_ok=True)
    icon = os.path.join(OUT, 'icon.ico')
    make_icon(icon)
    manifest = os.path.join(GUI, 'app.manifest')
    exe = EXE
    if test:
        exe = EXE.replace('.exe', '_test.exe')
        text = open(manifest, encoding='utf-8').read().replace('requireAdministrator', 'asInvoker')
        manifest = os.path.join(OUT, 'test.manifest')
        open(manifest, 'w', encoding='utf-8').write(text)
    cmd = [os.path.join(FW, 'csc.exe'), '/nologo', '/target:winexe', '/optimize+', '/codepage:65001',
           '/out:' + os.path.join(OUT, exe), '/win32icon:' + icon,
           '/win32manifest:' + manifest] + ['/r:' + r for r in REFS] + \
          [os.path.join(GUI, 'Installer.cs')]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='mbcs', errors='replace')
    print(r.stdout[-4000:], r.stderr[-2000:])
    if r.returncode:
        sys.exit(r.returncode)
    print('->', os.path.join(OUT, exe), os.path.getsize(os.path.join(OUT, exe)), 'bytes')


if __name__ == '__main__':
    main()
