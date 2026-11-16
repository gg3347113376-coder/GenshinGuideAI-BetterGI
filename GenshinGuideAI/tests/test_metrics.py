import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import metrics  # noqa: E402


class MetricsTests(unittest.TestCase):
    def test_levenshtein(self):
        self.assertEqual(metrics.levenshtein("abc", "abc"), 0)
        self.assertEqual(metrics.levenshtein("abc", "abd"), 1)
        self.assertEqual(metrics.levenshtein("", "abc"), 3)

    def test_similarity_ignores_punctuation(self):
        a = "你好，世界！"
        b = "你好世界"
        self.assertAlmostEqual(metrics.text_similarity(a, b), 1.0, places=3)

    def test_coverage(self):
        project = {
            "events": [
                {"confidence": 0.8, "evidence": [{"path": "a.jpg"}],
                 "position": {"map": {"x": 1, "y": 2}}, "review": {"status": "pending"}},
                {"confidence": 0.6, "evidence": [], "position": {"map": {"x": None, "y": None}},
                 "review": {"status": "confirmed"}},
            ]
        }
        result = metrics.project_coverage(project)
        self.assertEqual(result["events"], 2)
        self.assertEqual(result["with_evidence"], 1)
        self.assertEqual(result["with_coords"], 1)
        self.assertAlmostEqual(result["evidence_ratio"], 0.5)

    def test_match_gold(self):
        project = {
            "events": [
                {"video_time": {"start_s": 10.0}, "action": {"type": "dialogue", "params": {"text": "你好世界", "speaker": "派蒙"}}},
                {"video_time": {"start_s": 50.0}, "action": {"type": "dialogue", "params": {"text": "别的话", "speaker": "卡齐娜"}}},
            ]
        }
        matches = metrics.match_gold(project, [{"t": 11, "speaker": "派蒙", "text": "你好，世界"}])
        summary = metrics.summarize_matches(matches)
        self.assertEqual(summary["matched"], 1)
        self.assertGreaterEqual(summary["mean_similarity"], 0.99)
        self.assertEqual(summary["speaker_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
