# P3 方向二 沙盘骨架（第二步：真实路线三维可视化）

- 日期：2026-11-06
- 引擎：Godot 4.7.2
- 位置：`sandbox/`
- 截图：`docs/reports/sandbox_route.png`

## 一、已实现

| 能力 | 说明 |
|---|---|
| 路线导入 | 读取 `natlan_story_route.json`：33 个分 P、9 幕、总时长 70742 秒 |
| 三维坐标 | 分 P 世界坐标（x/y/z，米）缩放 0.01 后落点，`estimated=true` 原样标注 |
| 可视化 | 路线连线 + 分 P 节点球（按幕着色）+ 当前分 P 高亮胶囊 + 3D 标签 |
| 时间线 | 按分 P 时长推进；空格暂停/继续、→ 下一分 P、↑/↓ 调速（10–20000×） |
| HUD | 当前分 P 标题、坐标、幕、估算标记；方向一事件数量（明确“未按时间对齐”） |
| 自动取景 | 按路线包围盒计算相机位置与朝向 |
| 可验证 | 无头自检 + Movie Maker 渲染 + FFmpeg 抽帧 |

## 二、验证记录

```
ROUTE parts=33 acts=9 events=195 total_s=70742.0
READY parts=33 acts=9 total_s=70742
T=18 part=P1 荣花与炎日之途 1 纳塔！新的旅程
```

渲染：`demo3.avi`（120 帧 @30fps），抽帧见 `sandbox_route.png`。

## 三、边界与说明

1. 坐标来自路线 JSON 的 `estimated` 字段，**是估算值，不是实测**；HUD 明确标注“（估算坐标）”。
2. 地面是参考平面，**不是真实地形**；地形 OBJ 尚未导入。
3. 方向一事件（195 条）来自另一支视频（P002），**没有按时间对齐**，HUD 已写明，仅作数据接入演示。
4. 没有导航网格、碰撞、角色控制器；当前是“路线回放”，不是“可操作沙盘”。

## 四、下一步

1. 导入 `GenshinMaps_7.1` 的纳塔地形/城市网格（按 manifest 的 position 摆位）；
2. 给地形加碰撞与 NavigationRegion3D，接入最小角色控制器；
3. 把方向一事件的相对轨迹（有坐标后）映射到地形上；
4. 状态快照与暂停/跳转恢复；
5. 双模式：证据回放（不补动作）/ 连续演示（标注“沙盘补全”）。

## 五、运行

```powershell
$gd = "D:\OpenAI\GenshinGuideAI\tools\godot\Godot_v4.7.2-stable_win64_console.exe"
& $gd --headless --path D:\OpenAI\GenshinGuideAI\sandbox --quit-after 120
& "D:\OpenAI\GenshinGuideAI\tools\godot\Godot_v4.7.2-stable_win64.exe" `
  --path D:\OpenAI\GenshinGuideAI\sandbox
```

## 六、第三步：真实场景网格导入（2026-11-06 追加）

- 工具：`tools/export_scene_obj.py`（按 manifest 的 position 偏移，合并多个 OBJ，三角化）
- 区域：以分 P1 坐标 (1470, 195, 10950) 为中心、半径 1500m
- 结果：合并 **18 个 HLOD 网格，116,087 顶点 / 83,257 三角形**（4.93 MB OBJ）
- 导入：Godot `--import` 后以 Mesh 资源加载，按锚点对齐（减去 P1 坐标后缩放到 1%）
- 视角：F 键切换「近景（场景网格）/ 全景（33 分 P 路线）」，默认近景
- 截图：`docs/reports/sandbox_terrain.png`

如实说明：
1. 这些是 HLOD 城市/区域网格块，**不是连续地形**；拼接后仍有空洞与断裂，HUD 已标注；
2. 没有法线数据，材质用 unshaded 显示；
3. 尚未加碰撞、NavigationRegion3D 与角色控制器；
4. 高度图方案（`tools/export_terrain.py`）也已实现，但因网格是建筑体块、有效格仅 4%，暂不作为主方案。
## 七、第四步：碰撞体 + 角色 + 航点跟随（2026-11-06 追加）

- 碰撞：场景 Mesh → `create_trimesh_shape()` → StaticBody3D（84k 三角形三角网碰撞，缩放 1% 与网格一致）
- 角色：CharacterBody3D（胶囊 0.4×1.6）+ 青色发光胶囊外观
- 跟随镜头：相机保持「角色 + (0, 7, 10)」俯视跟随，F 键切自由视角
- 航点：角色依次飞向 33 个分 P 节点（悬停于节点上方 2m，1 秒到达冷却），到达后 HUD 计数
- 验证：无头模式打印 `REACHED P1..Pn`；Movie Maker 渲染 300 帧，抽帧 `sandbox_walk1.png` / `sandbox_walk2.png`

实测（300 帧 / 10 秒）：

```
REACHED P1 (1)
REACHED P2 (2)
REACHED P3 (3)
...
REACHED P5 (5)   HUD：目标 P6   已到达 5 次
```

如实说明：
1. 角色是**悬停航点跟随**，不是真正的地面行走（网格碎片间有空隙，步行会掉落）；
2. 碰撞体已建立但演示未依赖它；
3. 尚未做 NavigationRegion3D 烘焙与 NavMesh 寻路，下一步再补。
## 八、第五步：NavMesh 烘焙 + NavigationAgent3D 寻路（2026-11-06 追加）

- 可走层：新建 240×240 连续地面（Mesh + StaticBody3D BoxShape），顶部 y=0
- 导航烘焙：运行时 `NavigationMesh`（agent_radius 0.5 / cell 0.25）→
  `NavigationServer3D.parse_source_geometry_data` + `bake_from_source_geometry_data`
  → `NavigationRegion3D`
- 结果：**4 顶点 / 2 多边形**（地面平面），`ok=true`
- 角色：`NavigationAgent3D` 跟随路径点，`get_next_path_position()` 转向 + 重力 + `move_and_slide`
- 到达判定：`agent.is_navigation_finished()` → 下一个分 P，冷却 1 秒
- 验证：无头 `NAV vertices=4 polygons=2 ok=true` + `REACHED P1..Pn`；渲染抽帧 `sandbox_nav.png`

如实说明：
1. NavMesh 只覆盖**演示地面层**，不覆盖 HLOD 碎片（碎片无法形成连续可行走面）；
2. 角色站在地面（高度约 0.8，胶囊半高），不再是悬停；
3. 尚未用真实地形烘焙导航——需要连续地形数据后再做。