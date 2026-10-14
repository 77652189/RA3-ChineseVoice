# 红警3 / 起义时刻 中文配音 MOD 安装器（Windows PowerShell 5.1 兼容）
# 由 安装.bat / 卸载.bat 调用；也可：
#   -Action install|uninstall  -Components "allied,soviet,empire,eva" | "all"  -Silent  -GameDir "<路径1>|<路径2>"
# install 的 -Components = 装好后要有的组件；uninstall 的 -Components = 要去掉的组件。
param(
    [ValidateSet('install', 'uninstall')][string]$Action = 'install',
    [string]$Components,   # 不给就弹窗让玩家勾选
    [switch]$Silent,
    [string]$GameDir       # 用 | 分隔多个目录
)
$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Pkg = Get-Content (Join-Path $Here 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$AllComp = @($Pkg.components | ForEach-Object { $_.id })
$CompName = @{}; $CompLetter = @{}
foreach ($c in $Pkg.components) { $CompName[$c.id] = $c.name; $CompLetter[$c.id] = $c.letter }
# 'voice' 组件替换语音（需要配套的 core 长度表）；'text' 组件替换文字和字体，和语音无关
$TextComp = @($Pkg.components | Where-Object { $_.kind -eq 'text' } | ForEach-Object { $_.id })
# 'fps' 组件 = 帧率解锁插件 SAGE-Unlocked（GPL-3.0）：三个文件放进 Data\，和本 MOD 的包无关
$FpsComp = @($Pkg.components | Where-Object { $_.kind -eq 'fps' } | ForEach-Object { $_.id })
$VoiceComp = @($AllComp | Where-Object { $TextComp -notcontains $_ -and $FpsComp -notcontains $_ })
$FpsMark = 'CNVoice_fps.json'     # 记下本 MOD 装进去的插件文件和哈希：卸载时只删自己装的
$FpsDlls = @('d3d9.dll', 'CnCFpsUnlocker.dll')
$FpsIni = 'SAGEUnlocked.ini'
$DefaultFps = 120                 # 插件不会超过显示器刷新率，掉帧时游戏速度也不变
$CoreBig = $Pkg.core
$MarkerRe = 'add-big\s+Data\\(CNVoice\w*|ChineseVoice)\.big'   # 本 MOD 写进配置的行（含旧版本的名字）
$LegacyBigs = @('CNVoiceMod.big', 'ChineseVoice.big')
$SkuRe = '^(RA3EP1|RA3)_([A-Za-z_]+)_(\d+)\.(\d+)\.SkuDef$'
$Latin1 = [Text.Encoding]::GetEncoding(28591)   # SkuDef 是纯 ASCII，用 Latin-1 原样读写字节
$BackupExt = '.cnvoice-backup'
$MarkerFile = 'CNVoice_installed.json'   # 记录装的是哪个版本，和图形安装器一致
# 文字组件：官方语言包（Lang-English11.big、ChineseT.big……）在哪份配置里加载，文字包就插在那份的最前面
$LangBigRe = '(?mi)^[ \t]*add-big[ \t]+Data\\(Lang-[A-Za-z]+\d*|English|ChineseT|ChineseS|German|French|Spanish|Italian|Korean|Polish|Russian|Japanese|Dutch|Swedish|Norwegian|Czech|Hungarian|Portuguese|Brazilian)\.big[ \t]*\r?$'
# 非繁中语言用简体文字时，还要加载繁中包里的字体映射（FontSubstitution）；本 MOD 的文字包排在它前面
$LocaleBig = 'ChineseT.big'

function Say([string]$m, [string]$color = 'Gray') { Write-Host $m -ForegroundColor $color }
function Done([int]$code) {
    if (-not $Silent) { Write-Host ''; Read-Host '按回车键关闭窗口' | Out-Null }
    exit $code
}
function Read-Raw([string]$p) { return [IO.File]::ReadAllText($p, $Latin1) }
function Write-Raw([string]$p, [string]$t) { [IO.File]::WriteAllText($p, $t, $Latin1) }
function Comp-Big([string]$c) { return $Pkg.component_big -replace '\{\}', $c }

# ---------------------------------------------------------------- 找游戏
function Get-GameKind([string]$dir) {
    if (-not $dir -or -not (Test-Path -LiteralPath $dir -PathType Container)) { return $null }
    if ((Test-Path -LiteralPath (Join-Path $dir 'RA3EP1.exe')) -or (Get-ChildItem -LiteralPath $dir -Filter 'RA3EP1_*.SkuDef' -ErrorAction SilentlyContinue)) { return 'uprising' }
    if ((Test-Path -LiteralPath (Join-Path $dir 'RA3.exe')) -or (Get-ChildItem -LiteralPath $dir -Filter 'RA3_*.SkuDef' -ErrorAction SilentlyContinue)) { return 'ra3' }
    return $null
}

function Find-Games {
    $cands = New-Object System.Collections.Generic.List[string]
    if ($GameDir) { foreach ($d in ($GameDir -split '\|')) { if ($d) { $cands.Add($d) } } }
    else {
        # EA / Origin / EA App / 零售版写在注册表里的安装目录
        foreach ($root in 'HKLM:\SOFTWARE\WOW6432Node\Electronic Arts', 'HKLM:\SOFTWARE\Electronic Arts', 'HKLM:\SOFTWARE\WOW6432Node\EA Games', 'HKLM:\SOFTWARE\EA Games') {
            if (-not (Test-Path $root)) { continue }
            Get-ChildItem $root -Recurse -Depth 2 -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'Red Alert 3|Red Alert\(tm\) 3' } | ForEach-Object {
                $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
                foreach ($v in 'Install Dir', 'InstallDir', 'Install Location') { if ($p.$v) { $cands.Add([string]$p.$v) } }
            }
        }
        # Steam 各个库目录
        $steam = (Get-ItemProperty 'HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue).SteamPath
        if ($steam) {
            $libs = @($steam)
            $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
            if (Test-Path -LiteralPath $vdf) {
                foreach ($m in [regex]::Matches((Get-Content -LiteralPath $vdf -Raw), '"path"\s+"([^"]+)"')) { $libs += $m.Groups[1].Value -replace '\\\\', '\' }
            }
            foreach ($l in $libs) {
                foreach ($n in 'Command and Conquer Red Alert 3', 'Command and Conquer Red Alert 3 Uprising') { $cands.Add((Join-Path $l "steamapps\common\$n")) }
            }
        }
        # 安装包放在游戏目录里时
        $cands.Add((Split-Path -Parent (Split-Path -Parent $Here)))
    }
    $seen = @{}
    $found = @()
    foreach ($c in $cands) {
        try { $full = (Resolve-Path -LiteralPath $c -ErrorAction Stop).Path.TrimEnd('\') } catch { continue }
        if ($seen.ContainsKey($full.ToLower())) { continue }
        $seen[$full.ToLower()] = $true
        $kind = Get-GameKind $full
        if ($kind) { $found += [pscustomobject]@{ Dir = $full; Kind = $kind } }
    }
    return $found
}

function Ask-Folder {
    Add-Type -AssemblyName System.Windows.Forms
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = '没有自动找到游戏，请选择《红警3》或《起义时刻》的安装文件夹（里面有 RA3.exe 或 RA3EP1.exe）'
    if ($dlg.ShowDialog() -eq 'OK') { return $dlg.SelectedPath }
    return $null
}

function Test-Writable([string]$dir) {
    try {
        $t = Join-Path $dir ('.cnvoice_write_test_' + [guid]::NewGuid().ToString('N'))
        [IO.File]::WriteAllText($t, 'x'); Remove-Item -LiteralPath $t -Force; return $true
    } catch { return $false }
}

# ---------------------------------------------------------------- 组件选择
function Get-Installed($g) {
    return @($AllComp | Where-Object {
        if ($FpsComp -contains $_) { Test-Path -LiteralPath (Join-Path $g.Dir "Data\$FpsMark") }
        else { Test-Path -LiteralPath (Join-Path $g.Dir ("Data\" + (Comp-Big $_))) }
    })
}

function Get-Sha1([string]$p) { return (Get-FileHash -LiteralPath $p -Algorithm SHA1).Hash }

function Get-FpsSetting($g) {
    # 现在 ini 里设的帧率（玩家可能自己改过，重装时保留）；旧版插件的 ini 叫 RA3HighFps.ini
    foreach ($n in $FpsIni, 'RA3HighFps.ini') {
        $p = Join-Path $g.Dir "Data\$n"
        if (-not (Test-Path -LiteralPath $p)) { continue }
        $m = [regex]::Match((Read-Raw $p), '(?m)^[ \t]*fps[ \t]*=[ \t]*(\d+)')
        if ($m.Success) { return [int]$m.Groups[1].Value }
    }
    return $null
}

function Set-Fps($g, [int]$fps) {
    $data = Join-Path $g.Dir 'Data'
    if ((Test-Path -LiteralPath (Join-Path $data 'd3d9.dll')) -and -not (Test-Path -LiteralPath (Join-Path $data 'CnCFpsUnlocker.dll'))) {
        # 别的 d3d9.dll（ReShade、DXVK……）：两者不能同时用，不覆盖玩家的东西
        Say '  帧率解锁没有安装：Data 里已经有别的 d3d9.dll（可能是 ReShade、DXVK 等画面工具），为避免冲突跳过了。' 'Yellow'
        return
    }
    $src = Join-Path $Here 'fps'
    $mark = [ordered]@{}
    foreach ($n in $FpsDlls) {
        Copy-Item -LiteralPath (Join-Path $src $n) -Destination (Join-Path $data $n) -Force
        $mark[$n] = Get-Sha1 (Join-Path $data $n)
    }
    Write-Raw (Join-Path $data $FpsIni) ([regex]::Replace((Read-Raw (Join-Path $src $FpsIni)), '(?m)^fps=\d+', "fps=$fps"))
    $mark[$FpsIni] = Get-Sha1 (Join-Path $data $FpsIni)
    [IO.File]::WriteAllText((Join-Path $data $FpsMark), ($mark | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding $false))
    Say "  帧率解锁已安装（$fps 帧）"
}

function Remove-Fps($g) {
    # 只删本 MOD 装进去、之后没被换过的插件文件；玩家自己升级过插件就原样留着
    $data = Join-Path $g.Dir 'Data'
    $mk = Join-Path $data $FpsMark
    if (-not (Test-Path -LiteralPath $mk)) { return }
    $mark = [IO.File]::ReadAllText($mk, [Text.Encoding]::UTF8) | ConvertFrom-Json
    $ours = $true
    foreach ($n in $FpsDlls) {
        $q = Join-Path $data $n
        if ((Test-Path -LiteralPath $q) -and $mark.$n -ne (Get-Sha1 $q)) { $ours = $false }
    }
    if ($ours) {
        foreach ($n in ($FpsDlls + $FpsIni)) {
            $q = Join-Path $data $n
            if (Test-Path -LiteralPath $q) { Remove-Item -LiteralPath $q -Force }
        }
    }
    Remove-Item -LiteralPath $mk -Force
}

function Ask-Components([string]$title, [string]$hint, [string[]]$offer, [string[]]$checked) {
    Add-Type -AssemblyName System.Windows.Forms
    $f = New-Object System.Windows.Forms.Form
    $f.Text = $title; $f.StartPosition = 'CenterScreen'; $f.FormBorderStyle = 'FixedDialog'
    $f.MaximizeBox = $false; $f.MinimizeBox = $false; $f.ClientSize = New-Object Drawing.Size(360, 300)
    $f.Font = New-Object Drawing.Font('Microsoft YaHei UI', 10)
    $lb = New-Object System.Windows.Forms.Label
    $lb.Text = $hint; $lb.SetBounds(16, 12, 330, 44)
    $list = New-Object System.Windows.Forms.CheckedListBox
    $list.CheckOnClick = $true; $list.SetBounds(16, 60, 328, 170)
    foreach ($c in $offer) { [void]$list.Items.Add($CompName[$c], ($checked -contains $c)) }
    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = '确定'; $ok.SetBounds(160, 250, 85, 32); $ok.DialogResult = 'OK'
    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = '取消'; $cancel.SetBounds(256, 250, 85, 32); $cancel.DialogResult = 'Cancel'
    $f.Controls.AddRange(@($lb, $list, $ok, $cancel)); $f.AcceptButton = $ok; $f.CancelButton = $cancel
    $f.TopMost = $true
    if ($f.ShowDialog() -ne 'OK') { return $null }
    # 逗号运算符：保证“一个都没勾”时返回空数组而不是 $null（$null 表示取消）
    return , @($offer | Where-Object { $list.CheckedItems -contains $CompName[$_] })
}

function Parse-Components([string]$s) {
    if (-not $s -or $s -eq 'all') { return $AllComp }
    if ($s -eq 'none') { return @() }
    return @($s -split '[,; ]+' | Where-Object { $AllComp -contains $_ })
}

# ---------------------------------------------------------------- 安装 / 卸载
function Remove-Mod($g) {
    $n = 0
    Get-ChildItem -LiteralPath $g.Dir -Filter '*.SkuDef' | ForEach-Object {
        $text = Read-Raw $_.FullName
        if ($text -notmatch $MarkerRe) { return }
        $backup = $_.FullName + $BackupExt
        if (Test-Path -LiteralPath $backup) {
            # 被本 MOD 插过行的原版配置：用安装时的备份原样恢复
            Copy-Item -LiteralPath $backup -Destination $_.FullName -Force
            Remove-Item -LiteralPath $backup -Force
        } elseif ($text -match 'add-config' -and ($text -split "`n").Count -le 4) {
            # 旧版本 MOD 新建的“版本号 +1”配置（如 RA3_english_1.14.SkuDef）：整个删除
            Remove-Item -LiteralPath $_.FullName -Force
        } else {
            # 没有备份的原版配置：只去掉本 MOD 的行（紧跟在文字包后面的繁中字体映射行也是本 MOD 加的）
            $text = [regex]::Replace($text, "(?m)^([ \t]*add-big\s+Data\\CNVoice_text\.big[ \t]*\r?\n)[ \t]*add-big\s+Data\\$([regex]::Escape($LocaleBig))[ \t]*\r?\n", '$1')
            Write-Raw $_.FullName ([regex]::Replace($text, "(?m)^[ \t]*$MarkerRe[ \t]*\r?\n", ''))
        }
        $n++
    }
    Remove-Fps $g
    $mk = Join-Path $g.Dir "Data\$MarkerFile"
    if (Test-Path -LiteralPath $mk) { Remove-Item -LiteralPath $mk -Force }
    # 本 MOD 的所有包都以 CNVoice 开头（含测试包和旧版本的 CNVoiceMod.big），外加最早期的 ChineseVoice.big
    $bigs = @(Get-ChildItem -LiteralPath (Join-Path $g.Dir 'Data') -Filter 'CNVoice*.big' | ForEach-Object Name) + $LegacyBigs
    foreach ($b in ($bigs | Sort-Object -Unique)) {
        $p = Join-Path $g.Dir "Data\$b"
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force; $n++ }
    }
    return $n
}

function Set-Components($g, [string[]]$want) {
    # 让这个游戏里装着的组件正好等于 $want（空 = 完全卸载，恢复原版）
    $fps = Get-FpsSetting $g
    if ($null -eq $fps) { $fps = $DefaultFps }
    [void](Remove-Mod $g)
    if ($want.Count -eq 0) { return $true }
    $voice = @($want | Where-Object { $VoiceComp -contains $_ })
    $text = @($want | Where-Object { $TextComp -contains $_ })
    if ($voice.Count -and -not (Set-Voice $g $voice)) { [void](Remove-Mod $g); return $false }
    if ($text.Count -and -not (Set-Text $g $text)) { [void](Remove-Mod $g); return $false }
    if (@($want | Where-Object { $FpsComp -contains $_ }).Count) { Set-Fps $g $fps }
    # 记下装的是哪个版本（安装器的“故障诊断”据此区分“旧版本”和“文件损坏”）
    $build = if ($Pkg.build) { $Pkg.build } else { $Pkg.version }
    $edition = if ($Pkg.edition) { $Pkg.edition } else { '完整版' }
    # a full package rebuilt from an update patch keeps that patch's release as base, so later patches still apply
    $base = if ($Pkg.base) { $Pkg.base } else { $build }
    $marker = [ordered]@{ version = $Pkg.version; build = $build; base = $base; edition = $edition; components = @($want) }
    [IO.File]::WriteAllText((Join-Path $g.Dir "Data\$MarkerFile"), ($marker | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding $false))
    return $true
}

function Insert-Lines([string]$path, [int]$at, [string[]]$lines) {
    # 在第 $at 个字符处插入几行；第一次改这份配置前先原样备份，卸载时用备份恢复
    $text = Read-Raw $path
    $eol = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
    $backup = $path + $BackupExt
    if (-not (Test-Path -LiteralPath $backup)) { Write-Raw $backup $text }
    Write-Raw $path ($text.Substring(0, $at) + (($lines | ForEach-Object { $_ + $eol }) -join '') + $text.Substring($at))
}

function Set-Text($g, [string[]]$want) {
    $files = Join-Path $Here $g.Kind
    foreach ($c in $want) {
        $src = Join-Path $files (Comp-Big $c)
        if (-not (Test-Path -LiteralPath $src)) { Say "  安装包里缺少 $($g.Kind)\$(Comp-Big $c)" 'Red'; return $false }
        Copy-Item -LiteralPath $src -Destination (Join-Path $g.Dir ("Data\" + (Comp-Big $c))) -Force
    }
    # 字符串表要压过官方语言包，所以插在加载语言包的那份配置的最前面。新版本配置通过 add-config
    # 一路引用旧版本（1.13 → 1.12 → … → 1.0），只改链条上最靠前、带语言包的那份，同一个包不重复加载。
    $skus = @(Get-ChildItem -LiteralPath $g.Dir -Filter '*.SkuDef' | Where-Object { $_.Name -match $SkuRe })
    $hasLang = @{}; $next = @{}
    foreach ($f in $skus) {
        $t = Read-Raw $f.FullName
        if ($t -match $LangBigRe) { $hasLang[$f.Name.ToLower()] = $true }
        $m = [regex]::Match($t, '(?mi)^[ \t]*add-config[ \t]+(\S+)')
        if ($m.Success) { $next[$f.Name.ToLower()] = $m.Groups[1].Value.ToLower() }
    }
    $covered = @{}
    foreach ($n in @($hasLang.Keys)) {
        $seen = @{}; $cur = $next[$n]
        while ($cur -and -not $seen.ContainsKey($cur)) { $seen[$cur] = $true; $covered[$cur] = $true; $cur = $next[$cur] }
    }
    $haveLocale = Test-Path -LiteralPath (Join-Path $g.Dir "Data\$LocaleBig")
    $made = 0
    foreach ($f in $skus) {
        $key = $f.Name.ToLower()
        if (-not $hasLang.ContainsKey($key) -or $covered.ContainsKey($key)) { continue }
        $lang = if ($f.Name -match $SkuRe) { $Matches[2] } else { $f.Name }
        $lines = @($want | ForEach-Object { "add-big Data\" + (Comp-Big $_) })
        if ($lang -ne 'chinese_t' -and $haveLocale) { $lines += "add-big Data\$LocaleBig" }
        $first = [regex]::Match((Read-Raw $f.FullName), '(?mi)^[ \t]*add-big[ \t]')
        Insert-Lines $f.FullName $first.Index $lines
        Say "  [$lang] 简体文字已在 $($f.Name) 里加载（原文件已备份）"
        $made++
    }
    if ($made -eq 0) { Say '  没有找到加载语言包的配置，简体文字没有装上。' 'Red'; return $false }
    return $true
}

function Set-Voice($g, [string[]]$want) {
    $files = Join-Path $Here $g.Kind
    # 带字母的组件改语音，需要配套的长度表（core）；过场视频这类整文件替换的组件没有字母，不需要
    $letters = -join @($VoiceComp | Where-Object { $want -contains $_ } | ForEach-Object { $CompLetter[$_] })
    $core = Join-Path $files "core\CNVoice_core_$letters.big"
    if ($letters -and -not (Test-Path -LiteralPath $core)) { Say "  安装包里缺少 $($g.Kind)\core\CNVoice_core_$letters.big" 'Red'; return $false }
    foreach ($c in $want) {
        $src = Join-Path $files (Comp-Big $c)
        if (-not (Test-Path -LiteralPath $src)) { Say "  安装包里缺少 $($g.Kind)\$(Comp-Big $c)" 'Red'; return $false }
        Copy-Item -LiteralPath $src -Destination (Join-Path $g.Dir ("Data\" + (Comp-Big $c))) -Force
    }
    # 语音长度表必须和装上的组件完全对应，所以按组合挑对应的那一份
    if ($letters) { Copy-Item -LiteralPath $core -Destination (Join-Path $g.Dir "Data\$CoreBig") -Force }

    # 不新建配置、不改版本号：在每种语言最底层的配置里（写着 add-big Data\EnglishAudio.big 的那份，
    # 一般是 *_1.0.SkuDef），紧挨着英文语音包那一行的前面插入本 MOD 的几行。
    # 所有版本（1.12、1.13、Steam 固定的 -runver……）最后都会加载这份配置，所以都能生效。
    $lines = @($want | ForEach-Object { "add-big Data\" + (Comp-Big $_) })
    if ($letters) { $lines += "add-big Data\$CoreBig" }
    $made = 0
    Get-ChildItem -LiteralPath $g.Dir -Filter '*.SkuDef' | Where-Object { $_.Name -match $SkuRe } | ForEach-Object {
        $lang = if ($_.Name -match $SkuRe) { $Matches[2] } else { $_.Name }
        $text = Read-Raw $_.FullName
        $m = [regex]::Match($text, '(?mi)^[ \t]*add-big[ \t]+Data\\EnglishAudio\.big[ \t]*\r?$')
        if (-not $m.Success) { return }
        Insert-Lines $_.FullName $m.Index $lines
        Say "  [$lang] 已在 $($_.Name) 里加载（原文件已备份）"
        $made++
    }
    if ($made -eq 0) { Say '  没有找到使用英文语音的语言配置，已撤销。' 'Red'; return $false }
    return $true
}

function Check-Audio($g) {
    $expect = $Pkg.games.($g.Kind).'EnglishAudio.big size'
    $audio = Join-Path $g.Dir 'Data\EnglishAudio.big'
    if (-not (Test-Path -LiteralPath $audio)) { Say '  这个游戏没有英文语音包（EnglishAudio.big），本 MOD 不适用，跳过。' 'Yellow'; return $false }
    $actual = (Get-Item -LiteralPath $audio).Length
    if ($expect -and $actual -ne $expect) {
        Say "  注意：你的 EnglishAudio.big 和制作 MOD 时用的版本不同（$actual / $expect 字节）。" 'Yellow'
        if (-not $Silent) {
            $ans = Read-Host '  仍要安装吗？可能出现无声或报错，可随时卸载。输入 y 继续'
            if ($ans -ne 'y') { return $false }
        }
    }
    return $true
}

# ---------------------------------------------------------------- main
Say "红警3 中文配音 MOD v$($Pkg.version)  ——  $(if ($Action -eq 'install') { '安装' } else { '卸载' })" 'Cyan'
Say ''
$games = @(Find-Games)
if ($games.Count -eq 0 -and -not $Silent) {
    $pick = Ask-Folder
    if ($pick) { $k = Get-GameKind $pick; if ($k) { $games = @([pscustomobject]@{ Dir = $pick; Kind = $k }) } }
}
if ($games.Count -eq 0) { Say '没有找到《红警3》或《起义时刻》的安装目录。' 'Red'; Done 1 }

# 选组件（在请求管理员权限之前问，提权后的窗口直接用这次的选择）
$installed = @($games | ForEach-Object { Get-Installed $_ } | Sort-Object -Unique)
if (-not $PSBoundParameters.ContainsKey('Components')) {
    if ($Silent) { $sel = $AllComp }
    elseif ($Action -eq 'install') {
        $pre = if ($installed.Count) { $installed } else { $AllComp }
        $sel = Ask-Components '安装中文配音' '勾选要安装的部分（已经装了的已勾上；取消勾选的会被卸载）：' $AllComp $pre
    } else {
        if ($installed.Count -eq 0 -and -not (@($games | Where-Object { (Get-ChildItem -LiteralPath $_.Dir -Filter '*.SkuDef' | Where-Object { (Read-Raw $_.FullName) -match $MarkerRe }) }).Count)) {
            Say '没有发现本 MOD 的文件。' 'Green'; Done 0
        }
        $offer = if ($installed.Count) { $installed } else { $AllComp }
        $sel = Ask-Components '卸载中文配音' '勾选要卸载的部分（全部勾选 = 完全恢复原版）：' $offer $offer
    }
    if ($null -eq $sel) { Say '已取消。' 'Yellow'; Done 0 }
    $Components = if ($sel.Count) { $sel -join ',' } else { 'none' }
}
$chosen = Parse-Components $Components

# 游戏装在受保护目录（如 Program Files）时需要管理员权限
$needAdmin = @($games | Where-Object { -not (Test-Writable $_.Dir) }).Count -gt 0
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($needAdmin -and -not $isAdmin) {
    Say '需要管理员权限，正在请求……'
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$($MyInvocation.MyCommand.Path)`"", '-Action', $Action,
                 '-Components', $(if ($chosen.Count) { $chosen -join ',' } else { 'none' }))
    $argList += @('-GameDir', "`"$(($games | ForEach-Object { $_.Dir }) -join '|')`"")
    if ($Silent) { $argList += '-Silent' }
    $p = Start-Process powershell.exe -ArgumentList $argList -Verb RunAs -Wait -PassThru
    exit $p.ExitCode
}

$ok = 0
foreach ($g in $games) {
    $label = if ($g.Kind -eq 'uprising') { '起义时刻' } else { '红警3 原版' }
    Say "$label：$($g.Dir)" 'White'
    if (-not $Pkg.games.($g.Kind) -or -not (Test-Path -LiteralPath (Join-Path $Here $g.Kind))) {
        $pack = if ($g.Kind -eq 'uprising') { '起义时刻' } else { '原版' }
        Say "  这个安装包不含$label 的文件，跳过。请下载「$pack」版或「完整版」。" 'Yellow'; Say ''; continue
    }
    # 游戏运行时文件被占用，装到一半会出错：先检查，什么都不改
    $run = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { ($_.ProcessName -match '^ra3' -or $_.ProcessName -like '*.game') -and (-not $_.Path -or $_.Path.StartsWith($g.Dir.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) } | ForEach-Object { $_.ProcessName } | Sort-Object -Unique)
    if ($run.Count) { Say "  游戏正在运行（$($run -join '、')），请先完全退出游戏再运行。这个游戏什么都没有改动。" 'Red'; Say ''; continue }
    try {
        $have = @(Get-Installed $g)
        $want = if ($Action -eq 'install') { $chosen } else { @($have | Where-Object { $chosen -notcontains $_ }) }
        if (@($want | Where-Object { $VoiceComp -contains $_ }).Count -gt 0 -and -not (Check-Audio $g)) { Say ''; continue }
        if (Set-Components $g $want) {
            if ($want.Count) { Say ("  已安装：" + (($want | ForEach-Object { $CompName[$_] }) -join '、')) 'Green' }
            else { Say '  已完全卸载，恢复原版。' 'Green' }
            $ok++
        }
    } catch {
        Say "  出错：$($_.Exception.Message)" 'Red'
    }
    Say ''
}
if ($Action -eq 'install' -and $ok -gt 0) { Say '完成！正常从 Steam / EA App 启动游戏即可。以后想增减组件，再运行一次「安装.bat」或「卸载.bat」。' 'Green' }
Done $(if ($ok -gt 0) { 0 } else { 1 })
