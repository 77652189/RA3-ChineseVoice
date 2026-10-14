# 交接：第二阶段收尾

状态与路线以 `docs/phase2_scope.md` 为准。

## 当前切片
2026-10-13 v1.0 已发布：B 站 BV1tGpr6REsK（审核中，P1 功能演示 / P2 实机演示）、小黑盒 https://www.xiaoheihe.cn/app/bbs/link/193661933 、百度网盘 + GitHub v1.0 Release（三个安装包 + SHA256SUMS + 空 manifest）。两个游戏装着 build 20261013-1101。
- 待办：收集评论里的问题，用 `ra3cv.py patch --base 20261013-1101` 出补丁，发到新的 GitHub Release（标 latest）。
- 2026-10-13：B 站简介已补小黑盒链接、夸克网盘 https://pan.quark.cn/s/61c5ce2c6548（与百度并列）。补丁 1.0.1 已在本地生成：`patches/20261013-2109/`（补配 34 句坠机/坠落/娜塔莎喊话），尚未发布。
- 试听：安装器右上角“试听全部配音”，读 files/listen_index.json（tools/listen_index.py）直接从包里的 .big 解码播放（installer/gui/Listen.cs，与 Python 解码逐采样一致），不另带音频。
- 安装器和 ps1 现在在游戏运行时拒绝安装（按游戏目录判断进程）。
- 过场 14 句已用 work/speakers/ref_override.json 修好；停顿压缩不采用。
- 下一步（需用户确认）：推送 GitHub、建 v1.0 Release（空 manifest.json）。

## 改一句台词的流程
1. 改 `lines/<mission|movie|...>_zh_*.json` 里对应 asset 的 zh → `python -I -X utf8 tools/merge_zh.py <批次>`
2. 删掉 `candidates/<批次>/<asset>_*.wav` → `third_party/index-tts/.venv/Scripts/python.exe -I -X utf8 tools/dub.py <批次> --takes 10 --only <asset>`
3. `python -I -X utf8 tools/pick.py <批次>` → `.venv python tools/fx.py apply <批次>`
4. `python -I -X utf8 ra3cv.py build` → `tests/test_pipeline.py` → `ra3cv.py release` → `ra3cv.py install --components all`
   （只改了界面文字/术语时，可只重建文字组件：`ra3cv.build_text`）

- **别整批重跑 pick.py 就直接发补丁**：pick 的打分含停顿检测，那段代码在部分批次最后一次 pick 之后改过，整批重跑会给已发布的台词换候选（2026-10-13 帝国 12 句）并让同组整条 EQ 曲线跟着变。重跑后用 `python -I -X utf8 tools/restore_from_install.py <批次…> --keep <这次要改的 asset…>` 从游戏里装着的正式版把其余台词还原回 voices/ 和 clean/，再 build、patch。还原后会剩几十句采样级（-75 dB）差异，可忽略。
- 坠机（VoiCrash）、坠落（VoiFal）、惊吓（VoiFear）是有台词的喊话，2026-10-13 起配音；阵亡（Die）仍保留原声（tools/nonverbal_probe.py 用 Whisper 核过）。pick 设计同组 EQ 时不计这几类，免得带偏整组。

## 发补丁（在线更新）
- 仓库：https://github.com/77652189/RA3-ChineseVoice（公开，只放代码；提交用 noreply 邮箱）。
  发 v1.0 时同时建一个 Release，附件里放 `{"patches": [], "mirrors": []}` 的 manifest.json，否则“检查更新”会报 404。
- 前提：正式版 `ra3cv.py release` 时 `UPDATE_URL`（环境变量 `CNVOICE_UPDATE_URL`）已指向
  `https://github.com/<owner>/<repo>/releases/latest/download/manifest.json`，且留着 `releases/<build>.json`。
- 改完台词照上面 1–3 步、`ra3cv.py build` 后：`python -I -X utf8 ra3cv.py patch --base <正式版 build> --version 1.0.x --notes "改了什么"`
- 把 `patches/<新 build>/` 里**所有文件**（扁平命名，含 manifest.json）作为一个新的 GitHub Release 附件上传，标为 latest。
  补丁对正式版累积，manifest 只放最新一个；安装器装新补丁前会先清掉旧补丁。
- 备用下载地址（加速前缀）写在 `UPDATE_MIRRORS`，会随 manifest 下发。
- 本地验证：`scratchpad/guitest/update_test.py`（假服务器 + 假游戏目录，含直连失败走备用地址、旧补丁清理）。

## 硬约束（原文）
- 停任务只能按 PID 或完整命令行：先停 pipeline，再停 dub 子进程，删掉写了一半的 wav。
- 长时间显卡任务开跑前先问用户要不要限流。
- 不改游戏原文件，只用安装器的方式：备份后插入 SkuDef。不提交 git，不对外发布。下载任何东西都要用户明确同意。
- heredoc 里的反斜杠会被吃掉：带 `\` 的路径用 `chr(92)`，或者直接用 Edit 工具改。
- 字幕和界面文字以配音为准，不为对齐官方字幕去重配。
