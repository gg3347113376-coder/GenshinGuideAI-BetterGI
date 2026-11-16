# 执行结果归档（exec_runs 表）

- 工具：`tools/archive_exec.py`
- 存储：`src/ggai/execstore.py` → `runs/sim_runs.db` 的 `exec_runs` 表
- 测试：`tests/test_execstore.py`（2 个）

## 一、作用

把沙盘执行结果（`sandbox/data/exec_result.json`）归档到独立的 `exec_runs` 表，与视频事件、仿真结果分开保存，落实协议里「三类结果分开存」的要求。

## 二、表结构

```sql
exec_runs(
  id TEXT PRIMARY KEY,          -- exec_xxxxxxxxxxxx
  sim_run_id TEXT,              -- 可关联仿真运行（当前可空）
  created_at TEXT,
  env TEXT,                     -- godot_sandbox / 其它
  status TEXT,                  -- done / paused
  report TEXT                   -- 完整执行结果 JSON
)
```

## 三、使用

```powershell
# 归档一次沙盘执行
python tools\archive_exec.py --result sandbox\data\exec_result.json --env godot_sandbox

# 列出归档记录
python tools\archive_exec.py --list
```

实际输出：

```
{"id": "exec_062868403cef", "env": "godot_sandbox", "status": "done", "db": "...sim_runs.db"}
2026-11-06T21:47:09+08:00  exec_062868403cef  env=godot_sandbox  status=done  steps=8
{"count": 1}
```

## 四、验证

- 归档后 `exec_runs` 新增 1 行，`report.results` 含 8 步的位置与状态；
- 单元测试覆盖：往返读写、sim_run_id 关联字段、列表 limit。

## 五、边界

- 只归档沙盘（Godot）执行，未接真实环境；
- `sim_run_id` 目前为空，尚未把某次仿真与某次执行自动关联；
- 没有图形界面，只有 CLI 列表。
