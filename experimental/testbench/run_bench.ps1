# run_bench.ps1 [-Mod <skudef>] [-Shots 15,30,45] [-Seconds 60] [-Res 1280x720] [-Extra '<more args>']
# Starts the test bench copy of RA3 (make_bench.ps1) windowed, saves a frame at each of -Shots seconds through the
# capture shim (shots\NN.bmp -> .png), closes only the game process it started, prints the shim log.
# Like the Corona launcher, it starts Data\RA3_1.13.game directly with the bench's Chinese SkuDef.
param([string]$Mod, [string]$Shots = '20,40', [int]$Seconds = 60, [string]$Res = '1280x720', [string]$Extra = '',
      [string]$Clicks = '',     # 'sec:x,y;sec:x,y' left clicks posted to the game window (client coordinates)
      [string]$Keys = '',       # 'sec:vk;sec:vk' key presses posted to the game window (virtual-key code, e.g. 27 = Esc)
      [string]$Bench = (Join-Path $PSScriptRoot '..\..\work\testbench\RA3'))
$ErrorActionPreference = 'Stop'
$shotAt = @($Shots.Split(',') | ForEach-Object { [int]$_ })   # a string: pwsh -File does not parse arrays
$clickAt = @{}
foreach ($c in ($Clicks.Split(';') | Where-Object { $_ })) { $t, $xy = $c.Split(':'); $clickAt[[int]$t] = $xy }
$keyAt = @{}
foreach ($c in ($Keys.Split(';') | Where-Object { $_ })) { $t, $vk = $c.Split(':'); $keyAt[[int]$t] = [int]$vk }
Add-Type @'
using System; using System.Runtime.InteropServices; using System.Text;
public static class Bench {
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    public static IntPtr MainWindow(uint pid) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p); if (p == pid && IsWindowVisible(h)) { found = h; return false; } return true; }, IntPtr.Zero);
        return found;
    }
    // no focus, no real cursor: only window messages (WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP)
    public static void Click(IntPtr h, int x, int y) {
        IntPtr pos = (IntPtr)((y << 16) | (x & 0xFFFF));
        PostMessage(h, 0x0200, IntPtr.Zero, pos); System.Threading.Thread.Sleep(60);
        PostMessage(h, 0x0201, (IntPtr)1, pos); System.Threading.Thread.Sleep(60);
        PostMessage(h, 0x0202, IntPtr.Zero, pos);
    }
    [DllImport("user32.dll")] static extern uint MapVirtualKey(uint code, uint type);
    public static void Key(IntPtr h, int vk) {     // WM_KEYDOWN / WM_KEYUP with the scan code in lParam bits 16-23
        int sc = (int)MapVirtualKey((uint)vk, 0) << 16;
        // the game drops keys while it thinks it is inactive: tell it (messages only, the window is not raised)
        PostMessage(h, 0x001C, (IntPtr)1, IntPtr.Zero);   // WM_ACTIVATEAPP
        PostMessage(h, 0x0006, (IntPtr)1, IntPtr.Zero);   // WM_ACTIVATE, WA_ACTIVE
        PostMessage(h, 0x0007, IntPtr.Zero, IntPtr.Zero); // WM_SETFOCUS
        System.Threading.Thread.Sleep(100);
        PostMessage(h, 0x0100, (IntPtr)vk, (IntPtr)(sc | 1)); System.Threading.Thread.Sleep(80);
        PostMessage(h, 0x0101, (IntPtr)vk, (IntPtr)unchecked((int)(0xC0000001 | (uint)sc)));
    }
}
'@
Add-Type -AssemblyName System.Drawing
$Bench = [IO.Path]::GetFullPath($Bench)
$shotDir = Join-Path $Bench 'shots'
if (Get-Process | Where-Object { $_.ProcessName -match '^ra3' }) { Write-Output 'ABORT: an RA3 process is already running'; exit 3 }
Get-ChildItem $shotDir -File -ErrorAction SilentlyContinue | Remove-Item -Force
$w, $h = $Res.Split('x')
$gameArgs = @('-config', "`"$Bench\RA3_chinese_t_1.13.SkuDef`"", '-runver', '1.13', '-win', '-xres', $w, '-yres', $h)
if ($Mod) { $gameArgs += @('-modConfig', "`"$Mod`"") }
if ($Extra) { $gameArgs += $Extra.Split(' ') }
$t0 = Get-Date
# .game is not an executable extension for the shell: CreateProcess directly (UseShellExecute off), as the Corona launcher does
$psi = [Diagnostics.ProcessStartInfo]::new("$Bench\Data\RA3_1.13.game", ($gameArgs -join ' '))
$psi.UseShellExecute = $false
$psi.WorkingDirectory = $Bench
$p = [Diagnostics.Process]::Start($psi)
$crash = $null
foreach ($s in 1..$Seconds) {
    Start-Sleep 1
    if ($clickAt.ContainsKey($s)) {
        $hw = [Bench]::MainWindow([uint32]$p.Id); $x, $y = $clickAt[$s].Split(',')
        "CLICK at $s s: ($x,$y) window $hw"; if ($hw -ne [IntPtr]::Zero) { [Bench]::Click($hw, [int]$x, [int]$y) }
    }
    if ($keyAt.ContainsKey($s)) {
        $hw = [Bench]::MainWindow([uint32]$p.Id); "KEY at $s s: vk $($keyAt[$s])"
        if ($hw -ne [IntPtr]::Zero) { [Bench]::Key($hw, $keyAt[$s]) }
        # the game polls the keyboard (GetAsyncKeyState): the capture shim makes the key read as held for 300 ms
        Set-Content (Join-Path $shotDir 'key.req') $keyAt[$s] -Encoding ascii
    }
    if ($shotAt -contains $s) { "REQ shot at $s s"; Set-Content (Join-Path $shotDir 'shot.req') ('{0:D3}s' -f $s) -Encoding ascii }
    $crash = Get-WinEvent -FilterHashtable @{LogName = 'Application'; Id = 1000; StartTime = $t0} -ErrorAction SilentlyContinue |
             Where-Object { $_.Message -match 'RA3_1\.1\d\.game' } | Select-Object -First 1
    if ($crash -or $p.HasExited) { break }
}
$state = if ($crash) { 'CRASH' } elseif ($p.HasExited) { "EXITED code $($p.ExitCode)" } else { "alive $Seconds s" }
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
Start-Sleep 1
Get-ChildItem $shotDir -Filter *.bmp | ForEach-Object {
    $img = [Drawing.Image]::FromFile($_.FullName); $png = [IO.Path]::ChangeExtension($_.FullName, '.png')
    $img.Save($png, [Drawing.Imaging.ImageFormat]::Png); $img.Dispose(); Remove-Item $_.FullName
}
"RESULT $state (pid $($p.Id))"
if ($crash) { ($crash.Message -split "`n")[0..4] -join ' | ' }
Get-Content (Join-Path $shotDir 'cnv_testbench.log') -ErrorAction SilentlyContinue | Select-Object -Last 25
Get-ChildItem $shotDir -Filter *.png | ForEach-Object { "SHOT $($_.FullName)" }
