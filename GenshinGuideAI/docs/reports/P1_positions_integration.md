# 坐标写入项目 + 端到端合并

- 日期：2026-11-07
- 输入：纳塔跑图 555s（1080p）、Boss 实战 259s
- 产物：`runs/explore_with_pos.json`、`runs/combined_demo.json`

## 一、跑图视频管线

```
events=41  segments=18  dialogue_ratio=0.299  elapsed=391.7s
```

41 条事件（38 对话 + 3 移动），对话占比 29.9%。

## 二、位置轨迹

- 每 5 秒采样，共 111 个点；
- 成功 90（其中 7 个为相邻成功点线性插值），**覆盖率 81.1%**；
- 失败原因：转场/运动模糊/小地图被 UI 遮挡。

## 三、写入项目

`attach_positions.py` 生成 90 条 `move` 事件：

- `position.map.x/y`：游戏地图坐标；
- `method`：`minimap`（协议枚举），细节记在 `action.params.method=minimap_sift`；
- `confidence`：按匹配点数与散布折算，均值 **0.664**（插值帧 0.4）；
- 每条事件带采样帧证据。

校验结果：

```
events=131  by_action={move:93, dialogue:38}
by_layer={surface:90, unknown:41}
events_with_map_position=90  mean_confidence=0.687
```

坐标范围：x **7722–8220**、y **-2375–-1539**，全部落在纳塔。

## 四、端到端合并

`merge_projects.py` 把 Boss 项目并入同一份 JSON（两个 source）：

```
sources=2  events=133
by_action={move:93, dialogue:38, fight_start:1, fight_end:1}
positioned=90  mean_confidence=0.688
校验通过
```

一份文件同时包含：带坐标的移动、对话、Boss 战起止，且都带证据帧。

## 五、质量与边界

- 相邻采样位移均值 **46.1 单位/5s**（≈9.2 m/s，符合冲刺速度）；
- 最大位移 **397.5 单位/5s**，疑似传送/加载跳变或匹配错误，未做过滤；
- 插值帧置信度固定 0.4，不代表真实观测；
- 尚无绝对误差标定（无真值坐标），只有轨迹连续性；
- 坐标系为游戏地图坐标（1024 级），不是三维世界坐标；
- UI 参数（中心 205,160 / 直径 300）按 1080p 标定。

## 六、轨迹过滤

`filter_track.py` 按相邻采样位移 >150 单位标记可疑：

```
samples=111  ok=90  suspects=3  mean=46.1  max=397.5
```

3 个可疑点置信度降到 0.3，查看器中显示为橙色点。

## 七、查看器

`build_viewer.py` 增加：

- 轨迹画布：90 个坐标点连线，x 7722–8220、y -2375–-1539；
- 列表显示每个事件坐标；
- 详情显示坐标、方法、置信度。

截图：`docs/reports/viewer_explore2.png`。

## 八、质量备注

跑图视频本身带 UP 主叠加字幕与设置界面，38 条 dialogue 中有几条是这些文字被 OCR（如「场景细节极高」），不是游戏对白。属于素材特性，后续可用「说话人是否为空 + 字幕底色」过滤。

## 九、字幕/面板过滤

跑图视频的 38 条 dialogue 全是素材产物（UP 主黄色字幕 + 白底设置/提示面板 + 水印）：

- 黄色字幕过滤：黄色像素占比 >0.03，删掉 **25** 条；
- 剩余 6 条为白底面板/水印，人工确认不是游戏对白；
- 因此生成 `explore_positions_only.json`：删除全部 dialogue，保留 **93 条 move**（90 条带坐标），校验通过。

## 十、入库往返验证

```
import runs\explore_positions_only.json runs\explore.db
已导入：events=93
stats：events_with_map_position=90
export → explore_roundtrip.json，校验通过（93 事件、90 坐标）
```

## 十一、合并演示 v2

`combined_demo_v2.json`：跑图（93 move，90 坐标）+ Boss 战（fight_start/end），两个 source：

```
sources=2  events=95  positioned=90  fight_events=2  校验通过
```

## 十二、下一步

1. 位移阈值过滤（>150 单位/5s 标为可疑）；
2. 用任务追踪距离做一致性校验；
3. 查看器显示坐标与轨迹；
4. 多分辨率/多视频验证。
