import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.extract import Observation  # noqa: E402
from ggai.ocr import OcrItem  # noqa: E402
from ggai.segmentation import classify_segments, coverage  # noqa: E402


def obs(t, subtitle=None):
    regions = {}
    if subtitle:
        regions["subtitle"] = [OcrItem(text=subtitle, box=(0, 800, 100, 20), score=0.9)]
    return Observation(t_s=t, regions=regions)


class SegmentationTests(unittest.TestCase):
    def test_split_dialogue_and_travel(self):
        observations = [
            obs(0, "第一句"),
            obs(1, "第二句"),
            obs(2, "第三句"),
            obs(3),
            obs(4),
            obs(5),
            obs(6),
            obs(7),
            obs(8, "回到对话"),
            obs(9, "继续对话"),
        ]
        segments = classify_segments(observations, min_duration_s=1.0)
        kinds = [s["kind"] for s in segments]
        self.assertEqual(kinds, ["dialogue", "travel", "dialogue"])
        self.assertTrue(all(s["id"].startswith("seg_") for s in segments))

    def test_short_span_merged(self):
        observations = [obs(0, "对话一"), obs(1, "对话二"), obs(2), obs(3, "对话三"), obs(4, "对话四")]
        segments = classify_segments(observations, min_duration_s=2.0)
        self.assertEqual([s["kind"] for s in segments], ["dialogue"])

    def test_coverage(self):
        segments = [
            {"start_s": 0, "end_s": 10, "kind": "dialogue"},
            {"start_s": 10, "end_s": 30, "kind": "travel"},
        ]
        result = coverage(segments)
        self.assertEqual(result["dialogue_s"], 10)
        self.assertAlmostEqual(result["dialogue_ratio"], 0.333, places=2)


if __name__ == "__main__":
    unittest.main()
