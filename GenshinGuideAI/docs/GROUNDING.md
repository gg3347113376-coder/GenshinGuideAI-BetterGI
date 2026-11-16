# 第一阶段续作：任务理解与目标文字核验

本次仅分析本地攻略。主流程不导入窗口捕获或键鼠模块，不启动游戏，不投递 BetterGI 命令。BetterGI 的 `tp.json` 只被读取为候选目录。所有计划仍是 `execution_allowed=false`，所有步骤 `not_executed`。

## 做了什么

1. OCR 保存原始文字、置信度、四角坐标、帧哈希和模型哈希，再按相对位置区分地图状态栏、任务追踪、交互提示、字幕、地图标签、选中面板与作者图例。低分、图标粘连及未知文字不会自动补字。地图背景标签可辅助拼字匹配，但不直接送入任务模型当目的地。
2. 原 ASR 不修改。可用本地 Whisper small 做一次带领域词提示的复听，保留两版、时间范围及音视频哈希。复听记录词级时间，按原句时段取词，避免把后一句的地名当成前一句的证据。旧复听若只有跨句长段，会保留为上下文但不送入本句推理。词级时间仍是模型估计。两版一致不代表事实正确；词汇提示也可能引入幻觉。只有附近 3 秒的合适 OCR 文字可形成交叉支持。编辑距离产生的地名候选仍标记为“建议，未替换”。
3. 锚点按类型、选中面板、区域、候选列表分别处理，过滤七天神像与秘境等不同类型。地图上出现某个地名不等于选中该锚点；即使候选只剩一个，仍不自动认定坐标或用户解锁状态。
4. 任务模型的精确交互文字被限制在 OCR 提示枚举中；引用不存在的证据不允许。规则还检查背景地名被当目标、明确指令漏步、无证据激活锚点等问题。不合格最多自动重规划一次，每次请求、原始回复、草案和拒绝原因均保留；二次失败继续标记拒绝，不无限重试。命令行对语义拒绝返回退出码 2，同时保留可查看的报告；退出码 0 仍只表示可复核，不表示能执行。
5. 协议 1.2 增加 grounding，继续支持 1.0/1.1。原始证据文件、OCR 派生结果、候选和计划通过引用与哈希核验，SQLite 完整快照往返保存。

规则未报错只表示通过这些有限检查，不表示语义已完全正确。`confidence` 仍是模型自评分。

## 运行

沿用项目已有 D 盘虚拟环境。新版目标绑定与独立模型复核见 [TARGET_REVIEW.md](TARGET_REVIEW.md)；本页记录 OCR/ASR 核验层。不自动下载模型。已有的 `run_phase1.ps1` 会对隆崛坡片段运行复听、文字核验和任务规划。每次创建新输出目录。

其他攻略已有原始转写时：

```powershell
& '<Python路径>' -B ./tools/plan_guide.py `
  --video '<视频.mp4>' --transcript '<原始转写.json>' `
  --asr-model '<本地faster-whisper-small目录>' `
  --output '<新的D盘输出目录>' --start 0 --end 20 --frames '1,5,10,19' `
  --id guide_clip --name '攻略分析' --source-url '<原作者页面>'
```

视频与音轨分离时加 `--audio '<音轨.m4a>'`。必须是同一起点；当前只记录零偏移，不自动做声画同步校准。已有复听结果可用 `--retry-transcript`，必须含匹配视频的 `video_sha256`、`segments` 及起止时间。省略这两种选项时仍做 OCR/候选核验，明确记录未复听。

没有转写时先运行：

```powershell
& '<Python路径>' -B ./tools/transcribe_guide.py `
  --video '<视频.mp4>' --model-dir '<本地Whisper目录>' `
  --output '<新的D盘目录/原始转写.json>' --start 0 --end 20
```

第二次带领域提示可加 `--domain-prompt` 并指定另一个输出文件。已有转写文件不会被覆盖。

## 依赖

本机使用 rapidocr_onnxruntime 1.4.4、faster-whisper 1.2.1、现有 OpenCV headless。RapidOCR 的包依赖声明要求另一个 OpenCV 发行包；为避免两个包同时覆盖 cv2，安装它时单独使用 `--no-deps`，其余依赖由清单安装：

```powershell
& '<Python路径>' -m pip install -r requirements-phase1.txt -r requirements-grounding.txt
& '<Python路径>' -m pip install --no-deps rapidocr_onnxruntime==1.4.4
```

模型目录保留在本项目 D 盘 dependencies 下。无需云端 API 密钥。

## 结果和复核

- report.html：逐帧核对保留/排除理由、语音两版和锚点歧义。
- grounding.json / project.json：机器可读的全部来源和候选。
- evidence/ocr_raw.json：OCR 原始输出、尺寸和模型哈希。
- evidence/asr_retry.json：复听结果与来源；没有复听时不存在。
- evidence/waypoint_catalog.json：本次读取的锚点目录快照。
- model-draft-task_XXX.json / plan-review-task_XXX.json：每次模型输出及有限语义检查。
- validation.json：协议、证据与数据库往返结果。它不代表实机验收。

三段真实攻略的测试 manifest 与各轮结果保存在 `outputs/GenshinGuideAI/grounding-eval`。使用 `tools/evaluate_guides.py --manifest <grounding-eval/cases.json> --suffix v6` 可重新核验保存的结果，不会再次调用模型。期望断言不传给模型。它们是开发回归样本，已经用于发现和修复问题，不是未见样本测试，也不能据此宣称整体准确率。

## 当前明确限制

- OCR 位置规则目前只针对常见横屏布局，尚未覆盖任意裁切、遮挡、缩放界面及多语言。
- 没有新建物体检测/地形识别模型；新入口使用 OCR 的文字事实与语音理解任务，不能依此证明看懂所有无文字机关、裂隙或可通行地形。旧视觉推断历史保留，但不直接充当已核实事实。
- Whisper small 的第二次结果仍会错；同音词、短促方言、音乐重叠、说话人分离和音视频偏移未解决。
- 语义覆盖检查是有限中文规则，不是完整语言解析器。否定/假设只做保守跳过；复杂条件、指代与跨片段任务仍需复核。
- 锚点尚缺地图标记定位、坐标变换和图层校准。本次只能识别类型/区域并列候选，不能精确确定某一个锚点。
- 没有验证用户当前任务、解锁状态、体力、路线、战斗策略和成功后画面。没有运行暂停、失焦、停止或任何实机测试。
