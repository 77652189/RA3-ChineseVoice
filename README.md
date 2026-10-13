# 红警3 / 起义时刻 AI 中文配音 MOD

《命令与征服：红色警戒3》和资料片《起义时刻》的社区非盈利 AI 普通话配音：单位语音、EVA 播报、指挥官、剧情对白、过场视频，外加可选的简体中文文字。音色克隆自原版配音（IndexTTS2）。

**玩家下载：[百度网盘](https://pan.baidu.com/s/5oqzy02MrWkfMGjZQ18SbPQ)**，备用：[GitHub Releases](https://github.com/77652189/RA3-ChineseVoice/releases/latest)（附件 full = 完整版，ra3 = 原版，uprising = 起义时刻）。三个安装包选一个，不确定就下完整版。安装、试听、更新、故障诊断都在安装器里完成，说明见安装包里的「说明.txt」。

演示视频（B 站）：https://www.bilibili.com/video/BV1tGpr6REsK/　·　制作过程与踩坑长文（小黑盒）：https://www.xiaoheihe.cn/app/bbs/link/193635738

## 仓库里有什么

本仓库只有制作工具的代码和配置，**不含任何游戏文件、提取出的音频或生成的配音**。要自己重新生成，需要正版游戏。

| 目录 | 内容 |
|---|---|
| `ra3voice/` | 游戏格式读写：BIG 包、SkuDef、audio.bin / SNR、RefPack、EA-XA 视频音轨、CSF 文字 |
| `tools/` | 流水线：提取台词 → 识别 → 翻译合并 → 配音 → 挑选 → 音效 → 过场人声分离与回填 |
| `ra3cv.py` | 打包、发布、在线补丁 |
| `installer/` | 图形安装器（C# WPF，系统自带 csc 编译）与 PowerShell 备用安装脚本 |
| `tests/` | 格式与打包的回归测试 |
| `work/terms/` | 术语表（界面名称与配音统一用词） |

## 许可证

代码以 [GPL-3.0](LICENSE) 发布（与安装器将附带的帧率解锁插件 SAGE-Unlocked 一致）。许可证只覆盖本仓库的代码，不覆盖游戏素材和生成的配音。

## 声明

配音由 AI 语音合成生成，音色参考原版配音。游戏及其素材版权归 Electronic Arts 所有。如权利方提出异议，本项目将及时下架或替换相关内容。
