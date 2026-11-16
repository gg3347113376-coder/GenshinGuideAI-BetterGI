# 第一阶段：证据化任务计划

此目录是从已审查 V3 包导入的 Python 核心工作副本。原包快照保留在 `outputs/package-reviews/GenshinGuideAI-V3-20261108`。BetterGI 和 GuideWorkbench 的控制程序保持原样。

本阶段实现视频证据、任务理解、动作目录和数据往返；不绑定游戏窗口，不调用游戏截图，不发送键鼠，不生成或投递 BetterGI 命令。目录中的既有模拟器仍是独立的网格示例，不能作为本阶段真实执行证据。

## 使用

从此目录执行 `./run_phase1.ps1`，会为已有隆崛坡攻略 0–17.22 秒片段创建新输出目录。先执行 `./run_task_model.ps1` 检查或启动项目独立的本地模型服务（11435 端口）。任务入口使用已安装模型，不自动下载；目标绑定与独立复核详见 [TARGET_REVIEW.md](TARGET_REVIEW.md)。输出目录必须不存在，避免把不同推理运行混在一起。

Python 使用现有 `dependencies/GuideWorkbench/venv/Scripts/python.exe`。基础依赖在 `requirements-phase1.txt`；本轮文字核验与语音复听的依赖和安装方式见 [GROUNDING.md](GROUNDING.md)。原组件完整测试还需要其既有 NumPy、PyAV 等依赖。只依赖本地 Ollama HTTP API，不需要云端 API 密钥。

分析其他攻略：

```powershell
& '<Python路径>' -B ./tools/plan_guide.py --video '<本地视频>' --transcript '<转写JSON>' --output '<新的D盘目录>' --start 0 --end 20 --frames '1,6,12,19' --id guide_clip --name '攻略片段'
```

转写格式保持 GuideWorkbench 的 `{ "segments": [{ "start": 0, "end": 2, "text": "原文" }] }`。现在可用 `--asr-model` 对同起点音轨进行一次复听，或用 `--retry-transcript` 导入带视频哈希的复听结果。两者互斥；默认启动脚本已启用本地复听。错字保留为原始证据，不能悄悄覆盖；坐标和路线不从语言模型生成。现有经过其他流程标定的坐标没有被自动继承，仍需显式对齐来源、地图版本和图层。

## 统一协议

- `schema/project_v1.schema.json`：旧版 1.0，继续支持。
- `schema/project_v1_2.schema.json`：在 1.1 基础上增加 `grounding`，保存 OCR 位置/分类、转写候选、锚点候选及语义检查。旧项目继续支持。
- `schema/project_v1_3.schema.json`：新 CLI 默认版本，增加目标注册表、每步 `target_ref` 和独立语义复核。
- `schema/project_v1_1.schema.json`：继续兼容的第一阶段项目。包含 sources、segments、events、evidence_index、analysis_runs、task_plan、simulation_runs、execution_runs。
- `schema/task_plan_v1.schema.json`：旧任务计划；`schema/task_plan_v1_3.schema.json`：含目标引用的新任务计划。
- `schema/action_catalog.json`：动作参数 Schema、前置/完成检查、超时、重试策略和源码绑定线索。共 8 类动作及 1 个 unknown 占位项。等待可观察条件尚无满足语义的执行实现；普通 sleep 不算该能力。

原视频事件、模型推断的任务、模拟结果和真实执行结果分开。新计划所有 `observed_result.status` 都是 `not_executed`，`execution_allowed=false`；审核状态是 pending，模拟与真实执行列表为空。模型自评分不等于校准后的正确率。

`protocol.validate(project, artifact_root)` 同时检查结构、动作参数、依赖顺序、证据和事件交叉引用、文件范围及 SHA-256。转写文字和时间必须与原始转写片段一致。离线校验无法证明图片中的语义判断正确，也不证明场景可通行。

模型只有选择目录动作与填写任务描述的权限。数值坐标、路线 ID、地图层不会由模型补造；缺失内容进入 blockers。计划存在并不意味着可运行。任务步骤的成功检查当前是明确的检查规格，真实传感器适配和执行后验证属于下一阶段。

## 数据丢失修复

`store.import_project` 在一个事务中保存完整项目 JSON 和查询投影，完整 JSON 是导出的唯一权威数据。保留前置条件、预期/观测结果、sim_time、模型版本、actor confidence、action notes、嵌套参数、审核差异及新计划字段。

导入只替换当前项目的数据，保留其他项目以及已有 sim_runs 历史。跨项目使用相同 source/segment/event ID 会被明确拒绝，不能覆盖。多个项目的数据库导出需传 `project_id`，CLI 为 `export <db> <json> --project-id <id>`。

不要直接 UPDATE 查询投影；更改经 JSON 载入/审核后用 import_project 提交，保证投影与完整数据同时更新。旧库可只读导出并给出缺字段警告；已丢失的字段不能凭空恢复，需要从原 JSON 重新导入。本轮未修改用户旧数据库。

另修复中文路径下 OpenCV 图片保存失败却返回成功的问题，并补齐原包自带模板的读取兼容。

## 输出与追溯

- report.html：本地可读结果，逐步查看证据和缺项。
- project.json / task-plan.json：完整协议与任务计划。
- evidence/：4 帧原视频 PNG 和保留原文的转写片段；帧数按输入参数决定。
- model/*.request.json / *.response.json：提示词、结构 Schema、模型标识、参数、原始响应、耗时与引用。
- model-draft.json：当前模型草案；model-draft-task_XXX.json 保留每次尝试，新的 semantic_XXX.json 保存逐次独立复核，旧流程保存 plan-review-task_XXX.json。旧 1.1 流程还会保存 observations.json。
- grounding.json：原始 OCR 与候选对照。新流程由 OCR 提供文字证据，由 Qwen 理解任务，不把旧视觉模型的自由描述当作事实。
- project.sqlite / roundtrip.json：无损保存后的再导出，用完整字典相等验证。
- validation.json：结构/文件/往返检查和真实源码绑定检查；不是游戏测试通过报告。

失败时保留已产生的证据和模型回复，记录 failure.json 或 validation-failure.json；不会回退生成虚构成功计划。

## 下一阶段边界

需要补当前任务/世界状态、目标和锚点的可靠身份、地图层与坐标对齐、可通行路线、体力与攀爬约束、适配的战斗策略，以及动作后的新画面成功验证。再把动作目录接到 BetterGI 的受控适配器，分别验收暂停、失焦、停止、断流和恢复。此阶段没有授权或进行任何实机操作。

结构化输出实现参考 [Ollama 官方文档](https://docs.ollama.com/capabilities/structured-outputs)。它约束 JSON 形状，不保证模型内容真实。

本机首次以 CPU 处理第三帧出现 180 秒超时，已保留该次失败记录。当前关键帧输出限制条目数，每次模型调用最多等待 360 秒，超时仍停止；服务是否使用 GPU 需单独验证，不把请求了 GPU 当成实际使用。

## 语义复核与重新规划

本次真实样例的首次完整输出通过结构校验，但把常驻 UI 文字当成任务地点并遗漏传送前置，因此没有按语义验收通过。不能把 JSON 校验成功当成任务理解正确。

`tools/replan_guide.py --project <原project.json> --review <复核意见.json> --output <新目录>` 会验证原证据、保留 previous-project.json 和既有模型回复，再将有作者、有证据引用的意见交给模型重新规划。不会把旧错误计划静默改成成功记录，也不会自动批准新计划。

复核意见格式为 `{ "author": "审阅者", "findings": [{ "evidence_ids": ["asr_001"], "text": "指出错误、根据与不确定项" }] }`。本次复核由 Codex 对原视频帧和转写进行，不代表用户批准或游戏实况。准确锚点、坐标、路线、精确宝箱文字仍留空。网页目前提供只读核对；尚未做人工复核编辑器。

修改后的初次规划提示也强调区分常驻 UI、作者贴图和当前任务。该提示的普适准确率还需要独立样本验证，不能用复核后的单个样例估计。
