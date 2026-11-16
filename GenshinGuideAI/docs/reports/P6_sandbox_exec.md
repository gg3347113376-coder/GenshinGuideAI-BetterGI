# 沙盘闭环执行（NavMesh 真跑，非网格模拟）

- 计划导出：`tools/export_exec_plan.py`
- 执行端：Godot `--exec` 模式（`sandbox/main.gd`）
- 结果：`sandbox/data/exec_result.json`
- 截图：`docs/reports/sandbox_exec.png`

## 一、链路

```
Python 生成 exec_plan.json（示意坐标）
  → Godot --exec：加载计划，用 NavigationAgent3D 沿 NavMesh 移动
  → 逐步执行 move / interact，记录位置与状态
  → 写出 exec_result.json（每步 id/action/status/pos/t）
```

## 二、执行规则

| 情况 | 处理 |
|---|---|
| move 步骤 | 用 NavigationAgent3D 寻路，进入 2 米内算到达 |
| interact 步骤 | 距目标 <2 米算完成 |
| 单步超过 15 秒 | 重试，最多 3 次；仍失败则 **安全暂停** |
| 目标越界（>110 米） | 立即判失败并暂停（不可达保护） |
| 场景碰撞 | 执行模式关闭 HLOD 场景碰撞，保留地面，避免碎片卡住角色 |
| 结果 | 每步写一条结果；结束写 `state`（done/paused） |

## 三、验证

正常计划（8 步）：

```
EXEC steps=8
EXEC step s1_move -> done
...
EXEC step s4_interact -> done
EXEC_RESULT written state=done results=8
```

结果文件包含每步坐标，例如：

```json
{"id": "s4_move", "action": "move", "status": "done",
 "t": 14205, "pos": [19.23, 19.23]}
```

坏计划（追加不可达目标）：

```
EXEC step s4_interact -> done
EXEC step s5_unreachable -> failed
EXEC unreachable s5_unreachable
EXEC_RESULT written state=paused results=9
```

## 四、边界

1. 计划坐标是**示意坐标**，不是视频真实坐标；
2. 执行模式关闭了 HLOD 场景碰撞，只保证在地面层可走；
3. 交互是“到达位置”判定，没有真正的 NPC/机关；
4. 不是真实游戏，只验证「计划 → NavMesh 执行 → 结果」闭环。
