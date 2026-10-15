# 交接：第二阶段收尾

状态与路线以 `docs/phase2_scope.md` 为准。

## 当前切片
2026-10-13 v1.0 已发布：B 站 BV1tGpr6REsK（审核中，P1 功能演示 / P2 实机演示）、小黑盒 https://www.xiaoheihe.cn/app/bbs/link/193661933 、百度网盘 + GitHub v1.0 Release（三个安装包 + SHA256SUMS + 空 manifest）。两个游戏装着 build 20261013-1101。
- 待办：收集评论里的问题，用 `ra3cv.py patch --base 20261013-1101` 出补丁，发到新的 GitHub Release（标 latest）。
- 2026-10-14：v1.0.1 已发布（GitHub Release v1.0.1 = 补丁 `patches/20261014-0037/` 全部文件 + 三个完整包 RA3-CNVoice-v1.0.1-*.zip）。补配 34 句坠机/坠落/娜塔莎喊话 + 磁爆坦克 2 句选中语音。完整包用 `ra3cv.py release --from-patch 20261014-0037` 打出：build 20261014-0037、base 仍是 20261013-1101，所以**下一个补丁照样 `--base 20261013-1101`**，装 1.0 的和装 1.0.1 完整包的都能收到。网盘文件夹（夸克 https://pan.quark.cn/s/61c5ce2c6548 、百度）由用户替换成 1.0.1 包，链接不变。
- N 网页面：https://www.nexusmods.com/commandandconquerredalert3/mods/16 （1.0.1 完整版一个文件）。
- **发 1.0.2 前必须先改打包工具**（v1.0.1 复查发现，已发的包不受影响）：
  1. `cmd_patch` 只收"和 1101 不同"的条目。1.0.2 若把 0037 改过的条目改回原样、或删掉 0037 新增的条目，装 1.0.1 完整包的玩家组件包里还是 0037 的音频，长度表却换成 1.0.2 的，会出现截断或无声。改法：同一 base 下以前补丁动过的条目一律收进新补丁；删除条目补丁表达不了，直接报错。
  2. `verify_dist_matches_patch` 只查了"补丁里的条目 dist 里一样"，要改成"dist 相对 1101 的改动集合正好等于补丁条目集合"，eva/mission/text 也要查。
- 安装器修复（2026-10-14，代码已改、已测，**还没进已发的安装包**，随下一次完整包发出）：在线更新后用新版安装器做故障诊断不再误报"文件不完整"；旧标记缺 base 时回退到它自己的 build；连接 15 秒 / 读取 30 秒超时，失败提示去网盘下完整包；"检查更新"不能重复点。
- 画质探索（2026-10-14，已结束，不做进产品）：AI 放大贴图 2 倍在正常视距下看不出区别；社区 PBR 着色器（NordLicht，ModDB v3.1，MIT）在 1.13 上能用，但观感提升有限，用户决定不再投入。留给以后的经验：
  - `-modConfig` 的 skudef 必须命名为 `名字_版本号.skudef`（如 `X_1.0.skudef`），否则任何 mod 都会在启动时崩溃（MSVCR80 0xc000000d）。
  - 用 SDK 做"同 id 覆盖"的 mod.manifest 不生效；在 mod 的 BIG 里放整份替换的 `data\static.*`（把资源拼进原版 static 流、改条目长度、保留校验值）能生效。之前"战役关卡写死"的结论因此存疑，CampProbe 的数据很可能根本没被读到。
  - EA 官方 mod 资料（github.com/electronicarts/CnC_Modding_Support，GPL v3 附加条款）有红警3 / 起义时刻的着色器源码，以及可能更新过的 Xml / Schemas。用 2010 版 fxc 编译要修两处：空宏参数、`lit()` 的 float4 参数。
  - 1.13 是 Steam 官方补丁（`Data\RA3_1.13.game`），用 mod 启动时跑的就是它。
- 画质（续，2026-10-14 晚）：
  - 后期增强（深度图做 SSAO + 锐化 + 调色）：引擎每帧有线性深度图 `WW3D.DepthTexture`，改 `PostFX_LookupTable.fx` 能读到；调色、锐化无瑕疵，SSAO 单 pass 有颗粒和斑块，没调完。测试 mod 在 `文档\Red Alert 3\Mods\CNVPic*`。mod 名（版本号前）最多 15 个字符、不能带下划线。
  - RTX Remix：自写 d3d9 中间层（`experimental/rtx-remix/`，说明见其 README）已能让 Remix 光追单位和建筑，光影正确；地形、水面、贴错图（发青）、对局界面缺失、残影未解决。Remix 自带的地形烘焙还原不了红警3 在着色器里做的三层图集混合，要走得自己烘一张俯视图。游戏每轮测完都已恢复（原 d3d9.dll sha 646e70e3…）。
  - 讨论过的路线和结论：换引擎完整重写最贵（要重做模拟层）；只做战役能去掉联机但仍重；最划算的架构是"保留原版模拟、只换表现层"（中间层就是这条边界）。用户倾向 PVE 战役内容。
- 明天待选（用户今天到此为止）：
  1. 战役扩展验证：用"整包顶替 static/资源流"的办法重测能否加新关卡或替换某关内容（CampProbe 的 mod.manifest 很可能没被读）。这是战役路线成立的前提。
  2. 视频通话式过场样片：虚构人物 + 我们的配音 + Wan2.2-S2V（Apache 2.0）。MiniMax H3 不能用：许可证排除美国（用户在美国）且禁止冒用他人形象。新剧情不用原演员的脸和声音说新台词。下载模型、占用 GPU 前都要先问。
  3. 1.0.2（先修打包工具两处隐患）。
- 小黑盒置顶评论：不带网址的"去 N 网搜索 RA3 Chinese Voice-over"可以置顶（2026-10-14 已置顶）；带 N 网网址的评论能发，但置顶会被判"不符合规范"。
- 小黑盒只允许 N 网分发 mod：文章（193661933）正文和评论里不放任何下载指引。N 网页面文案在 docs/publish/N网页面.txt（内置浏览器过不了 Cloudflare，用户自己在 Edge 里建页面）。
- 已知未配：少数战役专用单位（豪华轿车、越野车、打捞船、雷达船、炸弹船、苏联火车/汽车、海军陆战队）用 EA 遗留的红警2 英文占位语音（TEMP_*，约 36 句），用户选择留到以后。
- 试听：安装器右上角“试听全部配音”，读 files/listen_index.json（tools/listen_index.py）直接从包里的 .big 解码播放（installer/gui/Listen.cs，与 Python 解码逐采样一致），不另带音频。
- 安装器和 ps1 现在在游戏运行时拒绝安装（按游戏目录判断进程）。
- 过场 14 句已用 work/speakers/ref_override.json 修好；停顿压缩不采用。
- 下一步（需用户确认）：推送 GitHub、建 v1.0 Release（空 manifest.json）。

## 构建缓存（2026-10-14 改）
- 语音包按句缓存在 `work/voice_cache/<游戏>/`（键 = wav 内容 + 原版音频 + 资源格式 + 编码代码），没命中的句子 7 进程并行编码。
- 过场缓存（`work/movie_cache/`）的键是「准备阶段的结果」（每句的位置、速度、音量后的整条配音轨 + 英文去除范围）+ 混音编码代码，不再是 movie.py 全文：改放置/音量算法时只有结果真变了的过场才重编码。改 `movie.mix` 及其调用的函数、eaxa.py、vgm.py 会让全部过场重编码（这是对的）。
- 实测：什么都没变 1 分 41 秒；只动一个过场约 5 分钟（长过场的 Python EA-XA 编码本身要 4 分钟）；首次/编码代码变了约 12 分钟（以前 110 分钟）。
- `ra3cv.py build --movies afs07 a07th08`：只重建这些过场到现有 dist，其余直接取缓存，build.json 标 partial；release 和 patch 会拒绝 partial 或 test 构建，发版前跑一次完整 `build`。

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
