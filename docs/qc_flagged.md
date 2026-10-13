# 自动质检仍标黄的条目（v1.0）

| 批次 | 条数 | 标黄 | 通过率 |
|---|---|---|---|
| 播报 | 426 | 2 | 99.5% |
| 盟军 | 1208 | 8 | 99.3% |
| 苏联 | 1295 | 21 | 98.4% |
| 帝国 | 1137 | 13 | 98.9% |

共 44 条。读音类多为两三个字的短喊话（Whisper 对短句听写不稳），断句类是句中仍有 0.12 秒以上的小停顿。

| 批次 | 资源名 | 原因 | 台词 | Whisper 听成 | 时长（新/原） |
|---|---|---|---|---|---|
| 播报 | `Aeva_FundsTransfer` | 断句 | 资金已转移。 | 资金已转移 | 1.63s / 1.34s |
| 播报 | `Seva_WarnChronosphereAct` | 断句 | 超时空传送仪已启动！ | 超时空传送仪已启动 | 1.97s / 2.54s |
| 盟军 | `AUAssau_VoiRetread` | 断句 | 追我们就是找死。 | 追我们就是找死 | 1.70s / 1.54s |
| 盟军 | `AUAssau_VoiSelectb` | 偏长 | 指挥部，请讲。 | 指挥部请讲 | 1.53s / 0.87s |
| 盟军 | `AUCentu_VoiMovee` | 偏长 | 是，长官。 | 是,长官! | 1.14s / 0.59s |
| 盟军 | `AUGuard_VoiMoved` | 读音 | 听头儿的。 | 挺投入的 | 0.59s / 1.01s |
| 盟军 | `AUHarbi_voiAttSpeca` | 读音 | 瞧那个。 | 超內閣 | 0.92s / 2.06s |
| 盟军 | `AUPeace_VoiAtke` | 读音 | 他完了。 | 看完了 | 0.62s / 0.97s |
| 盟军 | `AURipti_VoiRetreac` | 读音 | 撤！ | 恰! | 0.42s / 0.62s |
| 盟军 | `AUTanya_VoiSelUndFira` | 读音 | 我中弹了！ | 我中台了 | 0.67s / 0.95s |
| 苏联 | `SUAkula_VoiAttackc` | 读音 | 击沉他们！ | 清晨他們 | 0.90s / 1.21s |
| 苏联 | `SUComba_VoiMoved` | 读音 | 乐意效劳。 | 那一箱了 | 0.75s / 1.41s |
| 苏联 | `SUComba_VoiSelBatc` | 断句 | 这仗我一个人打赢。 | 这仗我一个人打赢 | 1.59s / 1.77s |
| 苏联 | `SUGrind_voiMovei` | 读音 | 那儿？ | 呐! | 0.51s / 0.57s |
| 苏联 | `SUGrind_voiMovLana` | 读音 | 回家咯。 | 回家喽 | 0.71s / 1.05s |
| 苏联 | `SUGrind_voiSelUnde` | 读音 | 哎哟！好疼！ | 哎呦好疼 | 0.98s / 1.50s |
| 苏联 | `SUHamme_VoiMovAttf` | 读音 | 那儿！ | 拿! | 0.42s / 0.77s |
| 苏联 | `SUHamme_VoiSelBatb` | 断句 | 好货接着来。 | 好货接着来 | 1.55s / 1.20s |
| 苏联 | `SUMigFi_VoiMovRelc` | 读音 | 需要补弹。 | 需要补碳 | 0.98s / 0.93s |
| 苏联 | `SUMorta_voiSelUndc` | 断句 | 靠得有点近了。 | 靠 得有點勁了 | 1.20s / 1.28s |
| 苏联 | `SUNatas_VoiCreatec` | 断句 | 娜塔莎·沃尔科娃。 | 娜塔莎·沃尔科娃 | 1.65s / 1.27s |
| 苏联 | `SUNatas_VoiCrec` | 断句 | 娜塔莎·沃尔科娃。 | 娜塔莎·沃尔科娃 | 1.59s / 1.27s |
| 苏联 | `SUReape_voiAttSpecd` | 断句 | 腿肯定没事。 | 腿肯定没事 | 1.29s / 1.46s |
| 苏联 | `SUReape_voiAttSpLaua` | 读音 | 哇啊！ | 哇!哈! | 0.71s / 0.87s |
| 苏联 | `SUSickl_VoiSelecte` | 读音 | 我们在这！ | 我们在这儿 | 0.65s / 0.80s |
| 苏联 | `SUSickl_VoiSelUndb` | 读音 | 中弹了！ | 中台了 | 0.53s / 0.71s |
| 苏联 | `SUSting_VoiMovLanc` | 读音 | 登岸！ | 等我 | 0.42s / 0.79s |
| 苏联 | `SUTesla_VoiAtkc` | 读音 | 合闸！ | 喝茶 | 0.75s / 1.30s |
| 苏联 | `SUTesla_VoiMovSpce` | 读音 | 熄灯。 | 西丹! | 0.79s / 0.96s |
| 苏联 | `SUTwinb_VoiAttacka` | 读音 | 清理干净。 | 清理乾淨 | 1.11s / 1.12s |
| 苏联 | `SUV4_VoiRetd` | 断句 | 撤退命令确认。 | 撤退命令確認 | 1.29s / 1.32s |
| 帝国 | `IUGigaN_VoiMovSpca` | 断句 | 地点已指定。 | 地点已指定 | 1.36s / 1.76s |
| 帝国 | `IUMCV_VoiMovef` | 读音 | 从速办理。 | 重塑办理 | 1.00s / 1.41s |
| 帝国 | `IUMCV_VoiSelecte` | 断句 | 每项计划都须审批。 | 每项计划都需审批 | 2.01s / 2.10s |
| 帝国 | `IUMecha_VoiSelUndFira` | 读音 | 中弹了！ | 中他了 | 0.71s / 0.72s |
| 帝国 | `IUNano2_VoiHlpMea` | 断句 | 纳米核心严重受损。 | 纳米核心严重受损 | 2.67s / 2.56s |
| 帝国 | `IUOreCo_VoiMovRfna` | 读音 | 运去入库。 | 運氣入庫 | 0.99s / 1.03s |
| 帝国 | `IUSeaWi_VoiSelectc` | 断句 | 声呐有发现吗？ | 生呢有发现吗 | 1.59s / 1.40s |
| 帝国 | `JUEngin_VoiSelectb` | 断句 | 我在此为您效劳。 | 我在此为您效劳 | 1.66s / 1.83s |
| 帝国 | `JUImper_VoiMovAttc` | 读音 | 讨伐蛮夷！ | 頭髮滿意 | 1.15s / 0.92s |
| 帝国 | `JUKingO_VoiAttackd` | 读音 | 撕碎！ | 死罪 | 1.78s / 1.28s |
| 帝国 | `JUKingO_VoiAttacke` | 读音、断句 | 乐意之至。 | 一致致 | 2.29s / 1.45s |
| 帝国 | `JUNagin_VoiSelBatd` | 读音 | 保持阵位！ | 保持正位 | 0.78s / 1.37s |
| 帝国 | `JUShino_VoiInfiltb` | 读音 | 乐意效劳。 | 愿意效劳 | 1.40s / 1.21s |
