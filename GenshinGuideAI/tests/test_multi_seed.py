import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import simstore  # noqa: E402
from ggai.branches import BranchSpec, evaluate  # noqa: E402


class MultiSeedTests(unittest.TestCase):
    def test_evaluate_no_faults(self):
        spec = BranchSpec(id="a", name="直达", nodes=[(5, 5)], seed=0)
        summary = evaluate(spec, [1, 2, 3])
        self.assertEqual(summary["completion_rate"], 1.0)
        self.assertEqual(summary["actions_std"], 0.0)
        self.assertEqual(summary["valid_runs"], 3)

    def test_evaluate_reports_variation(self):
        from ggai.executor import Faults

        spec = BranchSpec(id="b", name="漂移", nodes=[(5, 5), (10, 10)], faults=Faults(drift_prob=0.3), seed=0)
        summary = evaluate(spec, list(range(5)))
        self.assertGreater(summary["valid_runs"], 0)
        self.assertGreaterEqual(summary["actions_std"], 0.0)

    def test_simstore_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "sim.db"
            run_id = simstore.save_sim_run(
                db,
                project_id="proj_test",
                params={"branch_id": "A", "nodes": [[5, 5]]},
                rules_ver="rules-v1",
                seed=7,
                status="completed",
                result={"actions": 31, "retries": 0},
            )
            self.assertTrue(run_id.startswith("sim_"))
            rows = simstore.list_sim_runs(db, "proj_test")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["seed"], 7)
            self.assertEqual(rows[0]["params"]["branch_id"], "A")
            self.assertEqual(rows[0]["result"]["actions"], 31)


if __name__ == "__main__":
    unittest.main()
