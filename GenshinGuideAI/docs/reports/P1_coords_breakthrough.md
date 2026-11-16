# 坐标定位突破：复用 BetterGI 地图资产与匹配算法

- 日期：2026-11-06
- 目标：解决方向一「绝对坐标」缺口
- 产物：`tools/minimap_localize.py`、`tests/test_minimap.py`

## 一、找到了什么

BetterGI 安装目录自带完整地图资产与匹配实现：

| 资产/源码 | 内容 |
|---|---|
| `Assets\Map\Teyvat\MapBack_*_gray.webp` | 5 张地表底图（灰度），带世界坐标锚点 |
| `Assets\Map\Teyvat\mapback_info.json` | 每张底图的 `Left` / `Top` / `Scale` |
| `TeyvatMap.cs` / `SceneBaseMap.cs` | 坐标换算公式 |
| `BaseMapLayerByTemplateMatch.cs` | 粗匹配 + 精匹配流程 |
| `MiniMapMatchConfig.cs` | 尺寸/缩放常量 |

## 二、换算公式（已核对源码）

- 2048 级别图像坐标 ↔ 1024 级游戏地图坐标：
  ```
  gameX = (32768 - imgX) / 2
  gameY = (24576 - imgY) / 2
  ```
- 底图层（Scale/Left/Top）↔ 世界坐标：
  ```
  mapX = (Left - worldX) * Scale / zoom
  worldX = Left - (mapX + size/2) * zoom / Scale
  ```
- 常量：OriginalSize=156、RoughSize=52/RoughZoom=5、ExactSize=260/ExactZoom=1。

## 三、实现与验证

`tools/minimap_localize.py`：

1. 按层做粗匹配（底图 1/5、小地图 52×52、TM_SQDIFF + 圆形掩码）；
2. 在粗结果附近 ±20px 做精匹配（260×260）；
3. 输出世界坐标、层 ID、匹配分数。

**合成验证**：从 MapBack_0 裁一块 260×260 作为“小地图”，反解结果：

```
target world = (10264.0, -2762.0)
recovered    = (10264.0, -2762.0)
error        = 0.0
```

坐标公式与匹配器均正确，已用单元测试锁定（2 个测试通过）。

## 四、真实视频为什么还不行

P002 的小地图几乎全是**未探索黑区**（HUD 仅 13% 时间可见，且小地图无地形纹理），模板匹配缺少特征；换到有 HUD 的帧（t=5/560）也只能看到黑盘与图标。

结论：**算法就绪，缺的是「已探索地图 + HUD 常驻」的素材**。

## 五、下一步

1. 找一段开放世界跑图/探索视频（小地图有地形纹理），验证连续帧坐标是否平滑；
2. 按 1920×1080 校准小地图裁剪（中心约 (180,130)、直径约 210–230），并遮掉左侧派蒙菜单、右上眼睛图标、下方任务条；
3. 用 Quest 距离做粗校验（距离变化应与坐标位移一致）。

## 六、边界

- 输出的是**游戏地图坐标（1024 级）**，写入协议的 `position.map.x/y`，不是三维世界坐标；
- 室内/地下需按层匹配，暂只做地表 MapBack；
- 单帧匹配可能失败，需要用上一帧位置做局部搜索（BetterGI 也是这么做的）。
