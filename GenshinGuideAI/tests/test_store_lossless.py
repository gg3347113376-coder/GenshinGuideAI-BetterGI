import copy
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai import store

class LosslessStoreTests(unittest.TestCase):
    def setUp(self):
        self.project = json.loads((ROOT / "samples/sample_project.json").read_text(encoding="utf-8"))
        self.project["project"]["model_versions"] = {"vlm": "qwen3-vl:4b-instruct"}
        event = self.project["events"][0]
        event["sim_time"] = {"start_s": 1, "end_s": 2, "precision": "frame"}
        event["preconditions"] = ["teleport unlocked"]
        event["expected_result"] = {"text": "arrive", "checks": ["distance <= 3"]}
        event["observed_result"] = {"text": "not run", "checks": []}
        event["actor"]["confidence"] = 0.83
        event["action"]["notes"] = "uncertain"
        event["action"]["params"]["nested"] = {"nullable": None, "values": [1, False, "证据"]}
        event["review"] = {"status": "corrected", "diff": {"old": "a", "new": "b"}}

    def test_full_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "roundtrip.db"
            store.import_project(self.project, db)
            self.assertEqual(self.project, store.export_project(db))

    def test_second_project_never_deletes_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "projects.db"
            store.import_project(self.project, db)
            second = copy.deepcopy(self.project)
            second["project"]["id"] = "second"
            for source in second["sources"]:
                source["id"] = "second_" + source["id"]
            for segment in second["segments"]:
                segment["id"] = "second_" + segment["id"]
                segment["source_id"] = "second_" + segment["source_id"]
            for event in second["events"]:
                event["id"] = "second_" + event["id"]
                event["source_id"] = "second_" + event["source_id"]
                if event.get("segment_id"):
                    event["segment_id"] = "second_" + event["segment_id"]
            store.import_project(second, db)
            with closing(sqlite3.connect(db)) as conn:
                count = conn.execute("SELECT COUNT(*) FROM events WHERE project_id=?", (self.project["project"]["id"],)).fetchone()[0]
            self.assertEqual(count, len(self.project["events"]))
            self.assertEqual(store.export_project(db, self.project["project"]["id"]), self.project)
            self.assertEqual(store.export_project(db, "second"), second)
            with self.assertRaisesRegex(ValueError, "project_id"):
                store.export_project(db)

    def test_failed_import_keeps_previous_payload_and_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "rollback.db"
            store.import_project(self.project, db)
            broken = copy.deepcopy(self.project)
            broken["events"][0]["confidence"] = float("nan")
            with self.assertRaises((ValueError, sqlite3.IntegrityError)):
                store.import_project(broken, db)
            self.assertEqual(store.export_project(db), self.project)
            with closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], len(self.project["events"]))

    def test_cross_project_id_collision_is_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "collision.db"
            store.import_project(self.project, db)
            other = copy.deepcopy(self.project)
            other["project"]["id"] = "different"
            with self.assertRaisesRegex(ValueError, "another project"):
                store.import_project(other, db)
            self.assertEqual(store.export_project(db), self.project)

    def test_reimport_removes_old_events_but_preserves_run_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "update.db"
            store.import_project(self.project, db)
            with closing(sqlite3.connect(db)) as conn:
                conn.execute("INSERT INTO sim_runs(id, project_id, created_at) VALUES (?,?,?)",
                             ("old_sim", self.project["project"]["id"], "test"))
                conn.commit()
            changed = copy.deepcopy(self.project)
            changed["events"] = changed["events"][:1]
            store.import_project(changed, db)
            self.assertEqual(store.export_project(db), changed)
            with closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM sim_runs").fetchone()[0], 1)

    def test_old_db_warns_and_reimport_recovers_from_original_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy.db"
            store.import_project(self.project, db)
            with closing(sqlite3.connect(db)) as conn:
                conn.execute("DROP TABLE project_payloads")
                conn.commit()
            with self.assertWarnsRegex(UserWarning, "无法恢复"):
                legacy = store.export_project(db)
            self.assertEqual(len(legacy["events"]), len(self.project["events"]))
            self.assertEqual(legacy["project"]["model_versions"], {})
            store.import_project(self.project, db)
            self.assertEqual(store.export_project(db), self.project)

if __name__ == "__main__":
    unittest.main()
