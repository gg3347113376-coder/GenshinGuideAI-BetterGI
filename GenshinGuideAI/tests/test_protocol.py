import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import protocol, store  # noqa: E402

SAMPLE = ROOT / "samples" / "sample_project.json"


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.project = json.loads(SAMPLE.read_text(encoding="utf-8"))

    def test_sample_validates(self):
        self.assertEqual(protocol.validate(self.project), [])

    def test_missing_action_fails(self):
        broken = copy.deepcopy(self.project)
        del broken["events"][0]["action"]
        errors = protocol.validate(broken)
        self.assertTrue(errors)
        self.assertTrue(any("action" in e for e in errors))

    def test_unknown_position_allowed(self):
        project = copy.deepcopy(self.project)
        project["events"][0]["position"]["map"].update(
            {"x": None, "y": None, "method": "unknown", "layer": "unknown"}
        )
        self.assertEqual(protocol.validate(project), [])

    def test_bad_layer_rejected(self):
        project = copy.deepcopy(self.project)
        project["events"][0]["position"]["map"]["layer"] = "sky"
        self.assertTrue(protocol.validate(project))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.project = json.loads(SAMPLE.read_text(encoding="utf-8"))

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            result = store.import_project(self.project, db)
            self.assertEqual(result["events"], 3)
            exported = store.export_project(db)
            self.assertEqual(exported["project"]["id"], self.project["project"]["id"])
            self.assertEqual(len(exported["events"]), 3)
            self.assertEqual(protocol.validate(exported), [])
            self.assertEqual(
                exported["events"][2]["action"]["type"],
                self.project["events"][2]["action"]["type"],
            )

    def test_summary(self):
        summary = protocol.summarise(self.project)
        self.assertEqual(summary["events"], 3)
        self.assertEqual(summary["review_pending"], 3)


if __name__ == "__main__":
    unittest.main()
