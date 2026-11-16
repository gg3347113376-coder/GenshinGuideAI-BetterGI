import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import protocol  # noqa: E402
from ggai.review import apply_review  # noqa: E402


def sample_project():
    return {
        "schema_version": "1.0.0",
        "project": {"id": "p", "name": "t", "created_at": "2026-11-06T00:00:00+08:00"},
        "sources": [],
        "segments": [],
        "events": [
            {
                "id": "evt_000001",
                "source_id": "src_1",
                "order": 0,
                "video_time": {"start_s": 1.0, "end_s": 1.0, "precision": "second"},
                "actor": {"kind": "npc", "name": "派蒙"},
                "action": {"type": "dialogue", "params": {"text": "错误文本", "speaker": "派?"}},
                "position": {"map": {"layer": "unknown", "method": "unknown"}},
                "state_status": "observed",
                "confidence": 0.7,
                "evidence": [{"kind": "ocr", "t_s": 1.0, "path": "a.jpg", "text": "错误文本"}],
                "review": {"status": "pending"},
            },
            {
                "id": "evt_000002",
                "source_id": "src_1",
                "order": 1,
                "video_time": {"start_s": 2.0, "end_s": 2.0, "precision": "second"},
                "actor": {"kind": "npc", "name": "卡齐娜"},
                "action": {"type": "dialogue", "params": {"text": "正确文本"}},
                "position": {"map": {"layer": "unknown", "method": "unknown"}},
                "state_status": "observed",
                "confidence": 0.9,
                "evidence": [{"kind": "ocr", "t_s": 2.0, "path": "b.jpg", "text": "正确文本"}],
                "review": {"status": "pending"},
            },
        ],
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = ["序号", "人工结论", "修正文本", "修正说话人", "复核备注"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class ReviewTests(unittest.TestCase):
    def test_apply_all_verdicts(self):
        project = sample_project()
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "review.csv"
            write_csv(
                csv_path,
                [
                    {"序号": 1, "人工结论": "corrected", "修正文本": "正确文本", "修正说话人": "派蒙"},
                    {"序号": 2, "人工结论": "confirmed"},
                ],
            )
            stats = apply_review(project, csv_path)
        self.assertEqual(stats["corrected"], 1)
        self.assertEqual(stats["confirmed"], 1)
        event = project["events"][0]
        self.assertEqual(event["action"]["params"]["text"], "正确文本")
        self.assertEqual(event["action"]["params"]["speaker"], "派蒙")
        self.assertEqual(event["review"]["status"], "corrected")
        self.assertEqual(event["review"]["diff"]["before"]["text"], "错误文本")
        self.assertEqual(event["review"]["diff"]["after"]["text"], "正确文本")
        self.assertEqual(project["events"][1]["review"]["status"], "confirmed")
        self.assertEqual(protocol.validate(project), [])

    def test_bad_rows_reported(self):
        project = sample_project()
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "review.csv"
            write_csv(
                csv_path,
                [
                    {"序号": 99, "人工结论": "confirmed"},
                    {"序号": 1, "人工结论": "whatever"},
                    {"序号": 1, "人工结论": "corrected"},
                ],
            )
            stats = apply_review(project, csv_path)
        self.assertEqual(stats["skipped"], 0)
        self.assertEqual(len(stats["errors"]), 3)

    def test_rejected_marks_without_change(self):
        project = sample_project()
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "review.csv"
            write_csv(csv_path, [{"序号": 1, "人工结论": "rejected"}])
            stats = apply_review(project, csv_path)
        self.assertEqual(stats["rejected"], 1)
        event = project["events"][0]
        self.assertEqual(event["review"]["status"], "rejected")
        self.assertEqual(event["action"]["params"]["text"], "错误文本")


if __name__ == "__main__":
    unittest.main()
