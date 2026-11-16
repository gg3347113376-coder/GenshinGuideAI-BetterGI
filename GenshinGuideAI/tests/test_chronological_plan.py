import copy
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai import planning


def sample():
    project = {"evidence_index": [
        {"id": "unlock", "source_id": "video", "kind": "frame", "text": "", "time": {"start_s": 32, "end_s": 35}},
        {"id": "teleport", "source_id": "video", "kind": "asr", "text": "点击这个传送点", "time": {"start_s": 53, "end_s": 56}}]}
    draft = {"goal_target_id": "point", "steps": [
        {"id": "step_001", "action_id": "teleport", "target_id": "point", "evidence_ids": ["teleport"], "depends_on": [], "uncertainties": ["坐标未知"]},
        {"id": "step_002", "action_id": "interact", "target_id": "point", "evidence_ids": ["unlock"], "depends_on": ["step_001"], "uncertainties": []}]}
    return project, draft


class ChronologicalPlanTests(unittest.TestCase):
    def test_unlock_precedes_teleport_and_dependency_is_rebuilt(self):
        p, draft = sample(); original = copy.deepcopy(draft)
        fixed, receipt = planning.order_linear_draft(p, draft)
        self.assertEqual([s["action_id"] for s in fixed["steps"]], ["interact", "teleport"])
        self.assertEqual(fixed["steps"][0]["depends_on"], [])
        self.assertEqual(fixed["steps"][1]["depends_on"], [fixed["steps"][0]["id"]])
        self.assertEqual(draft, original)
        self.assertEqual({s["id"] for s in fixed["steps"]}, {s["id"] for s in original["steps"]})
        for step in fixed["steps"]:
            old = next(s for s in original["steps"] if s["id"] == step["id"])
            self.assertEqual({k:v for k,v in step.items() if k != "depends_on"}, {k:v for k,v in old.items() if k != "depends_on"})
        self.assertEqual(receipt["status"], "reordered")

    def test_chronological_teleport_then_other_unlock_is_not_reversed(self):
        p, draft = sample()
        p["evidence_index"][0]["time"] = {"start_s": 60, "end_s": 60}
        fixed, receipt = planning.order_linear_draft(p, draft)
        self.assertEqual(fixed, draft)
        self.assertEqual(receipt["status"], "unchanged")

    def test_branch_dependencies_are_not_rewritten(self):
        p, draft = sample(); draft["steps"][1]["depends_on"] = []
        fixed, receipt = planning.order_linear_draft(p, draft)
        self.assertEqual(fixed, draft)
        self.assertEqual(receipt["status"], "needs_review")

    def test_overlapping_instruction_windows_need_review(self):
        p, draft = sample(); p["evidence_index"][0]["time"]["end_s"] = 54
        fixed, receipt = planning.order_linear_draft(p, draft)
        self.assertEqual(fixed, draft)
        self.assertEqual(receipt["status"], "needs_review")

    def test_explicit_retrospective_or_branch_is_not_sorted(self):
        for text in ["刚才点击这个传送点", "如果已解锁就点击传送点"]:
            p, draft = sample(); p["evidence_index"][1]["text"] = text
            fixed, receipt = planning.order_linear_draft(p, draft)
            self.assertEqual(fixed, draft)
            self.assertEqual(receipt["status"], "needs_review")

    def test_unknown_evidence_and_multiple_sources_are_not_sorted(self):
        p, draft = sample(); draft["steps"][0]["evidence_ids"] = ["missing"]
        self.assertEqual(planning.order_linear_draft(p, draft)[1]["status"], "needs_review")
        p, draft = sample(); p["evidence_index"][1]["source_id"] = "other_video"
        self.assertEqual(planning.order_linear_draft(p, draft)[1]["status"], "needs_review")

    def test_pipeline_preserves_reversed_raw_draft_and_repairs_dependencies(self):
        import json
        import tempfile
        from test_grounding import grounded_fixture
        from test_semantic_review import ReviewModel
        from ggai.semantic_review import plan_with_review, reprocess_project
        from ggai import protocol

        class ReversedModel(ReviewModel):
            def structured(self, prompt, schema, **kwargs):
                response = super().structured(prompt, schema, **kwargs)
                if "GUIDE_DATA=" in prompt:
                    d = json.loads(response["message"]["content"])
                    d["steps"].reverse()
                    for i, step in enumerate(d["steps"]):
                        step["depends_on"] = [] if i == 0 else [d["steps"][i - 1]["id"]]
                        step["evidence_ids"] = ["frame_001"] if step["action_id"] == "interact" else ["asr_001"]
                    response["message"]["content"] = json.dumps(d, ensure_ascii=False)
                return response

        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); p = grounded_fixture(out)
            p["evidence_index"][0]["time"] = {"start_s": 8, "end_s": 8}
            p = plan_with_review(p, out, ReversedModel(), "test_digest")
            raw = json.loads((out / "model-draft.json").read_text(encoding="utf-8"))
            self.assertEqual([s["action_id"] for s in raw["steps"]], ["interact", "move_to"])
            steps = p["task_plan"]["steps"]
            self.assertEqual([s["action_id"] for s in steps], ["move_to", "interact"])
            self.assertEqual(steps[1]["depends_on"], [steps[0]["id"]])
            receipt = json.loads((out / "plan-order.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "reordered")
            self.assertEqual(planning.sha256(out / receipt["source_draft"]), receipt["source_sha256"])
            self.assertEqual(protocol.validate(p, out), [])
            again = out / "retry"
            reprocess_project(out / "project.json", again, ReviewModel(), "test_digest", review_only=True)
            self.assertEqual(json.loads((again / "plan-order.json").read_text(encoding="utf-8")), receipt)
            self.assertEqual(planning.sha256(again / receipt["source_draft"]), receipt["source_sha256"])
            model = ReviewModel(); recompiled = out / "recompiled"
            result = reprocess_project(out / "project.json", recompiled, model, "test_digest", recompile=True)
            self.assertTrue(all("CLAIM_AND_EVIDENCE=" in prompt for prompt in model.requests))
            self.assertEqual(result["task_plan"], p["task_plan"])
            self.assertEqual(json.loads((recompiled / "plan-order.json").read_text(encoding="utf-8")), receipt)
            self.assertEqual(protocol.validate(result, recompiled), [])

    def test_tied_timestamp_keeps_original_order(self):
        p, draft = sample(); p["evidence_index"][0]["time"] = copy.deepcopy(p["evidence_index"][1]["time"])
        fixed, receipt = planning.order_linear_draft(p, draft)
        self.assertEqual(fixed, draft)
        self.assertEqual(receipt["status"], "unchanged")


if __name__ == "__main__":
    unittest.main()
