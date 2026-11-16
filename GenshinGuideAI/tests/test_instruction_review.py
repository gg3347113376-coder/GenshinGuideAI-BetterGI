import copy
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai.targets import goal_candidates, sequence_issues
from ggai.semantic_review import review_input, review_model_schema, item_inputs, item_judgment
import test_semantic_review


def sequence_fixture():
    return {"target_registry": {"entities": [
        {"id": "start", "kind": "waypoint", "role": "narrated_start"},
        {"id": "goal", "kind": "waypoint", "role": "narrated_goal"},
        {"id": "east", "kind": "location", "role": "relative_location"}]},
        "evidence_index": [{"id": "a" + str(i), "kind": "asr", "time": {"start_s": i, "end_s": i + .5}} for i in range(1, 5)],
        "task_plan": {"goal_target_ref": "goal", "steps": [
            {"id": "step_001", "action_id": "teleport", "target_ref": "start", "evidence_ids": ["a1"], "instruction_evidence_ids": ["a1"]},
            {"id": "step_002", "action_id": "move_to", "target_ref": "east", "evidence_ids": ["a2"], "instruction_evidence_ids": ["a2"]}]}}


class InstructionReviewTests(unittest.TestCase):
    def test_explicit_goal_does_not_allow_start_substitution(self):
        p = sequence_fixture()
        self.assertEqual(goal_candidates(p), ["goal"])
        p["task_plan"]["goal_target_ref"] = "start"
        self.assertIn("goal_role_mismatch", [x["code"] for x in sequence_issues(p)])

    def test_route_prefix_need_not_reach_total_goal(self):
        self.assertEqual(sequence_issues(sequence_fixture()), [])

    def test_reusing_start_instruction_is_not_a_return_instruction(self):
        p = sequence_fixture()
        step = copy.deepcopy(p["task_plan"]["steps"][0]); step["id"] = "step_003"
        p["task_plan"]["steps"].append(step)
        codes = [x["code"] for x in sequence_issues(p)]
        self.assertIn("repeated_instruction", codes)
        self.assertIn("instruction_order", codes)

    def test_explicit_later_return_is_allowed(self):
        p = sequence_fixture()
        step = copy.deepcopy(p["task_plan"]["steps"][0])
        step.update(id="step_003", evidence_ids=["a1", "a3"], instruction_evidence_ids=["a3"])
        p["task_plan"]["steps"].append(step)
        self.assertEqual(sequence_issues(p), [])

    def test_reversed_route_cannot_reuse_later_target_evidence(self):
        p = sequence_fixture()
        p["task_plan"]["steps"][0].update(evidence_ids=["a1", "a4"], instruction_evidence_ids=["a4"])
        self.assertIn("instruction_order", [x["code"] for x in sequence_issues(p)])

    def test_missing_instruction_cannot_be_hidden_by_target_evidence(self):
        p = sequence_fixture()
        p["task_plan"]["steps"][1]["instruction_evidence_ids"] = []
        self.assertIn("missing_instruction_evidence", [x["code"] for x in sequence_issues(p)])

    def test_review_input_separates_intent_from_readiness(self):
        case = test_semantic_review.SemanticReviewTests(); case.setUp()
        try:
            p, _ = case.run_plan()
            payload = review_input(p)
            for step in payload["proposed_steps"]:
                self.assertNotIn("uncertainties", step)
                self.assertNotIn("success_check", step)
                self.assertNotIn("params", step)
                self.assertIn("instruction_evidence_ids", step)
            legacy = review_input(p, version="1.0.0")
            self.assertIn("uncertainties", legacy["proposed_steps"][0])
            self.assertEqual(list(review_model_schema(p)["properties"]["goal"]["properties"])[-1], "verdict")
        finally:
            case.tearDown()

    def test_partial_review_failure_is_saved_without_positive_verdict(self):
        case = test_semantic_review.SemanticReviewTests(); case.setUp()
        try:
            p, _ = case.run_plan("step_timeout")
            self.assertEqual(p["semantic_review"]["status"], "failed")
            self.assertIsNone(p["semantic_review"]["result"])
            self.assertEqual(set(p["semantic_review"]["item_run_ids"]), {"goal"})
            self.assertEqual(test_semantic_review.protocol.validate(p, case.out), [])
        finally:
            case.tearDown()

    def test_each_item_needs_a_distinct_saved_model_call(self):
        case = test_semantic_review.SemanticReviewTests(); case.setUp()
        try:
            p, _ = case.run_plan()
            runs = p["semantic_review"]["item_run_ids"]
            runs["step_001"] = runs["goal"]
            self.assertTrue(any("trace mapping" in e for e in test_semantic_review.protocol.validate(p)))
        finally:
            case.tearDown()

    def test_new_step_preserves_original_instruction_selection(self):
        case = test_semantic_review.SemanticReviewTests(); case.setUp()
        try:
            p, _ = case.run_plan()
            import json
            draft = json.loads((case.out/"model-draft.json").read_text(encoding="utf-8"))
            for step, raw in zip(p["task_plan"]["steps"], draft["steps"]):
                self.assertEqual(step["instruction_evidence_ids"], raw["evidence_ids"])
        finally:
            case.tearDown()

    def test_compact_review_keeps_modified_assertions(self):
        case = test_semantic_review.SemanticReviewTests(); case.setUp()
        try:
            p, _ = case.run_plan()
            p["task_plan"]["goal"] = "领取常驻声望奖励"
            step = p["task_plan"]["steps"][0]
            step.update(title="接近虚构怪物", intent="该对象已经唯一识别", uncertainties=["不应进入复核的规划器意见"])
            step["params"]["target_label"] = "虚构的具体名字"
            items = item_inputs(p)
            self.assertEqual(items["goal"]["claim"], "领取常驻声望奖励")
            self.assertIn("接近虚构怪物", items[step["id"]]["claim"])
            self.assertIn("该对象已经唯一识别", items[step["id"]]["claim"])
            self.assertIn("虚构的具体名字", items[step["id"]]["claim"])
            self.assertNotIn("不应进入复核的规划器意见", str(items))
        finally:
            case.tearDown()

    def test_item_timeout_is_recorded_with_the_request(self):
        case = test_semantic_review.SemanticReviewTests(); case.setUp()
        try:
            p, _ = case.run_plan()
            import json
            trace = next(t for t in p["analysis_runs"] if t["id"] == p["semantic_review"]["analysis_run_id"])
            request = json.loads((case.out/trace["request_path"]).read_text(encoding="utf-8"))
            self.assertEqual(request["timeout_s"], 180)
        finally:
            case.tearDown()

    def test_cpu_setting_is_local_and_reaches_the_backend(self):
        from ggai.vlm import OllamaVLM
        cpu = OllamaVLM(gpu_layers=0)
        default = OllamaVLM()
        for client in (cpu, default):
            client._post = lambda path, payload, timeout: payload
        self.assertEqual(cpu.structured("test", {})["options"]["num_gpu"], 0)
        self.assertNotIn("num_gpu", default.structured("test", {})["options"])

    def test_review_fragment_must_be_a_real_suspect_substring(self):
        case = test_semantic_review.SemanticReviewTests(); case.setUp()
        try:
            p, _ = case.run_plan()
            payload = item_inputs(p, version="1.4.0")["goal"]
            for decision, fragment in [("unsupported_claim", "不存在于待审句子里的片段"), ("unsupported_claim", None), ("supported", payload["claim"][0:2])]:
                with self.subTest(decision=decision, fragment=fragment):
                    raw = {"decision": decision, "fragment": fragment, "citations": [{"unit_id": "asr_001:original"}]}
                    with self.assertRaises(ValueError):
                        item_judgment(p, payload, raw)
        finally:
            case.tearDown()

    def test_invalid_target_reference_returns_validation_errors(self):
        case = test_semantic_review.SemanticReviewTests(); case.setUp()
        try:
            p, _ = case.run_plan()
            p["task_plan"]["goal_target_ref"] = "target_999"
            errors = test_semantic_review.protocol.validate(p)
            self.assertTrue(errors)
            self.assertTrue(any("stale" in error or "verdict" in error for error in errors))
        finally:
            case.tearDown()

    def test_review_only_retry_preserves_plan_and_skips_planning(self):
        case = test_semantic_review.SemanticReviewTests(); case.setUp()
        try:
            p, _ = case.run_plan("step_timeout")
            model = test_semantic_review.ReviewModel()
            dest = case.out/"retry"
            result = test_semantic_review.reprocess_project(case.out/"project.json", dest, model, "test_digest", review_only=True)
            self.assertEqual(result["task_plan"], p["task_plan"])
            import json
            self.assertEqual(json.loads((dest/"targets.json").read_text(encoding="utf-8")), result["target_registry"])
            self.assertEqual(json.loads((dest/"grounding.json").read_text(encoding="utf-8")), result["grounding"])
            self.assertEqual(json.loads((dest/"model-draft.json").read_text(encoding="utf-8")), json.loads((case.out/"model-draft.json").read_text(encoding="utf-8")))
            self.assertTrue(all("CLAIM_AND_EVIDENCE=" in request for request in model.requests))
            self.assertEqual(result["semantic_review"]["status"], "supported_with_unknowns")
            self.assertEqual(test_semantic_review.protocol.validate(result, dest), [])
        finally:
            case.tearDown()

    def test_instruction_order_also_covers_ocr_tutorial_frames(self):
        p = sequence_fixture()
        p["evidence_index"][1].update(kind="frame", time={"start_s": 0, "end_s": 0})
        self.assertIn("instruction_order", [x["code"] for x in sequence_issues(p)])


    def test_compacted_review_preserves_source_timestamps(self):
        case = test_semantic_review.SemanticReviewTests(); case.setUp()
        try:
            p, _ = case.run_plan()
            from ggai.targets import evidence_units
            units = {u["id"]: u for u in evidence_units(p, include_excluded=True)}
            for payload in item_inputs(p).values():
                for row in payload["evidence"]:
                    self.assertEqual(row["time_s"], units[row["id"]]["time"]["start_s"])
                    for uid, timestamp in zip(row.get("same_text_ids", []), row.get("same_text_times_s", [])):
                        self.assertEqual(timestamp, units[uid]["time"]["start_s"])
                self.assertTrue(all("time_s" in row for row in payload.get("context", [])))
            self.assertNotIn("time_s", item_inputs(p, version="1.3.0")["goal"]["evidence"][0])
        finally:
            case.tearDown()

    def test_step_review_cannot_reject_whole_plan_order(self):
        import jsonschema
        from ggai.semantic_review import item_schema
        payload = {"item_id": "step_001", "claim": "先移动", "evidence": [{"id": "source"}]}
        raw = {"citations": [{"unit_id": "source"}], "decision": "wrong_order", "fragment": "先移动"}
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(raw, item_schema(payload))
        payload["item_id"] = "goal"; raw["missing_instructions"] = []
        jsonschema.validate(raw, item_schema(payload))


    def test_suspect_fragment_is_selected_from_verbatim_claims(self):
        import jsonschema
        from ggai.semantic_review import item_schema
        payload = {"item_id": "step_001", "claim": "朝东南方向,地图下角。具体位置未知", "evidence": [{"id": "source"}]}
        raw = {"citations": [{"unit_id": "source"}], "decision": "unsupported_claim", "fragment": "朝东南方向，地图下角"}
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(raw, item_schema(payload))
        raw["fragment"] = "朝东南方向,地图下角"
        jsonschema.validate(raw, item_schema(payload))

if __name__ == "__main__":
    unittest.main()
