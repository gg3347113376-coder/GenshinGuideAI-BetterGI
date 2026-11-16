# 沙盘性能实测（1080P / 60FPS 目标）

- 日期：2026-11-06
- 引擎：Godot 4.7.2（gl_compatibility）
- 工程视口：**1920×1080**
- 方法：Movie Maker 固定 60 FPS 渲染 120 帧，读取引擎自报的 CPU/GPU 渲染耗时

## 一、结果

| 模式 | 分辨率 | CPU 渲染 | GPU 渲染 | 合计 | 占 60FPS 预算（16.67ms） |
|---|---|---|---|---|---|
| 路线视图 | 1920×1080 | 0.55 ms | 0.29 ms | **0.84 ms** | 约 5.0% |
| 证据回放 | 1920×1080 | 0.39 ms | 0.21 ms | **0.60 ms** | 约 3.6% |
| 执行模式 | 1920×1080 | 0.43 ms | 0.19 ms | **0.62 ms** | 约 3.7% |

对比（1280×720）：路线 0.83ms、证据 0.58ms、执行 0.58ms——1080p 相比 720p 只增加约 0.02–0.03ms，瓶颈不在像素填充。

## 二、结论

1. **1080P@60FPS 有充足余量**：三种视图渲染成本都低于 1ms，占帧预算约 4%；
2. 场景很轻（18 个 HLOD 网格 + 少量节点与一条路线），远未触及 GPU 上限；
3. 证据回放把图片贴在 Sprite3D 上，成本反而最低（画面被大图覆盖）。

## 三、限制（如实说明）

- 这是**渲染耗时**，不含物理、脚本与导航计算；
- 没有长时间稳定性测试（仅 120 帧/模式）；
- 没有测 2560×1440 或 4K；
- 没有测多物体/多角色场景下的性能上限。

## 四、复现

```powershell
$gd = "D:\OpenAI\GenshinGuideAI\tools\godot\Godot_v4.7.2-stable_win64_console.exe"
# 路线视图
& $gd --path D:\OpenAI\GenshinGuideAI\sandbox --write-movie perf.avi --fixed-fps 60 --quit-after 120 -- --route
# 证据回放（默认）
& $gd --path D:\OpenAI\GenshinGuideAI\sandbox --write-movie perf.avi --fixed-fps 60 --quit-after 120
# 执行模式
& $gd --path D:\OpenAI\GenshinGuideAI\sandbox --write-movie perf.avi --fixed-fps 60 --quit-after 120 -- --exec
```

> 注：Movie Maker 使用工程视口尺寸（已在 `project.godot` 改为 1920×1080），`--resolution` 不改变录制尺寸。
