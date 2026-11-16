import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import lexicon  # noqa: E402


class LexiconTests(unittest.TestCase):
    def test_fix_same_length_substitution(self):
        self.assertEqual(lexicon.correct_text("鸟沙博蒂"), "乌沙博蒂")
        self.assertEqual(lexicon.correct_text("中来已久"), "由来已久")

    def test_do_not_touch_function_word_prefix(self):
        # 「和锋龙」不应被改成「嵴锋龙」（会吞掉「和」）
        self.assertEqual(lexicon.correct_text("人和锋龙的关系"), "人和锋龙的关系")

    def test_do_not_touch_punctuation_window(self):
        self.assertEqual(lexicon.correct_text("，锋龙也是"), "，锋龙也是")

    def test_short_terms_untouched(self):
        self.assertEqual(lexicon.correct_text("纳塔"), "纳塔")

    def test_correct_project_counts(self):
        project = {
            "events": [
                {"action": {"params": {"text": "鸟沙博蒂"}}, "observed_result": {"text": "鸟沙博蒂"}},
                {"action": {"params": {"text": "无关文本"}}, "observed_result": {"text": "无关文本"}},
            ]
        }
        stats = lexicon.correct_project(project)
        self.assertEqual(stats["events"], 2)
        self.assertGreaterEqual(stats["changed"], 2)
        self.assertEqual(project["events"][0]["action"]["params"]["text"], "乌沙博蒂")


if __name__ == "__main__":
    unittest.main()
