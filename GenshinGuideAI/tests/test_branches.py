import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.branches import BranchSpec, check_constraints, compare, run_branch  # noqa: E402
from ggai.executor import Faults  # noqa: E402


class BranchTests(unittest.TestCase):
    def test_detour_takes_more_actions(self):
        direct = run_branch(BranchSpec(id="a", name="直达", nodes=[(5, 5), (10, 10)], seed=3))
        detour = run_branch(BranchSpec(id="b", name="绕行", nodes=[(5, 14), (10, 14)], seed=3))
        self.assertTrue(direct["completed"])
        self.assertTrue(detour["completed"])
        self.assertGreater(detour["actions"], direct["actions"])

    def test_constraint_rejects_wall_node(self):
        spec = BranchSpec(id="c", name="穿墙", nodes=[(10, 10)], walls={(10, 10)})
        self.assertTrue(check_constraints(spec))
        result = run_branch(spec)
        self.assertFalse(result["valid"])
        self.assertFalse(result["completed"])

    def test_deterministic_with_same_seed(self):
        spec = BranchSpec(id="d", name="漂移", nodes=[(5, 5), (10, 10)], faults=Faults(drift_prob=0.2), seed=11)
        first = run_branch(spec)
        second = run_branch(spec)
        self.assertEqual(first["actions"], second["actions"])
        self.assertEqual(first["retries"], second["retries"])
        self.assertEqual(first["ticks"], second["ticks"])

    def test_compare_picks_completed_shortest(self):
        result = compare(
            [
                BranchSpec(id="a", name="直达", nodes=[(5, 5)], seed=1),
                BranchSpec(id="b", name="绕行", nodes=[(5, 14), (10, 14)], seed=1),
                BranchSpec(id="c", name="无效", nodes=[(10, 10)], walls={(10, 10)}),
            ]
        )
        self.assertEqual(result["winner"], "a")
        self.assertEqual(len(result["branches"]), 3)


if __name__ == "__main__":
    unittest.main()
