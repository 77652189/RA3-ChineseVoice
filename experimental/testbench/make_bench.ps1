# make_bench.ps1 [-Bench <folder>]
# A test copy of the Steam RA3 folder for automated runs, leaving the Steam folder untouched:
#   big read-only game data (.big .vp6 .game .snd .bik over 1 MB) -> NTFS hard links (no extra disk space);
#   everything else (logs, ini, txt, dll ...) -> real copies, because the game writes some of them.
#   Data\d3d9.dll -> our capture_shim (built by build.bat); the original (SAGE-Unlocked) becomes Data\d3d9_next.dll.
# NEVER write into a hard-linked file of the bench: it is the same file as the Steam one. Replace = delete, then create.
param([string]$Bench = (Join-Path $PSScriptRoot '..\..\work\testbench\RA3'))
$ErrorActionPreference = 'Stop'
$game = 'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3'
$shim = Join-Path $PSScriptRoot 'd3d9.dll'
if (-not (Test-Path $shim)) { throw 'build the shim first (build.bat)' }
$running = Get-Process | Where-Object { $_.Path -like "$game*" }
if ($running) { throw "RA3 is running ($($running.ProcessName -join ','))" }
$Bench = [IO.Path]::GetFullPath($Bench)
if ([IO.Path]::GetPathRoot($Bench) -ne [IO.Path]::GetPathRoot($game)) { throw 'bench must be on the same drive as the game (hard links)' }
$linkExt = '.big', '.vp6', '.game', '.snd', '.bik'
$linked = 0; $copied = 0
Get-ChildItem $game -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($game.Length + 1)
    $dst = Join-Path $Bench $rel
    New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
    if (Test-Path $dst) { Remove-Item $dst -Force }        # never write through an old link
    if ($_.Length -gt 1MB -and $linkExt -contains $_.Extension.ToLower()) {
        New-Item -ItemType HardLink -Path $dst -Target $_.FullName | Out-Null; $linked++
    } else {
        Copy-Item $_.FullName $dst; $copied++
    }
}
$data = Join-Path $Bench 'Data'
Remove-Item (Join-Path $data 'd3d9.dll') -Force                  # a copy, but delete-then-create anyway
Copy-Item (Join-Path $game 'Data\d3d9.dll') (Join-Path $data 'd3d9_next.dll')
Copy-Item $shim (Join-Path $data 'd3d9.dll')
New-Item -ItemType Directory -Force (Join-Path $Bench 'shots') | Out-Null
"bench $Bench : $linked hard links, $copied copies; capture shim in Data\d3d9.dll (next: d3d9_next.dll)"
