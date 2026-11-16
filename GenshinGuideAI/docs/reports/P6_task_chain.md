# 多任务依赖链执行与恢复（方向三战略层）

- 实现：`TaskRunner`（`src/ggai/executor.py`）
- 演示：`tools/run_task_chain.py`
- 测试：`tests/test_task_chain.py`（3 个）

## 一、机制

| 能力 | 说明 |
|---|---|
| 依赖排序 | `topological_order()`，有环直接报错 |
| 依赖检查 | 前置任务未完成 → 当前任务 `skipped` |
| 失败即停 | 任务失败后，后续依赖任务全部跳过，不盲目继续 |
| 检查点 | 记录 `{task_id, plan_index}`，失败时保存当前任务进度 |
| 恢复 | 从检查点任务继续；之前的任务视为已完成；当前任务按 plan_index 续跑 |
| 重新观察 | 恢复后仍以 `world.observe()` 为准，路径重新计算 |

## 二、演示结果

三个任务：`t1_采集 → t2_营地 → t3_返回`。第一轮把 `t2` 的目标用墙围死：

```
first_run:
  t1_采集: done
  t2_营地: failed
  t3_返回: skipped
checkpoint_after_failure:
  task_id: t2_营地
  plan_index: 0
```

修复环境（移除墙）并把玩家起点改到 (2,2) 后恢复：

```
resume_run:
  t1_采集: done
  t2_营地: done
  t3_返回: done
```

## 三、边界

- 只在模拟网格环境验证；
- 任务串行执行，没有并行任务与资源冲突锁；
- 恢复假设“检查点之前的任务确实已完成”，没有对已完成任务做二次观察校验；
- 环境变化由脚本注入，不是真实外部事件。
