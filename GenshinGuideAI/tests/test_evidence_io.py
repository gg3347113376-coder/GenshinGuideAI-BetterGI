import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai.images import save_image
from ggai.pipeline import build_project


class EvidenceIOTests(unittest.TestCase):
    def test_unicode_path_and_pixels_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "真实证据.png"
            pixels = np.full((8, 8, 3), 127, dtype=np.uint8)
            save_image(path, pixels)
            decoded = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
            np.testing.assert_array_equal(decoded, pixels)

    def test_encode_failure_is_not_reported_as_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.png"
            with patch("ggai.images.cv2.imencode", return_value=(False, None)):
                with self.assertRaises(OSError):
                    save_image(path, np.zeros((8, 8, 3), dtype=np.uint8))
            self.assertFalse(path.exists())

    def test_existing_pipeline_saves_unicode_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "project.json"
            info = SimpleNamespace(duration_s=1, fps=1, width=1280, height=720, sha256="a" * 64)
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            with patch("ggai.pipeline.video.probe", return_value=info), patch(
                "ggai.pipeline.video.iter_sampled_frames", return_value=iter([(0.0, frame)])), patch(
                "ggai.pipeline.make_ocr", return_value=SimpleNamespace(recognize=lambda image: [])):
                result = build_project("fake.mp4", output, frames_dir=Path(tmp) / "中文帧目录", ocr_mode="regions", verbose=False)
            self.assertEqual(result["saved_frames"], 1)
            self.assertTrue((Path(tmp) / "中文帧目录/f_00000.00.jpg").is_file())
            self.assertTrue(output.with_suffix(".obs.jsonl").is_file())

if __name__ == "__main__":
    unittest.main()
