import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.vlm import OllamaVLM, classify_scene  # noqa: E402


class FakeVLM(OllamaVLM):
    def __init__(self, response: str):
        super().__init__()
        self.response = response

    def describe(self, image_path, prompt, timeout=300):  # noqa: ARG002
        return self.response


class VlmTests(unittest.TestCase):
    def test_parse_strict_json(self):
        vlm = FakeVLM('{"scene": "dialogue", "confidence": 0.9, "reason": "底部有字幕"}')
        result = classify_scene(vlm, "dummy.jpg")
        self.assertEqual(result["scene"], "dialogue")
        self.assertAlmostEqual(result["confidence"], 0.9)

    def test_parse_json_with_wrapper_text(self):
        vlm = FakeVLM('分类如下：\n{"scene":"combat","confidence":0.8,"reason":"有伤害数字"}\n以上。')
        result = classify_scene(vlm, "dummy.jpg")
        self.assertEqual(result["scene"], "combat")

    def test_unparseable_returns_unknown(self):
        vlm = FakeVLM("这是一张游戏截图")
        result = classify_scene(vlm, "dummy.jpg")
        self.assertEqual(result["scene"], "unknown")
        self.assertEqual(result["confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()
