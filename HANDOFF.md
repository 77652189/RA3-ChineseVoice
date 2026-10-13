# 交接：第二阶段收尾

状态与路线以 `docs/phase2_scope.md` 为准。

## 当前切片
全部 8 个组件已打包并装进两个游戏，等用户游戏内检查（过场视频、字幕与配音一致性、界面名称）。

## 改一句台词的流程
1. 改 `lines/<mission|movie|...>_zh_*.json` 里对应 asset 的 zh → `python -I -X utf8 tools/merge_zh.py <批次>`
2. 删掉 `candidates/<批次>/<asset>_*.wav` → `third_party/index-tts/.venv/Scripts/python.exe -I -X utf8 tools/dub.py <批次> --takes 10 --only <asset>`
3. `python -I -X utf8 tools/pick.py <批次>` → `.venv python tools/fx.py apply <批次>`
4. `python -I -X utf8 ra3cv.py build` → `tests/test_pipeline.py` → `ra3cv.py release` → `ra3cv.py install --components all`
   （只改了界面文字/术语时，可只重建文字组件：`ra3cv.build_text`）

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
