import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import protocol  # noqa: E402
from ggai.extract import Observation, extract_events  # noqa: E402
from ggai.ocr import OcrItem  # noqa: E402


def obs(t, quest=None, subtitle=None, frame=None):
    regions = {}
    if quest is not None:
        regions["quest_tracker"] = [OcrItem(text=quest, box=(10, 10, 100, 20), score=0.9)]
    if subtitle is not None:
        regions["subtitle"] = [OcrItem(text=subtitle, box=(100, 800, 600, 30), score=0.9)]
    return Observation(t_s=t, regions=regions, frame_path=frame)


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.project = protocol.new_project("proj_test", "测试")

    def test_dedup_repeated_subtitle(self):
        observations = [
            obs(1, subtitle="你看，墙上有好多图案。"),
            obs(2, subtitle="你看，墙上有好多图案。"),
            obs(3, subtitle="你看，墙上有好多图案。"),
            obs(4, subtitle="至少说明我们走对了！"),
            obs(5, subtitle="至少说明我们走对了！"),
        ]
        events = extract_events(self.project, "src_1", observations)
        dialogues = [e for e in events if e["action"]["type"] == "dialogue"]
        self.assertEqual(len(dialogues), 2, [e["action"]["params"].get("text") for e in dialogues])

    def test_quest_emits_once_on_change(self):
        observations = [
            obs(1, quest="纳塔！新的旅程 深入纳塔"),
            obs(2, quest="纳塔！新的旅程 深入纳塔"),
            obs(3, quest="纳塔！新的旅程 深入纳塔 低处24m"),
            obs(4, quest="纳塔！新的旅程 深入纳塔"),
        ]
        events = extract_events(self.project, "src_1", observations)
        moves = [e for e in events if e["action"]["type"] == "move"]
        self.assertEqual(len(moves), 1)

    def test_events_validate(self):
        observations = [
            obs(1, quest="纳塔！新的旅程 深入纳塔", subtitle="派蒙 你看"),
            obs(2, quest="纳塔！新的旅程 深入纳塔", subtitle="派蒙 你看"),
            obs(3, subtitle="你看，墙上有好多花花绿绿的图案。"),
            obs(4, subtitle="你看，墙上有好多花花绿绿的图案。"),
        ]
        extract_events(self.project, "src_1", observations)
        self.assertEqual(protocol.validate(self.project), [])


if __name__ == "__main__":
    unittest.main()
