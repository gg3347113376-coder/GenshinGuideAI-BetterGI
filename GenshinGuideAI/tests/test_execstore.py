import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import execstore  # noqa: E402


class ExecStoreTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "runs.db"
            report = {
                "steps": 8,
                "state": "done",
                "results": [
                    {"id": "s1_move", "action": "move", "status": "done", "pos": [-19.2, -19.2]},
                ],
            }
            run_id = execstore.save_exec_run(
                db, env="godot_sandbox", status="done", report=report, sim_run_id="sim_abc"
            )
            self.assertTrue(run_id.startswith("exec_"))
            rows = execstore.list_exec_runs(db)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["env"], "godot_sandbox")
            self.assertEqual(rows[0]["status"], "done")
            self.assertEqual(rows[0]["sim_run_id"], "sim_abc")
            self.assertEqual(rows[0]["report"]["results"][0]["id"], "s1_move")

    def test_list_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "runs.db"
            for i in range(3):
                execstore.save_exec_run(db, env="e", status="done", report={"i": i})
            rows = execstore.list_exec_runs(db, limit=2)
            self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
