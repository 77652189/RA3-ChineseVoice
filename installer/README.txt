红警3 / 起义时刻  AI 中文配音 MOD  v{VERSION}（{EDITION}）
==================================================

本安装包：{EDITION}。{EDITION_HINT}
（一共三种安装包：「原版」「起义时刻」「完整版」，内容完全相同，只是包含的游戏不同。）

这是什么
--------
把《命令与征服：红色警戒3》和资料片《起义时刻》的语音换成 AI 生成的普通话配音（音色克隆自原版配音），
并可选把游戏文字换成简体中文。阵亡惨叫、笑声等无台词的声音保持原样。

社区非盈利作品，仅供交流学习，请勿用于商业用途。

可以分别安装、分别卸载的部分：
  盟军单位语音 / 苏联单位语音 / 帝国单位语音 / EVA 战场播报
  指挥官语音：合作战役、遭遇战里友军指挥官的语音和士兵闲聊
  剧情对白：战役任务里的对话、单位介绍旁白、教学关讲解
  过场视频配音：剧情过场、任务简报、视频通话、AI 指挥官视频（只在安装包里包含时出现）
  简体中文文字：把游戏界面、单位说明、字幕等换成简体中文（由官方繁体中文版转换，
                台湾用语改为大陆用语），英文版和繁体中文版游戏都适用。
                附带的字体基于思源黑体（Noto Sans SC，SIL OFL 1.1 许可，见 files\字体许可证_OFL.txt）。
  高帧率 120 帧（默认不勾选）：附带开源插件 SAGE-Unlocked（作者 TheeHorse，GPL-3.0，见 files\fps），
                把游戏锁死的 30 帧解锁到 120 帧。不会超过显示器刷新率（60 Hz 屏就是 60 帧），
                电脑带不动时只是没那么流畅，游戏速度不会变快变慢。想改帧率：用记事本打开游戏目录
                Data\SAGEUnlocked.ini，把 fps= 改成 15 的倍数（144 Hz 屏填 135），重装时会保留你的设置。
                Data 里已有别的 d3d9.dll（ReShade、DXVK 等）时会自动跳过，不会覆盖。


安装
----
1. 解压整个文件夹（不要在压缩包里直接运行）。
2. 双击「{SETUP_EXE}」。
   - 会请求管理员权限（游戏一般装在 Program Files 里），点“是”。
   - Windows 可能弹出蓝色的“Windows 已保护你的电脑”：这是因为本安装器是个人制作、没有购买数字签名，
     点“更多信息”→“仍要运行”即可。不放心的话可以核对下面的校验码。
   - 会自动找到 Steam / EA App / Origin 版的游戏，原版和起义时刻都装了的话会一起列出。
     没找到时点“手动选择游戏目录”，选里面有 RA3.exe 或 RA3EP1.exe 的那个文件夹。
3. 勾选要安装的内容，点“安装 / 更新”。已经装了的会预先勾上，取消勾选的部分会被卸载。
4. 正常从 Steam / EA App 启动游戏即可，版本号不变（仍是 1.12 / 1.13），不影响联机选版本。

想先听听效果：运行安装器，点右上角的“试听全部配音”。一万多句配音按单位、关卡、过场分好类，
点一句就播放，也能按台词、单位名、人名搜索。不用先安装。

卸载
----
再次运行安装器，点“全部卸载”。被改动过的那几个配置文件会从备份原样恢复，本 MOD 的文件全部删除。
只想去掉某一部分：取消勾选它，再点“安装 / 更新”。

更新到新版本：在安装器右上角点“检查更新”，只下载改动过的部分（一般几 MB 到几十 MB），
不用重新下载整个安装包。也可以直接运行新版本的安装器，会自动替换旧版。

装了没效果？在安装器右上角点“故障诊断”，会逐项检查常见原因（下错版本、Steam 验证文件后
配置被还原、文件不完整、游戏正在运行、启动参数里有 -modconfig 等），并给出处理办法。
需要求助时点“复制诊断报告”，把内容发给作者即可。

安装器校验码（SHA-256）：
  {SETUP_SHA256}
（PowerShell 里运行 Get-FileHash "{SETUP_EXE}" 可以核对）

备用方式：安装器打不开时，可以运行 files 文件夹里的「备用-安装.bat」/「备用-卸载.bat」，效果相同。


兼容性说明
----------
- 原版和起义时刻使用各自的语音包，安装器会自动区分，不会装错。
- 不改版本号：联机常用的官方 1.12、1.13，以及 Steam 启动时固定的版本，都直接生效。
  做法是在每种语言最底层的配置文件（写着 add-big Data\EnglishAudio.big 的那一份，
  一般是 *_1.0.SkuDef）里，紧挨着英文语音包那一行的前面，加一行加载本 MOD。
  改动前会自动备份为 *.SkuDef.cnvoice-backup，卸载时原样恢复。
- 简体中文文字要压过官方语言包，所以加在“加载语言包的那份配置”（原版是 *_1.11.SkuDef，
  起义时刻是 *_1.0 / *_1.1）的最前面；英文版还会顺带加载繁中包 ChineseT.big 里的中文字体设置。
  同样有备份、卸载时原样恢复。
- 语音部分只给使用英文语音的语言配置安装（Steam 版的英文、繁体中文都属于这种）。
  如果你装的是德语、俄语等其他语音版本，会自动跳过。
- 在 Steam 里“验证游戏文件完整性”会把那份配置还原，MOD 随之失效；
  重新运行「安装.bat」即可。
- 联机：本 MOD 只替换声音和文字，不改动游戏数据和版本号，但没有在线上对战中实测过；
  如果遇到不同步或进不了房间，先卸载本 MOD 再联机。高帧率插件同理，可以单独取消勾选它。


手动安装（自动安装失败时）
--------------------------
以全部语音为例（files\ra3 是原版，files\uprising 是起义时刻）：
1. 把 CNVoice_allied.big、CNVoice_soviet.big、CNVoice_empire.big、CNVoice_eva.big、CNVoice_commander.big、
   CNVoice_mission.big 复制到游戏目录下的 Data 文件夹；再把 core\CNVoice_core_asevcm.big 复制过去并改名为
   CNVoice_core.big（文件名里的字母对应装了哪几部分：a 盟军 s 苏联 e 帝国 v 播报 c 指挥官 m 剧情对白，
   只装一部分时选对应字母的那份）。过场视频（CNVoice_movie.big，如果有）不需要长度表，照第 3 步加一行即可。
2. 在游戏目录找到写着 add-big Data\EnglishAudio.big 的配置文件，例如
   RA3_chinese_t_1.0.SkuDef、ra3_english_1.0.SkuDef、RA3EP1_english_1.0.SkuDef，
   先复制一份备份。
3. 用记事本打开，在 add-big Data\EnglishAudio.big 那一行的正上方加上：
       add-big Data\CNVoice_allied.big
       add-big Data\CNVoice_soviet.big
       add-big Data\CNVoice_empire.big
       add-big Data\CNVoice_eva.big
       add-big Data\CNVoice_commander.big
       add-big Data\CNVoice_mission.big
       add-big Data\CNVoice_core.big
   每种语言（english、chinese_t 等）各改一份。
   简体中文文字：把 CNVoice_text.big 也复制到 Data，在加载语言包的配置（原版 *_1.11.SkuDef，
   起义时刻 *_1.0 和 *_1.1）第一行 add-big 的上方加 add-big Data\CNVoice_text.big；
   英文版再在它下面加一行 add-big Data\ChineseT.big。
高帧率：把 files\fps 里的 d3d9.dll、CnCFpsUnlocker.dll、SAGEUnlocked.ini 复制到游戏的 Data 文件夹，删掉这三个文件就是卸载。
手动卸载：删除 Data\CNVoice*.big，再把第 2 步的备份还原回去。


声明
----
配音由 AI 语音合成（IndexTTS2 等）生成，音色参考原版配音。游戏版权归 Electronic Arts 所有。
如权利方提出异议，本 MOD 将及时下架或替换相关内容。
