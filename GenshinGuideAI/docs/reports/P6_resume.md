# 检查点恢复验证（方向三验收点）

- 工具：`tools/resume_demo.py`
- 实现：`src/ggai/executor.py`（`max_steps` 中断、`from_pos` 审计、L3 恢复移动）

## 一、要验证什么

文档要求：“保存检查点；恢复时必须重新观察真实环境，不得仅依赖历史数据库状态。”

本轮用一个可复现的模拟场景验证：

1. 第一次运行只走 1 步就中断，落盘检查点；
2. 停机期间环境变化：玩家被移动到 **(10, 2)**，并新增一道 **x=12 的墙**；
3. 用检查点恢复：新执行器**重新观察**，发现不在交互点，先重新走到目标（L3 局部重规划），再完成交互。

## 二、运行结果

```
first_run:
  steps_done: 1
  stopped: 达到 max_steps（模拟中断）
  checkpoint: {plan_index: 1, tick: 28, pos: [15, 15]}

world_changed:
  start_pos: [10, 2]
  checkpoint_pos: [15, 15]
  same: false
  walls: 12

resume:
  completed: true
  steps_done: 1
  actions: 19
  paused_reason: ""
```

关键证据：恢复后第一条审计记录的动作前位置是 **[10, 2]**（新观察），不是检查点里的 [15, 15]。

## 三、实现要点

| 机制 | 说明 |
|---|---|
| `max_steps` | 执行到指定步数即返回，模拟中断 |
| 检查点 | 每完成一步写 `plan_index / tick / pos` |
| 恢复 | 新建执行器 + `Plan(index=checkpoint.plan_index)`，**不读取旧位置** |
| 重新观察 | 每轮循环都 `world.observe()`，动作基于当前真实位置 |
| L3 恢复 | 交互步骤前置不满足（不在交互点）时，先 A* 重新走过去，而不是直接失败 |
| 审计 | `from_pos`（动作前观察）+ `pos`（动作后）双记录，可核对 |

## 四、边界

- 仅模拟网格环境，不是真实游戏；
- 恢复仅覆盖单任务计划，多任务依赖链的恢复还未实现；
- 环境变化是脚本注入的，不是真实外部事件。
