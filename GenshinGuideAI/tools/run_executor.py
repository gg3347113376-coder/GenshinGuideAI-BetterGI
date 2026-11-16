"""方向三：在模拟环境中批量跑故障注入，输出指标报告。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.executor import (  # noqa: E402
    ExecReport,
    Executor,
    Faults,
    GridWorld,
    Plan,
    SafetyPolicy,
    SafetySupervisor,
    Step,
)


def build_plan() -> Plan:
    return Plan(
        steps=[
            Step(id="s1", goal="走到目标", action="move", expected="到达目标格"),
            Step(id="s2", goal="交互", action="interact", expected="交互成功"),
        ]
    )


def scenario(name: str):
    walls = set()
    faults = Faults()
    if name == "clean":
        pass
    elif name == "drift":
        faults = Faults(drift_prob=0.2)
    elif name == "lost":
        faults = Faults(lost_prob=0.2)
    elif name == "timeout":
        faults = Faults(timeout_prob=0.2)
    elif name == "blocked":
        walls = {(7, y) for y in range(0, 12)}
    elif name == "chaos":
        walls = {(7, y) for y in range(0, 12)}
        faults = Faults(drift_prob=0.1, lost_prob=0.1, timeout_prob=0.1)
    else:
        raise ValueError(name)
    return walls, faults


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--out", default="docs/reports/P6_executor.md")
    args = parser.parse_args()
    scenarios = ["clean", "drift", "lost", "timeout", "blocked", "chaos"]
    results = {}
    for name in scenarios:
        walls, faults = scenario(name)
        completed = 0
        actions = []
        retries = []
        ticks = []
        pauses = 0
        l1 = 0
        l2 = 0
        for seed in range(args.seeds):
            world = GridWorld(
                target=(15, 15), walls=set(walls), faults=faults, seed=seed
            )
            safety = SafetySupervisor(SafetyPolicy(max_total_retries=80))
            report = Executor(world, safety, max_ticks=2000).run(build_plan(), ExecReport())
            completed += 1 if report.completed else 0
            actions.append(report.actions)
            retries.append(report.retries)
            ticks.append(report.ticks)
            pauses += report.pauses
            l1 += report.level_events.get("l1_drift", 0)
            l2 += report.level_events.get("l2_action_lost", 0) + report.level_events.get("l2_blocked", 0)
        n = args.seeds
        results[name] = {
            "completion_rate": round(completed / n, 3),
            "mean_actions": round(sum(actions) / n, 1),
            "mean_retries": round(sum(retries) / n, 1),
            "mean_ticks": round(sum(ticks) / n, 1),
            "pauses": pauses,
            "l1_drift_events": l1,
            "l2_events": l2,
        }

    lines = [
        "# P6 方向三：模拟环境闭环执行报告",
        "",
        f"- 场景数：{len(scenarios)}；每场景种子数：{args.seeds}",
        "- 环境：20×20 网格，起点 (1,1)，目标 (15,15)，障碍墙 x=7（blocked/chaos）",
        "- 执行器：A* 战术规划 + 执行反馈 + L1–L4 纠错 + 安全监督",
        "",
        "| 场景 | 完成率 | 平均动作 | 平均重试 | 平均时钟 | 暂停次数 | L1 漂移 | L2 事件 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name in scenarios:
        r = results[name]
        lines.append(
            f"| {name} | {r['completion_rate']:.0%} | {r['mean_actions']} | {r['mean_retries']} | "
            f"{r['mean_ticks']} | {r['pauses']} | {r['l1_drift_events']} | {r['l2_events']} |"
        )
    lines += [
        "",
        "## 说明",
        "",
        "- 完成率 = 两个步骤（移动 + 交互）都成功的比例；",
        "- L1 漂移 = 位置偏移后的局部调整次数；L2 事件 = 动作丢失/阻塞后的本步重规划；",
        "- 超时/失败超过重试上限会触发 L4 安全暂停（计入暂停次数）；",
        "- 本报告只在模拟环境产生，**不代表真实游戏成功率**。",
        "",
    ]
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    summary = {"scenarios": results, "report": str(out)}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
