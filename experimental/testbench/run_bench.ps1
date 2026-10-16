# run_bench.ps1 [-Mod <skudef>] [-Shots 15,30,45] [-Seconds 60] [-Res 1280x720] [-Extra '<more args>']
# Starts the test bench copy of RA3 (make_bench.ps1) windowed, saves a frame at each of -Shots seconds through the
# capture shim (shots\NN.bmp -> .png), closes only the game process it started, prints the shim log.
# Like the Corona launcher, it starts Data\RA3_1.13.game directly with the bench's Chinese SkuDef.
# By default the window is parked off the desktop and the game's own audio sessions are muted (-Visible / -Sound
# keep them); the game's "Game crash" box ends the run with its text instead of staying on the user's screen.
param([string]$Mod, [string]$Shots = '20,40', [int]$Seconds = 60, [string]$Res = '1280x720', [string]$Extra = '',
      [string]$Clicks = '',     # 'sec:x,y;sec:x,y' left clicks posted to the game window (client coordinates)
      [string]$Keys = '',       # 'sec:vk;sec:vk' key presses posted to the game window (virtual-key code, e.g. 27 = Esc)
      [switch]$Visible,         # leave the window on screen (default: parked off the desktop, still rendering)
      [switch]$Sound,           # leave the game's audio on (default: its own audio sessions muted)
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
    // out of sight, not minimized (a minimized D3D9 window stops presenting): parked off the desktop, no activation
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint f);
    public static void Park(IntPtr h) { SetWindowPos(h, IntPtr.Zero, -4000, -4000, 0, 0, 0x0001 | 0x0004 | 0x0010); }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr h, EnumProc f, IntPtr l);
    // the game's own fatal-error box ("Game crash", e.g. a type hash mismatch): its text, or null
    public static string CrashBox(uint pid) {
        string text = null;
        EnumWindows((h, l) => {
            uint p; GetWindowThreadProcessId(h, out p); var sb = new StringBuilder(256); GetWindowText(h, sb, 256);
            if (p == pid && sb.ToString() == "Game crash") {
                var all = new StringBuilder();
                EnumChildWindows(h, (c, l2) => { var t = new StringBuilder(2048); GetWindowText(c, t, 2048); all.Append(t).Append(" | "); return true; }, IntPtr.Zero);
                text = all.ToString(); return false;
            }
            return true;
        }, IntPtr.Zero);
        return text;
    }
}
// mute only the bench game's audio sessions (Core Audio per-process session volume; the system volume is untouched)
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorCo { }
[ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator { int EnumAudioEndpoints(int flow, int mask, out IMMDeviceCollection c); }
[ComImport, Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceCollection { int GetCount(out int n); int Item(int i, out IMMDevice d); }
[ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice { int Activate(ref Guid iid, int ctx, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object o); }
[ComImport, Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioSessionManager2 { int GetAudioSessionControl(IntPtr a, int b, out IntPtr c); int GetSimpleAudioVolume(IntPtr a, int b, out IntPtr c);
    int GetSessionEnumerator(out IAudioSessionEnumerator e); }
[ComImport, Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioSessionEnumerator { int GetCount(out int n); int GetSession(int i, out IAudioSessionControl2 s); }
[ComImport, Guid("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioSessionControl2 { int GetState(out int s); int GetDisplayName(out IntPtr n); int SetDisplayName(string n, ref Guid g);
    int GetIconPath(out IntPtr p); int SetIconPath(string p, ref Guid g); int GetGroupingParam(out Guid g); int SetGroupingParam(ref Guid g, ref Guid c);
    int RegisterAudioSessionNotification(IntPtr n); int UnregisterAudioSessionNotification(IntPtr n);
    int GetSessionIdentifier(out IntPtr s); int GetSessionInstanceIdentifier(out IntPtr s); int GetProcessId(out uint pid); }
[ComImport, Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface ISimpleAudioVolume { int SetMasterVolume(float v, ref Guid g); int GetMasterVolume(out float v); int SetMute(bool m, ref Guid g); int GetMute(out bool m); }
public static class BenchAudio {
    // returns how many of the process's sessions are muted now (sessions appear once the game opens audio)
    public static int Mute(uint pid) {
        int muted = 0; var none = Guid.Empty; var iid = new Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F");
        var en = (IMMDeviceEnumerator)new MMDeviceEnumeratorCo(); IMMDeviceCollection devs; en.EnumAudioEndpoints(0, 1, out devs);
        int nd; devs.GetCount(out nd);
        for (int d = 0; d < nd; d++) {
            IMMDevice dev; devs.Item(d, out dev); object o; dev.Activate(ref iid, 23, IntPtr.Zero, out o);
            IAudioSessionEnumerator se; ((IAudioSessionManager2)o).GetSessionEnumerator(out se); int ns; se.GetCount(out ns);
            for (int s = 0; s < ns; s++) {
                IAudioSessionControl2 c; se.GetSession(s, out c); uint p; c.GetProcessId(out p);
                if (p == pid) { ((ISimpleAudioVolume)c).SetMute(true, ref none); muted++; }
            }
        }
        return muted;
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
$crash = $null; $box = $null; $parked = $false; $muted = 0
foreach ($s in 1..$Seconds) {
    Start-Sleep 1
    if (-not $Visible -and -not $parked) {
        $hw = [Bench]::MainWindow([uint32]$p.Id)
        if ($hw -ne [IntPtr]::Zero) { [Bench]::Park($hw); $parked = $true; "PARKED window $hw off screen at $s s" }
    }
    if (-not $Sound -and ($muted -eq 0 -or $s % 5 -eq 0)) {
        try { $n = [BenchAudio]::Mute([uint32]$p.Id); if ($n -gt $muted) { "MUTED $n audio session(s) at $s s" }; $muted = [Math]::Max($muted, $n) } catch { }
    }
    $box = [Bench]::CrashBox([uint32]$p.Id)
    if ($box) { break }
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
$state = if ($box) { "CRASH BOX: $box" } elseif ($crash) { 'CRASH' } elseif ($p.HasExited) { "EXITED code $($p.ExitCode)" } else { "alive $Seconds s" }
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
