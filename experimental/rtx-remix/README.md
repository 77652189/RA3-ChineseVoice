# RTX Remix 实验（不随配音包发布）

红警3 只用着色器渲染，摄像机、模型矩阵和灯光都只作为着色器常量传给显卡，RTX Remix 识别不到。
这里的 `shim.cpp` 是一个 32 位 `d3d9.dll` 中间层：游戏 → 中间层 → `d3d9_remix.dll`（Remix 的 bridge 改名）。
它从着色器常量里取出这些数据，再用固定管线接口告诉 Remix。寄存器位置来自 EA 的 `RegisterMap.fxh`
（github.com/electronicarts/CnC_Modding_Support）：

| 内容 | 寄存器 | 中间层做的事 |
|---|---|---|
| ViewProjection | c119–c122（按列存放） | 透视：拆成 VIEW + 左手 PROJECTION；正交（界面、阴影图）：原样作为 PROJECTION |
| 摄像机位置 | c123 | 判断矩阵的存放方式 |
| 普通模型世界矩阵 | c124–c127 | 每次绘制前设为 WORLD（配合 `rtx.useWorldMatricesForShaders`） |
| 骨骼 | c128 起 | 写了骨骼就用单位 WORLD（顶点捕获已经是世界坐标） |
| 方向光 | c5–c10（颜色、指向光源的方向） | 转成 D3DLIGHT_DIRECTIONAL |

## 现状（2026-10-14，Remix 1.5.2）

- 能用光线追踪渲染出单位和建筑，阴影和反射正确（截图在会话里）。
- 未解决：地形和水面（多层贴图混合，Remix 只拿到一层）；部分物体选错贴图（青色）；对局界面不显示；
  放置建筑的红色提示被当成实体；镜头移动时有残影或条纹；开局到第一次部署前一片灰。
- 已知 bug：普通模型世界矩阵按"rows"解析时丢了平移（`push_world`，应取 `W[3][r] = g_world[r][3]`）。

## 安装（测试用，会替换游戏文件，测完必须恢复）

1. 备份 `Data\d3d9.dll`（SAGE-Unlocked 的 120 帧插件）。
2. `Data\d3d9.dll` ← 本目录编译出的中间层；`Data\d3d9_remix.dll` ← Remix release 包里的 `d3d9.dll`；
   `Data\.trex` ← Remix 的 `.trex`；`Data\rtx.conf` ← 本目录的 `rtx.conf`。
3. 恢复：放回备份的 `d3d9.dll`，删掉 `d3d9_remix.dll`、`.trex`、`rtx.conf`、`Data\rtx-remix`、`<游戏>\rtx-remix`。

编译：装 VS 2022 生成工具（C++）后运行 `build.bat`。

## shaders/

画质探索留下的工具：`compile.py` + `fix_noinit.py` 用 2010 版 fxc 编译 EA 着色器源码；
`cnv_enhance.fxh` 是后期 SSAO / 锐化 / 调色；`pack_shaders.py` 打成按路径顶替的 mod BIG；
`splice_static.py` 把贴图拼进整份 static 流；`boottest.ps1` 自动启动游戏判断是否崩溃（`-Bat` 测指定启动器，
`-Shot` 截图）；`FxLoad.cs` 用游戏同款 d3dx9_35 离线加载 .fxo。mod 的 skudef 必须叫 `名字_版本号.skudef`，
名字不超过 15 个字符、不含下划线。
