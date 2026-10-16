# run_bench.ps1 [-Mod <skudef>] [-Shots 15,30,45] [-Seconds 60] [-Res 1280x720] [-Extra '<more args>']
# Starts the test bench copy of RA3 (make_bench.ps1) windowed, saves a frame at each of -Shots seconds through the
# capture shim (shots\NN.bmp -> .png), closes only the game process it started, prints the shim log.
# Like the Corona launcher, it starts Data\RA3_1.13.game directly with the bench's Chinese SkuDef.
param([string]$Mod, [string]$Shots = '20,40', [int]$Seconds = 60, [string]$Res = '1280x720', [string]$Extra = '',
      [string]$Bench = (Join-Path $PSScriptRoot '..\..\work\testbench\RA3'))
$ErrorActionPreference = 'Stop'
$shotAt = @($Shots.Split(',') | ForEach-Object { [int]$_ })   # a string: pwsh -File does not parse arrays
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
