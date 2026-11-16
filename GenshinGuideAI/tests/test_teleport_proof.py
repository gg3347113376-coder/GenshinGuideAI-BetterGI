import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai.targets import teleport_instruction_issues
from ggai.semantic_review import bound_draft_schema, item_inputs, plan_with_review
from test_grounding import grounded_fixture
import test_semantic_review


class TeleportProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.out = Path(self.temp.name)
        self.p = grounded_fixture(self.out)
        self.p = plan_with_review(self.p, self.out, test_semantic_review.ReviewModel(), "test_digest")
    def tearDown(self):
        self.temp.cleanup()
    def teleport(self, source, role="map_selection"):
        target = self.p["target_registry"]["entities"][0]
        target.update(kind="waypoint", role=role)
        step = self.p["task_plan"]["steps"][0]
        step.update(action_id="teleport", instruction_evidence_ids=["asr_001"])
        self.p["grounding"]["transcripts"][0].update(original=source, alternative=None)
        return step
    def test_unlock_target_is_not_a_map_teleport_destination(self):
        self.teleport("点击这个传送锚点", role="world_interaction")
        self.assertTrue(teleport_instruction_issues(self.p))
        choices = bound_draft_schema(self.p)["properties"]["steps"]["items"]["oneOf"]
        self.assertFalse(any(c["properties"]["action_id"]["const"] == "teleport" for c in choices))
    def test_nearby_waypoint_is_not_a_teleport_instruction(self):
        self.teleport("我们在这个传送点旁边")
        self.assertTrue(teleport_instruction_issues(self.p))
    def test_explaining_teleport_is_not_a_command(self):
        self.teleport("这个传送锚点是可以传送的")
        self.assertTrue(teleport_instruction_issues(self.p))
    def test_region_cannot_be_promoted_to_unique_waypoint(self):
        step = self.teleport("你点击这个传送某点")
        step.update(title="传送到名为测试地区的唯一锚点", intent="把地区视作已确认唯一身份")
        self.assertIn("unproven_waypoint_identity", [i["code"] for i in teleport_instruction_issues(self.p)])
        step.update(title="传送到锚点，唯一身份待核验", intent="唯一身份未知")
        self.assertEqual(teleport_instruction_issues(self.p), [])
    def test_clicking_selected_waypoint_has_direct_support(self):
        self.teleport("你点击这个传送某点")
        self.assertEqual(teleport_instruction_issues(self.p), [])
    def test_narrated_start_can_keep_unresolved_original_words(self):
        self.teleport("我们现在回到这个传统膜带", role="narrated_start")
        self.assertEqual(teleport_instruction_issues(self.p), [])
    def test_target_evidence_cannot_replace_instruction_reference(self):
        step = self.teleport("你点击这个传送锚点")
        step["instruction_evidence_ids"] = []
        self.assertTrue(teleport_instruction_issues(self.p))
    def test_background_region_is_excluded_from_action_support(self):
        old = item_inputs(self.p, version="1.5.0")["goal"]["evidence"]
        current = item_inputs(self.p)["goal"]["evidence"]
        self.assertTrue(any(row["source"] == "map_region" for row in old))
        self.assertFalse(any(row["source"] == "map_region" for row in current))
    def test_teleport_schema_cannot_use_a_goal_intro_as_instruction(self):
        import copy
        import jsonschema
        self.teleport("这是一个隐藏锚点", role="narrated_start")
        target = self.p["target_registry"]["entities"][0]
        target["evidence_ids"] = ["asr_002"]
        ev = copy.deepcopy(self.p["evidence_index"][1]); ev["id"] = "asr_002"
        self.p["evidence_index"].append(ev)
        row = copy.deepcopy(self.p["grounding"]["transcripts"][0])
        row.update(evidence_id="asr_002", original="首先来到这个传统猫点", alternative="首先来到这个传送锚点")
        self.p["grounding"]["transcripts"].append(row)
        choices = bound_draft_schema(self.p)["properties"]["steps"]["items"]["oneOf"]
        choice = next(c for c in choices if c["properties"]["action_id"]["const"] == "teleport")
        evidence_schema = choice["properties"]["evidence_ids"]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(["asr_001"], evidence_schema)
        jsonschema.validate(["asr_002"], evidence_schema)

    def test_planner_and_reviewer_keep_distinct_model_identity(self):
        with tempfile.TemporaryDirectory() as name:
            out = Path(name); p = grounded_fixture(out)
            planner = test_semantic_review.ReviewModel(); planner.model = "planner_test"
            reviewer = test_semantic_review.ReviewModel(); reviewer.model = "reviewer_test"
            p = plan_with_review(p, out, planner, "planner_digest", reviewer=(reviewer, "reviewer_digest"))
            self.assertTrue(all("GUIDE_DATA=" in request for request in planner.requests))
            self.assertTrue(all("CLAIM_AND_EVIDENCE=" in request for request in reviewer.requests))
            versions = p["project"]["model_versions"]
            self.assertEqual(versions["task_understanding"], "planner_test@planner_digest")
            self.assertEqual(versions["semantic_review"], "reviewer_test@reviewer_digest")
            for rid in p["semantic_review"]["item_run_ids"].values():
                trace = next(r for r in p["analysis_runs"] if r["id"] == rid)
                self.assertEqual((trace["model"], trace["model_digest"]), ("reviewer_test", "reviewer_digest"))
            self.assertEqual(test_semantic_review.protocol.validate(p, out), [])


if __name__ == "__main__":
    unittest.main()
