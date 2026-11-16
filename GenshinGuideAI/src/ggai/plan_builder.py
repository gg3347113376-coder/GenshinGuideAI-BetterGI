"""把方向一的事件 JSON 转成可执行的示意计划（无真实坐标，仅用于链路验证）。"""
from __future__ import annotations

from .executor import Plan, Step


def plan_from_events(project: dict, max_events: int = 12) -> tuple[Plan, dict]:
    """按事件顺序生成示意计划。

    - move 事件 → 移动到下一个示意节点
    - dialogue/interact/dialogue_choice → 在当前节点交互
    节点是固定示意位置，**不代表真实坐标**。
    """
    nodes = [(3, 3), (6, 6), (9, 9), (12, 12), (15, 15)]
    events = project.get("events", [])[:max_events]
    steps: list[Step] = []
    current = (1, 1)
    node_index = 0
    for index, event in enumerate(events):
        action = event.get("action", {})
        kind = action.get("type", "unknown")
        params = action.get("params", {})
        text = str(params.get("text") or params.get("quest_text") or "")[:24]
        if kind == "move":
            target = nodes[node_index % len(nodes)]
            node_index += 1
            current = target
            steps.append(
                Step(
                    id=f"evt_{index:03d}",
                    goal=f"移动到示意节点 {target}：{text}",
                    action="move",
                    expected="到达示意节点",
                    target=target,
                )
            )
        elif kind in ("dialogue", "interact", "dialogue_choice"):
            steps.append(
                Step(
                    id=f"evt_{index:03d}",
                    goal=f"在 {current} 交互：{text}",
                    action="interact",
                    expected="交互成功",
                    target=current,
                )
            )
    meta = {
        "events_used": len(events),
        "steps": len(steps),
        "note": "节点位置为示意，不是视频中的真实坐标",
    }
    return Plan(steps=steps), meta
