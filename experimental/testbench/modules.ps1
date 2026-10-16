# modules.ps1 [-At 30] : start the bench game, list the DLLs it has loaded after -At seconds (input-related first), close it.
param([int]$At = 30, [string]$Bench = (Join-Path $PSScriptRoot '..\..\work\testbench\RA3'))
$Bench = [IO.Path]::GetFullPath($Bench)
if (Get-Process | Where-Object { $_.ProcessName -match '^ra3' }) { 'ABORT: an RA3 process is already running'; exit 3 }
$psi = [Diagnostics.ProcessStartInfo]::new("$Bench\Data\RA3_1.13.game", "-config `"$Bench\RA3_chinese_t_1.13.SkuDef`" -runver 1.13 -win -xres 1280 -yres 720")
$psi.UseShellExecute = $false; $psi.WorkingDirectory = $Bench
$p = [Diagnostics.Process]::Start($psi)
Start-Sleep $At
$mods = (tasklist /m /fi "PID eq $($p.Id)" /fo csv | ConvertFrom-Csv).Modules -split ','
Stop-Process -Id $p.Id -Force
"input-related: " + (($mods | Where-Object { $_ -match 'dinput|xinput|hid|raw' }) -join ', ')
"all ($($mods.Count)): " + ($mods -join ', ')
