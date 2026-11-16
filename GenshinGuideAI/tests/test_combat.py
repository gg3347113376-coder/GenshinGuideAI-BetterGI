import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.combat import BossCapDetector, filter_sequence, windows_from_hits  # noqa: E402


class CombatTests(unittest.TestCase):
    def test_template_scores_self(self):
        import cv2

        detector = BossCapDetector()
        canvas = np.zeros((1080, 1920, 3), dtype=np.uint8)
        h, w = detector.template.shape[:2]
        canvas[100 : 100 + h, 600 : 600 + w] = detector.template
        score = detector.score(canvas)
        self.assertGreaterEqual(score, 0.9)

    def test_blank_frame_no_bar(self):
        detector = BossCapDetector()
        hit, score = detector.hit(np.zeros((1080, 1920, 3), dtype=np.uint8))
        self.assertFalse(hit)
        self.assertLess(score, 0.55)

    def test_windows_merge(self):
        samples = [
            {"t": 0, "hit": True},
            {"t": 1, "hit": True},
            {"t": 2, "hit": False},
            {"t": 12, "hit": True},
            {"t": 13, "hit": True},
        ]
        self.assertEqual(windows_from_hits(samples, gap_s=8), [[0, 1], [12, 13]])

    def test_filter_requires_consecutive(self):
        samples = [
            {"t": 0, "hit": True, "y": 100},
            {"t": 1, "hit": True, "y": 101},
            {"t": 2, "hit": False, "y": 0},
            {"t": 3, "hit": True, "y": 100},
        ]
        kept = filter_sequence(samples, min_consecutive=2)
        self.assertEqual([s["t"] for s in kept], [0, 1])


if __name__ == "__main__":
    unittest.main()
