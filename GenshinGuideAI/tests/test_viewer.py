import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import build_viewer  # noqa: E402


class ViewerTests(unittest.TestCase):
    def test_build_copies_frame_and_embeds_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            frame = tmp_path / "ev.jpg"
            frame.write_bytes(b"\xff\xd8\xff\xd9")  # 最小 JPEG 头尾，仅用于复制
            project = {
                "events": [
                    {
                        "video_time": {"start_s": 12.5},
                        "action": {"type": "dialogue", "params": {"speaker": "派蒙", "text": "测试文本"}},
                        "confidence": 0.9,
                        "evidence": [{"kind": "frame", "path": str(frame)}],
                        "review": {"status": "pending"},
                    }
                ]
            }
            project_path = tmp_path / "p.json"
            project_path.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
            out_dir = tmp_path / "viewer"
            result = build_viewer.build(project_path, out_dir)
            self.assertEqual(result["events"], 1)
            self.assertEqual(result["frames_copied"], 1)
            html = (out_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("测试文本", html)
            self.assertIn("证据查看器", html)
            self.assertEqual(len(list((out_dir / "frames").iterdir())), 1)

    def test_missing_frame_still_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            project = {
                "events": [
                    {
                        "video_time": {"start_s": 1.0},
                        "action": {"type": "move", "params": {"quest_text": "前往目标"}},
                        "confidence": 0.5,
                        "evidence": [],
                        "review": {"status": "pending"},
                    }
                ]
            }
            project_path = tmp_path / "p.json"
            project_path.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
            out_dir = tmp_path / "viewer"
            result = build_viewer.build(project_path, out_dir)
            self.assertEqual(result["frames_copied"], 0)
            self.assertTrue((out_dir / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
