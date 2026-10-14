# boottest.ps1 -Big <path> [-Wait 60]
# Installs <Big> as Documents\Red Alert 3\Mods\ShaderTest, starts RA3 with it, and reports
#   PASS  game still running <Wait> s after start, no crash event
#   FAIL  Windows logged an RA3 application error (prints module + exception code)
# Only the game process started by this run is closed afterwards.
param([string]$Big, [int]$Wait = 60, [string]$Bat, [string]$Shot, [int]$ShotAt = 0)   # -Bat: run an existing launcher as-is instead of installing <Big>; -Shot <png> -ShotAt <s>: screenshot while running
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
$ErrorActionPreference = 'Stop'
for ($i = 0; $i -lt 30 -and (Get-Process | Where-Object { $_.ProcessName -match '^ra3' }); $i++) { Start-Sleep 1 }   # launcher of a previous run lingers a few seconds
$running = Get-Process | Where-Object { $_.ProcessName -match '^ra3' }
if ($running) { Write-Output "ABORT: RA3 is already running ($($running.ProcessName -join ','))"; exit 3 }

if ($Bat) { $mod = Split-Path $Bat } else {
$mod = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Red Alert 3\Mods\ShaderTest'
New-Item -ItemType Directory -Force $mod | Out-Null
Copy-Item $Big (Join-Path $mod 'ShaderTest.big') -Force
# exactly what the hand-made launchers that the user ran do: skudef ending in CRLF, started from a .bat in the mod folder
[IO.File]::WriteAllText((Join-Path $mod 'ShaderTest_1.0.skudef'), "mod-game 1.12`r`nadd-big ShaderTest.big`r`n")
$bat = Join-Path $mod 'launch_test.bat'
[IO.File]::WriteAllText($bat, "@echo off`r`nstart `"`" `"C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3\RA3.exe`" -modConfig `"%~dp0ShaderTest_1.0.skudef`"`r`n")
}
$t0 = Get-Date
Start-Process cmd.exe -ArgumentList @('/c', "`"$bat`"") -WorkingDirectory $mod -WindowStyle Hidden
$game = $null
$result = $null
for ($i = 0; $i -lt $Wait; $i++) {
    Start-Sleep -Seconds 1
    if (-not $game) { $game = Get-Process | Where-Object { $_.ProcessName -match '^RA3_1\.1\d' -and $_.StartTime -gt $t0 } | Select-Object -First 1 }
    $crash = Get-WinEvent -FilterHashtable @{LogName = 'Application'; Id = 1000; StartTime = $t0} -ErrorAction SilentlyContinue |
             Where-Object { $_.Message -match 'RA3_1\.1\d\.game' } | Select-Object -First 1
    if ($crash) {
        $lines = $crash.Message -split "`r?`n"
        $result = 'FAIL ' + (($lines | Select-Object -Index 1, 2, 3) -join ' | ')
        break
    }
    if ($game -and $game.HasExited) { $result = "FAIL exited without crash event after $i s"; break }
    if ($Shot -and $i -eq $ShotAt) {
        $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
        $bmp.Save($Shot, [System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose()
    }
}
if (-not $result) { $result = if ($game) { "PASS alive $Wait s (pid $($game.Id))" } else { 'FAIL game process never appeared' } }
if ($game -and -not $game.HasExited) { Stop-Process -Id $game.Id -Force }
Write-Output $result
