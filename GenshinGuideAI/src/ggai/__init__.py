"""GenshinGuideAI: 原神攻略智能解析 / 三维沙盘 / 受控执行。

当前阶段：P1 统一数据协议 v1 + P2 方向一 MVP 的骨架。
"""

__version__ = "0.1.0"
SCHEMA_VERSION = "1.0.0"

ACTION_TYPES = [
    "move", "teleport", "climb", "glide", "jump", "dodge",
    "normal_attack", "charged_attack", "plunge_attack",
    "skill", "burst", "switch_character",
    "interact", "dialogue", "dialogue_choice",
    "pick", "fight_start", "fight_end", "wait", "unknown",
]
LAYERS = ["surface", "underground", "cave", "interior", "instance", "unknown"]
STATES = ["observed", "inferred", "confirmed", "unknown"]
SEGMENT_KINDS = ["travel", "combat", "interaction", "dialogue", "cutscene", "unknown"]
