# 交接：第二阶段收尾

状态与路线以 `docs/phase2_scope.md` 为准。

## 当前切片
2026-10-13 v1.0 已发布：B 站 BV1tGpr6REsK（审核中，P1 功能演示 / P2 实机演示）、小黑盒 https://www.xiaoheihe.cn/app/bbs/link/193661933 、百度网盘 + GitHub v1.0 Release（三个安装包 + SHA256SUMS + 空 manifest）。两个游戏装着 build 20261013-1101。
- 待办：收集评论里的问题，用 `ra3cv.py patch --base 20261013-1101` 出补丁，发到新的 GitHub Release（标 latest）。
- 2026-10-14：v1.0.1 已发布（GitHub Release v1.0.1 = 补丁 `patches/20261014-0037/` 全部文件 + 三个完整包 RA3-CNVoice-v1.0.1-*.zip）。补配 34 句坠机/坠落/娜塔莎喊话 + 磁爆坦克 2 句选中语音。完整包用 `ra3cv.py release --from-patch 20261014-0037` 打出：build 20261014-0037、base 仍是 20261013-1101，所以**下一个补丁照样 `--base 20261013-1101`**，装 1.0 的和装 1.0.1 完整包的都能收到。网盘文件夹（夸克 https://pan.quark.cn/s/61c5ce2c6548 、百度）由用户替换成 1.0.1 包，链接不变。
- N 网页面：https://www.nexusmods.com/commandandconquerredalert3/mods/16 （1.0.1 完整版一个文件）。
- 打包工具两处隐患已修（2026-10-15，带测试）：`cmd_patch` 会重新带上同一 base 下以前补丁动过的条目，dist 里少了以前发过的文件直接报错；`verify_dist_matches_patch` 检查全部组件「相对 base 的改动 ⊆ 补丁条目」。原记录如下：
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
  - RTX Remix：自写 d3d9 中间层（现在在 [RA3-CampaignLab](https://github.com/77652189/RA3-CampaignLab) 的 `experimental/rtx-remix/`，说明见其 README）已能让 Remix 光追单位和建筑，光影正确；地形、水面、贴错图（发青）、对局界面缺失、残影未解决。Remix 自带的地形烘焙还原不了红警3 在着色器里做的三层图集混合，要走得自己烘一张俯视图。游戏每轮测完都已恢复（原 d3d9.dll sha 646e70e3…）。
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

## v1.1（2026-10-17 已发布）
- GitHub Release v1.1（latest）：三个完整包 RA3-CNVoice-v1.1-{full,ra3,uprising}.zip + SHA256SUMS.txt + 补丁 `patches/20261017-0012/` 全部 142 个文件（含 manifest.json、patch.json）。线上 latest manifest 已核对与本地一致。
- 完整包是**新 base**：build 20261017-0012（`ra3cv.py release`，不带 --from-patch），索引 `releases/20261017-0012.json`。补丁 20261017-0012 是对 base 20261013-1101 的累积补丁，给装 1.0 / 1.0.1 / 1.0.2 的玩家；两者 build 号相同，安装器按 base 选补丁，无冲突。
- 内容 = 下面「1.0.2 之后已改」全部 + 安装器按长度和 sha256 复用缓存里的同名文件（不再重复下载）+ 安装器 2026-10-14 那批修复 + 试听索引偏移。TEMP_ 占位语音用户决定不配。
- **下一个补丁一次带两份（2026-10-17 已支持）**：`ra3cv.py patch --base 20261017-0012 20261013-1101 --version 1.1.x --notes "…"`。一个 `patches/<build>/` 里每个 base 一条 manifest 条目：组件包文件名带 base（`ra3_<base>_CNVoice_patch_X.big`），语音长度表两条共用；第二条的 build 是 `<build>.<base>`（安装器按 build 分缓存目录，且任何更晚的时间戳都排在它后面）。已验证：真实 dist 空跑时老玩家那份与已发布 1.1 补丁逐字节一致、1.1 那份为空；v1.0 时期和当前安装器在本地假服务器上都只取自己 base 的那条（scratchpad/guitest/multibase_test.py）。补丁文件夹不再写 patch.json，`earlier_patch_entries` / `release --from-patch` 改读各文件夹的 manifest.json。
- `releases/` 里两个已发布的索引（1101、0012）已进仓库；`patches/` 含音频不进仓库，但**必须留在本地**：cmd_patch 要读同一 base 下以前补丁的 .big（earlier_patch_entries）。
- 网盘已由用户换成 1.1（N 网待确认）。B 站：动态 https://t.bilibili.com/1260086427628077077 + 置顶评论（320645749168）下回复 rpid 320989712512；小黑盒按用户意见不发。文案 docs/publish/v1.1公告.txt。

## 配音质量工程化（2026-10-17，进行中）
- 抽检：`tools/qa_sample.py`（固定种子随机抽句、人标标签，英文改用按演员开口截的 movie_clean）。r1：过场 100 句，缺陷约 15%（语气不对 8、音色不像 4、停顿怪 3；"念错"多为抽检页英文片段截错，已排除）。标签 work/qa/r1/labels.csv。
- 自动裁判检验（AUC，0.5=瞎猜）：现有 CER/停顿/时长 ≈0.5；`tools/qa_features.py`（对演员：时长、音高、起伏、响度起伏、亮度"用力程度"、声纹、尾音）最高为亮度 0.77；`tools/qa_emotion.py`（emotion2vec+，独立环境 third_party/emo-venv）≈0.5～0.63。
- 力度试点 `tools/pilot_effort.py`：40 句"比演员亮 >5 dB"重生成并按接近演员挑选，盲听新 13 / 旧 21 / 平 6 → 力度/音高匹配≠语气对，方向放弃。配对结果 work/qa/pairs_effort.csv。
- 短句试点 `tools/pilot_short.py`（sfs01）：拆块拼接不可用；口语短句整句生成更稳但感情偏平；发布版感情最好。只适合作为问题句的补救候选。
- 结论：客观缺陷（念错、多音字、串人、残留英文、音量、口型时间）可自动化；"语气"目前只能人判，工程化方向是机器生成+初筛、人在快速挑选页批量拍板，并积累标签做未来裁判模型的评测集。

## v1.1.1（2026-10-17 已发布，补丁）
- GitHub Release v1.1.1（latest）= `patches/20261017-0329/` 全部 150 个文件，一份清单两条：build 20261017-0329（base 20261017-0012，1.1 玩家，约 41 MB）和 20261017-0329.20261013-1101（base 1101，老玩家累积约 1 GB）。线上清单已核对；GitHub 下载支持 Range（206）。
- 只发补丁，没出完整包：安装器的断点续传仍要等下一次完整包。
- B 站 BV1tGpr6REsK 编辑后重新提交审核（2026-10-17）：P1 重剪（开场直接库可夫中文，去掉 9 秒无声文字卡；B 站反馈 3 秒跳出率高）、P2 去标题卡且录像里的简报/通话换成 1.1.1 配音（`patch_gameplay_audio.py`，含 afs07 谭雅）、新增 P3「1.1 更新对比」（`docs/article/make_update_video.py`）；简介加了 1.1.1 说明、更新包大小和安装器校验码。经验：开头第一秒就要有人声，说明叠在画面上。下一个补丁照样 `--base 20261017-0012 20261013-1101`。

## 1.1.1 的改动（2026-10-17）
- 多音字筛查：`tools/polyphone_audit.py`（全部台词的多音字 + Whisper 听写对照）→ `tools/polyphone_score.py`（把字换成各读音的同音字，让 Whisper 按声音打分；只比声母韵母，声调分不出；按组校准去掉系统偏差）→ `tools/polyphone_page.py` 试听页。63 句候选里用户确认念错 9 处，加上同词的地名共 18 句重配：戛纳 5、海参崴 7、落空 2、就落那儿、伤得多重、朝步兵、一模一样（三种写法都不行，改说法「本是一体！」，字幕同步）。
- `work/terms/pronounce.json` 支持 `assets`（只对指定台词生效）。经验：IndexTTS2 认带声调拼音（`WEI1`、`ZHONG4`、`CHAO2`、`LUO4` 有效），但「戛纳」「落空」写拼音无效，改同音字（颊、洛空）才对；改完必须听，不能只看打分。
- 旧录音在 `archive/polyphone_redub/`，落选候选在 `archive/choose_rejected/`。与 v1.1 比：单位/任务 7 句、过场 7 个、起义字幕文件有变，其余不变。
- 安装器断点续传（见「发补丁」），未进已发安装包。

## 1.0.2 之后已改（2026-10-16，已随 v1.1 发布）
- 副官补配 5 句（EA 拼错前缀，原来是英文）：Svea_UltraNagnticSatellteReady「终极磁力卫星准备完毕！」（界面名也由“超磁力卫星”改为“终极磁力卫星”）、Svea_MagnticSingularityReady、Svea_ / Ivea_RedAlertAct、Ieve_SecurityPointGranted。全量英文排查（tools/english_audit.py，work/english_audit/）只找到这些；其余是 Whisper 幻觉、惨叫、背景广播和 TEMP_ 占位。
- 「弹」读音：work/terms/pronounce.json，配音时 弹→蛋（弹性/动弹除外），字幕不变；23 句高风险（中弹/装弹/补弹/一弹/弹舱…）已重配，单位里普通“炸弹/导弹”没重配。
- 过场参考音改为从实测开口截取（clean_refs.py）；545 句（被前一人声音污染的 414 + speakers.py 新查出的）重配，keep_better 择优：395 句换新（86 句旧版音高明显不对）、150 句留旧。串人确认的 4 句（达莎、宾汉姆、切尔登科、库可夫）已修。
- 复查（2026-10-16 晚）：tools/check_refs.py 用 Whisper 核对新参考音是否真是这句台词，15 段截错（电话铃、别的台词）→ 记入 work/speakers/bad_onset_refs.json（clean_refs 对它们改回按字幕截），其中已换新的 6 句退回旧版；换新后多了停顿/拖长且旧版音高正常的 5 句也退回。最终过场换新 389 句。jfs07_02「谢谢，父亲」原为女声，ref_override→R_jfs07_31 重配为男声。仍拿不准 4 句（work/voice_audit/doubtful.json）列在试听页最后，等用户听。新旧音色明亮度中位比 1.00、响度差 +0.1 dB，无系统偏移。
- 全量过场声纹检测（2026-10-16 夜）：check_refs 核实全部 2782 段参考音（2723 段含本句台词，work/voice_audit/ref_text_all.csv）；voice_audit 只用核实过的参考比对，pYIN 复测音高后，训练关等大部分「男女颠倒」是音高测量误差（声纹相似 0.6–0.83）。fix_swaps.py 对 4 句借同一演员参考重配，均未更像本人，已全部退回（配置也撤回）。拿不准的 11 句列在试听页最后（work/voice_audit/doubtful.json），只能人耳判断。mission 批次已支持 ref_override（work/speakers/ref_override_mission.json，目前为空）。
- 用户试听（2026-10-17）：11 句拿不准的里，U_chwinfs_23「(Ah, hell...)」原声无人声→不配音（voices 移到 archive/silent_lines，字幕保留）；U_ath02kj02_03、R_sfs00_26、U_ch12mv02_01 语气不对→ choose_takes.py 出三个候选，用户都选 A；其余 7 句没问题。与 v1.0.2 比：原版 73 / 起义 23 个过场有变，正好是含改动句子的那些。
- fx.py：P0 改为原样复制；voices/movie 已按 archive/voices_movie_0430 还原并同步 clean（之前 fix14 留下的不一致曾让 fx 回退已发布台词）。
- 验证：重建后与 v1.0.2 比，原版 74 / 起义 21 个过场有变，正好是含换新句子的那些；语音包只重编码改动的句子。试听：work/review/index.html（tools/review_page.py）。
- 发布前要定：这些改动的过场补丁仍约数百 MB（补丁累积 + 旧安装器不复用下载），建议和“安装器按校验值复用下载”一起出完整包。

## v1.0.2（2026-10-16 已发布）
- GitHub Release v1.0.2 = `patches/20261016-0023/` 全部 136 个文件；base 仍是 20261013-1101，所以下一个补丁照样 `--base 20261013-1101`。只发了补丁，没有新完整包（新玩家装 1.0.1 完整包后检查更新）；安装器修复（151eb34）和试听索引的偏移仍要等下一次完整包。
- 内容：1054 句过场按演员开口对齐（work/movie_offsets.json，字幕保持原版时间）、谭雅 R_afs07_08 重配、停顿处漏掉的英文、被压太小声的中文。
- B 站：动态 https://t.bilibili.com/1259701847713644552 + 置顶评论（rpid 320645749168）下回复。内置浏览器的 B 站登录会丢（蓝屏后要用户重新扫码）。
- 感情试点（work/pilot/afs07，tools/pilot_emotion.py）：A/B/C 用户盲听都不理想（还原度、连续性、口型）。根因：过场参考音是从混音里分离的、逐句独立生成、中文比英文长。待用户在「暂停 / 针对根因再试 / 先调研新模型」中选。

## 过场配音对齐演员开口（2026-10-15/16，已完成）
- 已证实：全屏过场（afs/sfs/jfs、mm 简报）原版字幕普遍比演员开口早 1.2–1.7 秒（A01MM01 画面：字幕 2.3 s 时 Krukov 还在走进画面，3.6 s 开口），通话小窗（th）晚约 0.7 秒。中文过去按字幕时间放 → 比口型早。决定：中文对齐演员开口，字幕保持原版时间。
- 工具 `tools/align_movies.py`：`transcribe`（Whisper 逐词时间戳，限流，可续跑，按静音切 ≤25 s 段、max_new_tokens 200、显存不够自动对半切）→ `work/align/<游戏>/<过场>.json`；`offsets` → `work/align/report.csv` + `work/align/offsets.json`（提议值；规则：第一个词「结束点」附近最后开始的人声段为开口，|偏移|≥0.35 s 才挪，邻句一致时补上没认出的句子）。试跑的 7 个过场和手工测的 4 句全部吻合。
- 进度：831 个过场里转写完 632 个，接着跑 `python -I -X utf8 tools/align_movies.py transcribe`（已完成的自动跳过）。
- 下一步：`offsets` → 看分布和异常值 → 把 offsets.json 合进 `work/movie_offsets.json` → `ra3cv.py build`（只重编码受影响的过场）→ 用 scratchpad 的 leftover_en / quiet_dub 检测复查 → 打包工具两处隐患（见上）→ 1.0.2。之后：编码器按声道并行。

## 构建缓存（2026-10-14 改）
- 语音包按句缓存在 `work/voice_cache/<游戏>/`（键 = wav 内容 + 原版音频 + 资源格式 + 编码代码），没命中的句子 7 进程并行编码。
- 过场缓存（`work/movie_cache/`）的键是「准备阶段的结果」（每句的位置、速度、音量后的整条配音轨 + 英文去除范围）+ 混音编码代码，不再是 movie.py 全文：改放置/音量算法时只有结果真变了的过场才重编码。改 `movie.mix` 及其调用的函数、eaxa.py、vgm.py 会让全部过场重编码（这是对的）。
- 实测：什么都没变 1 分 41 秒；只动一个过场约 5 分钟（长过场的 Python EA-XA 编码本身要 4 分钟）；首次/编码代码变了约 12 分钟（以前 110 分钟）。
- `ra3cv.py build --movies afs07 a07th08`：只重建这些过场到现有 dist，其余直接取缓存，build.json 标 partial；release 和 patch 会拒绝 partial 或 test 构建，发版前跑一次完整 `build`。

## 战役扩展与测试台（已迁出）
- 新战役 / 新地图 / 新单位 / 引擎工具链 / 测试台已拆到独立仓库 RA3-CampaignLab（`..\RA3-CampaignLab`，https://github.com/77652189/RA3-CampaignLab），交接见那边的 HANDOFF.md 与 docs/plan.md。

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
- 改完台词照上面 1–3 步、`ra3cv.py build` 后：`python -I -X utf8 ra3cv.py patch --base <玩家可能装着的每个正式版 build，新的在前> --version 1.x --notes "改了什么"`
- 把 `patches/<新 build>/` 里**所有文件**（扁平命名，含 manifest.json）作为一个新的 GitHub Release 附件上传，标为 latest。
  补丁对各自的 base 累积，manifest 每个 base 只放最新一条；安装器装新补丁前会先清掉旧补丁。
- 备用下载地址（加速前缀）写在 `UPDATE_MIRRORS`，会随 manifest 下发。
- 本地验证：`scratchpad/guitest/update_test.py`（假服务器 + 假游戏目录，含直连失败走备用地址、旧补丁清理）。
- 断点续传（2026-10-17，**还没进已发的安装包**，随下一次完整包发出）：下载中断留下的 `.part` 下次用 Range 接着下（服务器回 200 就从头下，续传位置不对就报错重试，校验失败删掉重下）。验证：`scratchpad/guitest/resume_test.py <exe>`（第一次下到 40% 断开）；多 base 清单：`multibase_test.py <exe>`。

## 硬约束（原文）
- 停任务只能按 PID 或完整命令行：先停 pipeline，再停 dub 子进程，删掉写了一半的 wav。
- 长时间显卡任务开跑前先问用户要不要限流。
- 不改游戏原文件，只用安装器的方式：备份后插入 SkuDef。不提交 git，不对外发布。下载任何东西都要用户明确同意。
- heredoc 里的反斜杠会被吃掉：带 `\` 的路径用 `chr(92)`，或者直接用 Edit 工具改。
- 字幕和界面文字以配音为准，不为对齐官方字幕去重配。
