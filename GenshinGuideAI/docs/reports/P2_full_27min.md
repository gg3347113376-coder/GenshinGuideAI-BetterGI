# P2 方向一 MVP 完整视频报告（27 分钟）

- 日期：2026-11-06
- 样本：`data/videos/bili_p002_1080.mp4`（B 站 BV1cW421R7me 第 2 分 P「荣花与炎日之途1」）
- 规格：1920×1080 / 30fps / 1641.4 秒
- SHA-256：`2c693ada97209e146ea885c579eb6b307b0361274f9d1683c10024a8e812b9da`

## 一、管线（v0.2）

| 环节 | 做法 |
|---|---|
| 解码采样 | PyAV 逐帧解码，1 fps（1641 帧） |
| OCR | RapidOCR，固定条带 + 免检测识别（任务追踪 3 条带、字幕 6 条带） |
| 文本归一化 | 去空白/首尾标点；汉字占比过滤（≥50%、≥2 字） |
| 稳定性 | 连续 2 采样才发射；最近 3 条相似度 ≥0.9 去重 |
| 说话人 | 按条带高度识别说话人，相似度 ≥0.7 归并到已知说话人 |
| 任务追踪 | 任务名/小标题与距离分离；10 秒记忆补齐；拉丁/数字噪声过滤 |
| 片段分类 | 有字幕→dialogue，无字幕→travel；短片段合并 |
| 证据 | 变化帧存 JPEG；缺帧事件二次回填 |
| 观测落盘 | `*.obs.jsonl`，规则调整后可用 `tools/reprocess.py` 只重跑抽取 |

## 二、结果

| 指标 | 数值 |
|---|---|
| 采样帧 | 1641（1 fps） |
| 证据帧 | 1190 张（另有 53 条事件二次回填） |
| 事件总数 | **195**（dialogue 190、move 5） |
| 片段 | 35（dialogue 17、travel 18） |
| 对话时长占比 | **87.3%**（1433 / 1641 秒） |
| 处理耗时 | 763.7 秒（约 0.47 秒/采样） |
| 平均置信度 | 0.746 |
| 带说话人的对白 | 136 / 190（71.6%） |
| 可复核标记 | 46 / 195（23.6%）：首尾噪声 37、说话人可疑 7、文本过短 3 |
| 协议校验 | 通过（生成、回填后各一次） |
| 坐标事件 | 0（见限制 1） |

说话人分布（OCR 归并后）：卡齐娜 81、未知 54、帕加尔 22、派蒙 6、特拉科 4、森珀娅系 4。

任务事件（5 条）：

```
   0s  深入纳塔
   4s  纳塔！新的旅程 | 深入纳塔
  19s  深入纳塔一 | 深入纳塔        ← 仍有一次条带噪声，已列入复核
 559s  随卡齐娜前往「回声之子」
1421s  猫尾酒馆·七圣召唤            ← 非任务弹窗，误报，已列入复核
```

## 三、限制（如实声明）

1. **没有绝对坐标**：原神小地图是玩家居中的，箭头恒在中心；要从视频得到地图/世界坐标，需要引入地图数据（如空荧酒馆 ky-genshin-map）做小地图匹配，本期未做。所有事件 `position.*` 均为 `null` + `method=unknown`，符合“未知不编造”，但定位覆盖率为 0。
2. **没有战斗事件**：镜头运动本身很大，单纯帧差无法区分战斗；需要血条/伤害数字/技能 CD 等专用识别。
3. **未接 VLM**：Ollama 与 qwen3-vl:4b 尚未安装，关键帧语义复核未启用。
4. **未做人工标注对照**：动作类型 Precision/Recall 尚未测量；目前只有规则与抽检。
5. **单视频、单场景**：仅验证纳塔 5.0 一段；跨地区/跨 UI 主题未验证。

## 四、下一步（按优先级）

1. 小地图定位：接入地图数据 + 模板匹配，给 `move` 补 `map.x/y` 与 `error_m`；
2. 战斗识别：血条/受击/技能图标；
3. 人工抽检 30 条并计算动作准确率与 OCR 错误率；
4. 安装 Ollama + qwen3-vl:4b，关键帧语义复核；
5. 换 1–2 个不同地区视频做泛化测试；
6. 进入 P3：把事件 JSON 交给 Godot 局部沙盘回放。

## 五、复现与工具

```powershell
$env:PYTHONPATH = "D:\OpenAI\GenshinGuideAI\src"

# 全量抽取（约 13 分钟）
python tools\run_pipeline.py --video data\videos\bili_p002_1080.mp4 --sample-fps 1 `
  --out runs\p002_full_v2.json --frames data\frames\p002_full_v2 `
  --db runs\p002_full_v2.db --ocr-mode strips

# 仅重跑规则（不重新 OCR）
python tools\reprocess.py runs\p002_full_v2.obs.jsonl --duration 1641.4 `
  --out runs\p002_full_v2_re.json

# 证据帧回填
python tools\backfill_evidence.py runs\p002_full_v2.json `
  data\videos\bili_p002_1080.mp4 data\frames\p002_full_v2_backfill

# 人工复核清单
python tools\make_review.py runs\p002_full_v2.json runs\p002_full_v2_review.csv
```
