import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import av  # noqa: E402

from ggai import video  # noqa: E402


def make_test_video(path: Path, seconds: int = 4, fps: int = 10) -> None:
    container = av.open(str(path), "w")
    try:
        stream = container.add_stream("mpeg4", rate=fps)
        stream.width = 320
        stream.height = 180
        stream.pix_fmt = "yuv420p"
        total = seconds * fps
        for i in range(total):
            color = (0, 0, 255) if i < total // 2 else (255, 0, 0)
            image = np.full((180, 320, 3), color, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()


class VideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "test.mp4"
        make_test_video(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_probe(self):
        info = video.probe(self.path)
        self.assertGreater(info.duration_s, 3.5)
        self.assertLess(info.duration_s, 4.6)
        self.assertEqual(info.width, 320)
        self.assertEqual(info.height, 180)
        self.assertEqual(len(info.sha256), 64)

    def test_sampled_frames(self):
        frames = list(video.iter_sampled_frames(self.path, sample_fps=1.0))
        self.assertGreaterEqual(len(frames), 3)
        for t, frame in frames:
            self.assertEqual(frame.shape[2], 3)

    def test_scene_cut(self):
        cuts = video.scene_cuts(self.path, sample_fps=2.0, threshold=0.55)
        self.assertTrue(cuts, "应当检测到颜色切换")
        self.assertTrue(any(1.5 <= c <= 2.6 for c in cuts), cuts)

    def test_extract_frames(self):
        out = Path(self.tmp.name) / "frames"
        saved = video.extract_frames(self.path, [0.5, 2.5], out)
        self.assertEqual(len(saved), 2)
        for p in saved:
            self.assertTrue(p.exists() and p.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
