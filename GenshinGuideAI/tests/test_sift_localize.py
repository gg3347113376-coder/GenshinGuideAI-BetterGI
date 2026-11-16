import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

KP = Path(r"C:\Program Files\BetterGI\Assets\Map\Teyvat\Teyvat_0_2048_SIFT.kp.bin")
DESC = Path(r"C:\Program Files\BetterGI\Assets\Map\Teyvat\Teyvat_0_2048_SIFT.mat.png")


@unittest.skipUnless(KP.exists() and DESC.exists(), "需要 BetterGI SIFT 特征")
class SiftFeatureTests(unittest.TestCase):
    def test_feature_counts_match(self):
        from sift_localize import load_features

        keypoints, descriptors = load_features()
        self.assertEqual(len(keypoints), 681139)
        self.assertEqual(descriptors.shape, (681139, 128))

    def test_keypoint_ranges(self):
        from sift_localize import load_features

        keypoints, _ = load_features()
        self.assertGreaterEqual(float(keypoints[:, 0].min()), 0.0)
        self.assertLessEqual(float(keypoints[:, 0].max()), 45056.0)
        self.assertGreaterEqual(float(keypoints[:, 1].min()), 0.0)
        self.assertLessEqual(float(keypoints[:, 1].max()), 38912.0)

    def test_image_to_game(self):
        from sift_localize import image_to_game

        self.assertEqual(image_to_game(32768.0, 24576.0), (0.0, 0.0))
        self.assertEqual(image_to_game(32768.0 - 2 * 10264, 24576.0 + 2 * 2762), (10264.0, -2762.0))


if __name__ == "__main__":
    unittest.main()
