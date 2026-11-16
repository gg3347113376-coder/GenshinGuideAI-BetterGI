> 当前工作副本已增加第一阶段证据化任务计划，入口与边界见 [docs/PHASE1.md](docs/PHASE1.md)，运行 `run_phase1.ps1`。以下保留原包说明；Godot 沙盒和旧运行记录仍在原包快照中。

# GenshinGuideAI

> 32 轮成果汇总：[项目总报告](docs/项目总报告.md)

原神攻略智能解析、三维沙盘与受控执行系统（V3.0 实现）。

## 现在做到哪了

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 范围与边界确认、环境盘点 | ✅ |
| P1 | **统一数据协议 v1**（JSON Schema + SQLite + CLI + 测试） | ✅ 已完成 |
| P2 | 方向一 MVP：单视频 → 可追溯事件 | ✅ 事件/证据/复核完成；战斗识别实验失败（[报告](docs/reports/P2_full_27min.md) / [战斗实验](docs/reports/P2_combat_attempt.md)） |
| P3 | 方向二：Godot 局部地形精确回放 | 🚧 路线 + HLOD 场景 + NavMesh + 证据回放（跳转/暂停/调速）（[沙盘](docs/reports/P3_sandbox_skeleton.md) / [证据](docs/reports/P3_evidence_replay.md)） |
| P4 | 误差验证与指标 | 🚧 金标准指标 + 人工复核工作流 + 证据查看器 + 第二支视频泛化（[指标](docs/reports/P4_metrics30.md) / [查看器](docs/reports/P4_viewer.md) / [泛化](docs/reports/P4_generalization.md)） |
| P5 | 自由推演分支 | 🚧 4 分支 × 20 种子统计 + sim_runs 落库（80 行）（[分支](docs/reports/P5_branches.md) / [多种子](docs/reports/P5_multi_seed.md)） |
| P6 | 方向三：沙盘闭环执行 + 故障注入 | 🚧 模拟执行器 + 依赖链/恢复 + 沙盘 NavMesh 闭环 + exec_runs 归档（[沙盘闭环](docs/reports/P6_sandbox_exec.md) / [归档](docs/reports/P6_exec_store.md)） |

## 目录

```
schema/           协议 JSON Schema 与 SQLite DDL
src/ggai/         协议、存储、CLI
samples/          协议样例项目
tests/            单元测试
docs/             范围决策、协议说明、路线图
data/videos/      样本视频（不入库）
data/frames/      抽帧与证据图
runs/             数据库、导出、运行记录
tools/            辅助脚本
```

## 快速开始

```powershell
# 1. 依赖
python -m pip install -r requirements.txt

# 2. 环境变量（不装包时用源码路径）
$env:PYTHONPATH = "D:\OpenAI\GenshinGuideAI\src"

# 3. 校验样例
python -m ggai validate samples\sample_project.json

# 4. 入库 + 统计 + 导出
python -m ggai import samples\sample_project.json runs\demo.db
python -m ggai stats runs\demo.db
python -m ggai export runs\demo.db runs\exported.json

# 5. 测试
python -m unittest discover -s tests -v
```

## 三条设计底线

1. **证据可追溯**：每条事件都能回到视频时间戳与关键帧；没有证据就标 `unknown`。
2. **未知不编造**：坐标/高度/层级缺证据时留空并标注 `method=unknown`，不拼接不存在的地下路线。
3. **三类结果分开**：视频证据、沙盘计算、授权环境实际观察，各自存储、互不覆盖。

## 非目标（明确不做）

- 绕过反作弊、注入游戏进程、修改内存、拦截未授权通信；
- 未获授权的真实游戏自动化；
- 把沙盘回放通过等同于真实环境通过。

## 文档

- [范围与已确认决策](docs/00_范围与决策.md)
- [统一数据协议 v1](docs/01_数据协议_v1.md)
- [V3.0 验收对照与差距清单](docs/03_验收对照.md)
- [P2 完整视频报告](docs/reports/P2_full_27min.md)
- [坐标定位突破（BetterGI 资产复用）](docs/reports/P1_coords_breakthrough.md)
- [Boss 战识别（模板+时序）](docs/reports/P2_combat_boss.md)
- [本地 VLM 部署（Qwen2.5-VL-3B CPU）](docs/reports/P2_vlm_local.md)
- [Mock 驱动闭环与只读观测](docs/reports/P6_mock_and_observer.md)
- [坐标定位 SIFT（真实视频验证）](docs/reports/P1_coords_sift.md)
- [坐标写入项目与端到端合并](docs/reports/P1_positions_integration.md)
- [战斗识别实验（未通过）](docs/reports/P2_combat_attempt.md)
- [VLM 接入尝试（网络阻塞）](docs/reports/P2_vlm_attempt.md)
- [P3 沙盘骨架报告](docs/reports/P3_sandbox_skeleton.md)
- [P3/P6 执行结果回放](docs/reports/P3_exec_replay.md)
- [检查点恢复验证](docs/reports/P6_resume.md)
- [多任务依赖链与恢复](docs/reports/P6_task_chain.md)
- [自由推演分支](docs/reports/P5_branches.md)
- [多 Seed 分支评估](docs/reports/P5_multi_seed.md)
- [沙盘 NavMesh 闭环执行](docs/reports/P6_sandbox_exec.md)
- [执行结果归档 exec_runs](docs/reports/P6_exec_store.md)
- [沙盘证据回放](docs/reports/P3_evidence_replay.md)
- [沙盘性能实测](docs/reports/P3_performance.md)
- [双模式回放](docs/reports/P3_dual_mode.md)
- [路线图与验收](docs/02_路线图.md)
