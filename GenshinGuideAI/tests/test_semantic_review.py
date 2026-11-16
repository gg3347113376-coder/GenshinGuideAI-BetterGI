import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai import protocol, store
from ggai.planning import make_plan
from ggai.semantic_review import (bound_draft_schema, plan_with_review, review_input, review_issues,
                                 review_status, reprocess_project)
from ggai.targets import build_registry, binding_issues, action_label
from test_grounding import grounded_fixture
from test_task_planning import draft


class ReviewModel:
    model = "test_model_not_real_inference"
    think = False
    def __init__(self, mode="valid"):
        self.mode = mode
        self.requests = []
    def structured(self, prompt, schema, **kwargs):
        self.requests.append(prompt)
        if "CLAIM_AND_EVIDENCE=" in prompt:
            if self.mode == "timeout":
                raise TimeoutError("test review timeout")
            data = json.loads(prompt.split("CLAIM_AND_EVIDENCE=", 1)[1])
            if self.mode == "step_timeout" and data["item_id"] != "goal":
                raise TimeoutError("test later item timeout")
            result = {"citations": [{"unit_id": "asr_001:original"}], "decision": "supported", "fragment": None}
            if data["item_id"] == "goal":
                result["missing_instructions"] = []
            if self.mode == "forged":
                result["citations"][0]["unit_id"] = "not_in_evidence"
            if data.get("review_version") in ("1.5.0", "1.6.0", "1.7.0"):
                component = {"decision": "supported", "citations": result["citations"]}
                result = {"missing_instructions": []} if data["item_id"] == "coverage" else {
                    "object_details": copy.deepcopy(component), "intent": copy.deepcopy(component)}
        elif "EVIDENCE_AND_PROPOSAL=" in prompt:
            if self.mode == "timeout":
                raise TimeoutError("test review timeout")
            data = json.loads(prompt.split("EVIDENCE_AND_PROPOSAL=", 1)[1].split("\nOUTPUT_SHAPE=", 1)[0])
            judgment = {"verdict": "supported", "reason": "原文要求去树下开箱；身份和坐标仍未知",
                        "citations": [{"unit_id": "asr_001:original"}]}
            result = {"goal": copy.deepcopy(judgment), "steps": [{"step_id": s["id"], **copy.deepcopy(judgment)} for s in data["proposed_steps"]],
                      "missing_instructions": []}
            if self.mode == "forged":
                result["steps"][0]["citations"][0]["unit_id"] = "not_in_evidence"
            result["steps"] = {x["step_id"]: {k: v for k, v in x.items() if k != "step_id"} for x in result["steps"]}
        else:
            data = json.loads(prompt.split("GUIDE_DATA=", 1)[1].split("\nOUTPUT_SHAPE=", 1)[0])
            target = next(t for t in data["targets"] if t["kind"] == "chest")
            result = draft()
            del result["goal"]
            result["goal_target_id"] = target["id"]
            for s in result["steps"]:
                for key in ("target_label", "title", "intent", "expected_result"):
                    s.pop(key)
                s["target_id"] = target["id"]
        return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(result, ensure_ascii=False)}}


class SemanticReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.p = grounded_fixture(self.out)
    def tearDown(self):
        self.tmp.cleanup()
    def run_plan(self, mode="valid"):
        model = ReviewModel(mode)
        return plan_with_review(self.p, self.out, model, "unit_test_digest"), model
    def test_bound_targets_independent_trace_and_lossless_storage(self):
        p, model = self.run_plan()
        self.assertEqual(protocol.validate(p, self.out), [])
        self.assertEqual(p["semantic_review"]["status"], "supported_with_unknowns")
        self.assertFalse(p["semantic_review"]["execution_allowed"])
        self.assertEqual(p["task_plan"]["goal_target_ref"], "target_001")
        self.assertTrue(all(s["params"]["target_label"] == p["target_registry"]["entities"][0]["label"] for s in p["task_plan"]["steps"]))
        self.assertEqual(store.export_project(self.out / "project.sqlite"), p)
        review_request = model.requests[-1]
        self.assertNotIn("explicit_instruction_hints", review_request)
        self.assertNotIn("plan_review", review_request)
        payload = json.loads(review_request.split("CLAIM_AND_EVIDENCE=", 1)[1])
        self.assertNotIn("uncertainties", payload)
        self.assertEqual(len(model.requests), len(p["task_plan"]["steps"]) + 3)
    def test_compiler_retains_registered_anchor_unknowns_when_model_omits_notes(self):
        self.p["target_registry"] = build_registry(self.p)
        target = self.p["target_registry"]["entities"][0]
        target.update(kind="waypoint", role="narrated_start", label="起点传送锚点（身份待核验）")
        d = draft(); d["goal_target_id"] = target["id"]; d["steps"] = d["steps"][:1]
        d["steps"][0].update(action_id="teleport", target_id=target["id"], uncertainties=[])
        before = copy.deepcopy(d); self.p["events"] = []
        make_plan(self.p, d, ["task_001"])
        notes = self.p["task_plan"]["steps"][0]["uncertainties"]
        self.assertEqual(len(notes), 3)
        self.assertTrue(any("身份" in note for note in notes))
        self.assertTrue(any("坐标" in note for note in notes))
        self.assertTrue(any("解锁" in note for note in notes))
        self.assertEqual(d, before)
        self.assertIsNone(target["verified_identity"])
        self.assertFalse(self.p["task_plan"]["execution_allowed"])

    def test_unknown_target_rejected_before_events_change(self):
        self.p["target_registry"] = build_registry(self.p)
        before = copy.deepcopy(self.p["events"])
        d = draft()
        d["goal_target_id"] = "target_001"
        for s in d["steps"]: s["target_id"] = "target_999"
        with self.assertRaisesRegex(ValueError, "目标 ID"):
            make_plan(self.p, d, ["task_001"])
        self.assertEqual(self.p["events"], before)
    def test_interaction_label_distinguishes_waypoint_and_chest(self):
        self.assertEqual(action_label("interact", {"kind": "chest"}), "开启宝箱")
        self.assertEqual(action_label("interact", {"kind": "waypoint", "role": "world_interaction"}), "解锁传送锚点")
    def test_target_label_cannot_be_model_free_text(self):
        self.p["target_registry"] = build_registry(self.p)
        fields = bound_draft_schema(self.p)["properties"]["steps"]["items"]["oneOf"]
        for choice in fields:
            self.assertFalse({"target_label", "title", "intent", "expected_result"} & choice["properties"].keys())
            self.assertIn("target_id", choice["required"])
    def test_action_cannot_use_region_as_waypoint(self):
        p, _ = self.run_plan()
        target = p["target_registry"]["entities"][0]
        target["kind"] = "region"
        p["task_plan"]["steps"][0]["action_id"] = "teleport"
        self.assertIn("target_type_mismatch", [i["code"] for i in binding_issues(p)])
    def test_unknown_review_source_cannot_be_parsed_as_supported(self):
        p, model = self.run_plan("forged")
        self.assertEqual(p["semantic_review"]["status"], "failed")
        self.assertEqual(len(model.requests), 2)
        self.assertEqual(protocol.validate(p, self.out), [])
    def test_forged_quote_is_rejected_despite_supported_verdict(self):
        p, _ = self.run_plan()
        result = p["semantic_review"]["result"]
        result["steps"][0]["citations"][0]["quote"] = "原文没有这句话"
        self.assertIn("invalid_review_citation", [i["code"] for i in review_issues(p, result)])
    def test_schema_forbids_action_and_target_type_mismatch(self):
        import jsonschema
        self.p["target_registry"] = build_registry(self.p)
        d = draft()
        d["goal_target_id"] = "target_001"
        for s in d["steps"]:
            for key in ("target_label", "title", "intent", "expected_result"):
                del s[key]
            s["target_id"] = "target_001"
        del d["goal"]
        d["steps"][0]["action_id"] = "fight"
        self.assertTrue(list(jsonschema.Draft202012Validator(bound_draft_schema(self.p)).iter_errors(d)))
    def test_schema_forbids_teleport_to_an_unlocated_exploration_goal(self):
        import jsonschema
        self.p["grounding"]["transcripts"][0]["original"] = "本段是一个隐藏锚点"
        self.p["target_registry"] = build_registry(self.p)
        target = next(t for t in self.p["target_registry"]["entities"] if t["role"] == "narrated_goal")
        d = draft()
        del d["goal"]
        d["goal_target_id"] = target["id"]
        for s in d["steps"]:
            for key in ("target_label", "title", "intent", "expected_result"):
                del s[key]
            s.update(action_id="teleport", target_id=target["id"])
        self.assertTrue(list(jsonschema.Draft202012Validator(bound_draft_schema(self.p)).iter_errors(d)))
    def test_free_text_cannot_reintroduce_a_named_target(self):
        self.p["target_registry"] = build_registry(self.p)
        d = draft()
        d["goal_target_id"] = "target_001"
        d["goal"] = "领取虚构声望奖励"
        for s in d["steps"]:
            s["target_id"] = "target_001"
            for key in ("title", "intent", "expected_result"):
                s[key] = "前往虚构的传统锚点"
        self.p["events"] = []
        make_plan(self.p, d, ["task_001"])
        self.assertNotIn("传统锚点", json.dumps(self.p["task_plan"], ensure_ascii=False))
        self.assertNotIn("声望", self.p["task_plan"]["goal"])
        self.assertIn("传统锚点", json.dumps(d, ensure_ascii=False))
    def test_timeout_is_saved_as_failed_and_no_retry_loop(self):
        p, model = self.run_plan("timeout")
        self.assertEqual(p["semantic_review"]["status"], "failed")
        self.assertIn("timeout", p["semantic_review"]["failure"])
        self.assertEqual(len(model.requests), 2)
        self.assertEqual(protocol.validate(p, self.out), [])
        self.assertTrue((self.out / "failure.json").exists())
    def test_missing_or_duplicate_review_step_rejected(self):
        p, _ = self.run_plan()
        result = p["semantic_review"]["result"]
        result["steps"][1] = copy.deepcopy(result["steps"][0])
        self.assertIn("incomplete_review", [i["code"] for i in review_issues(p, result)])
    def test_visible_ui_cannot_be_positive_action_evidence(self):
        p, _ = self.run_plan()
        result = p["semantic_review"]["result"]
        result["steps"][0]["citations"] = [{"unit_id": "frame_001_text_001", "quote": "第12层第3间"}]
        self.assertIn("unsupported_evidence_role", [i["code"] for i in review_issues(p, result)])
    def test_plan_edit_invalidates_old_review(self):
        p, _ = self.run_plan()
        p["task_plan"]["goal"] = "领取声望奖励"
        self.assertTrue(any("stale" in e for e in protocol.validate(p)))
    def test_registry_edit_cannot_forge_identity(self):
        p, _ = self.run_plan()
        p["target_registry"]["entities"][0]["label"] = "已核实的具体锚点"
        self.assertTrue(any("registry differs" in e for e in protocol.validate(p)))
    def test_reviewer_output_cannot_be_replaced_even_with_new_status(self):
        p, _ = self.run_plan()
        p["semantic_review"]["result"]["goal"]["reason"] = "伪造复核说明"
        self.assertTrue(any("trace does not match" in e for e in protocol.validate(p, self.out)))
    def test_bad_source_id_rejected(self):
        p, _ = self.run_plan()
        result = p["semantic_review"]["result"]
        result["steps"][0]["citations"][0]["unit_id"] = "not_in_evidence"
        self.assertIn("invalid_review_citation", [i["code"] for i in review_issues(p, result)])
    def test_support_outside_the_step_citations_is_not_accepted(self):
        p, _ = self.run_plan()
        p["task_plan"]["steps"][0]["evidence_ids"] = ["frame_001"]
        codes = [i["code"] for i in review_issues(p, p["semantic_review"]["result"])]
        self.assertIn("uncited_support", codes)
        self.assertIn("target_without_step_evidence", codes)
    def test_source_identity_change_invalidates_review(self):
        p, _ = self.run_plan()
        p["sources"][0]["path"] = "different_video.mp4"
        self.assertTrue(any("stale" in e for e in protocol.validate(p)))
    def test_standalone_task_schema_accepts_new_bound_plan(self):
        import jsonschema
        p, _ = self.run_plan()
        schema = json.loads((ROOT / "schema/task_plan_v1_3.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(p["task_plan"])
        del p["task_plan"]["steps"][0]["target_ref"]
        self.assertTrue(list(jsonschema.Draft202012Validator(schema).iter_errors(p["task_plan"])))
    def test_explaining_a_waypoint_does_not_create_a_teleport_start(self):
        self.p["grounding"]["transcripts"][0]["original"] = "然后激活第一个传送锚点，你点击这个传送锚点"
        registry = build_registry(self.p)
        self.assertFalse(any(t["role"] == "narrated_start" for t in registry["entities"]))
    def test_return_instruction_can_use_unverified_anchor_candidate(self):
        t = self.p["grounding"]["transcripts"][0]
        t.update(original="我们回到这个传统猫点", alternative="我们回到这个传送锚点", status="alternative_unverified")
        target = next(t for t in build_registry(self.p)["entities"] if t["role"] == "narrated_start")
        self.assertEqual(target["unit_ids"], ["asr_001:original", "asr_001:retry"])
        self.assertIsNone(target["verified_identity"])
    def test_ambiguous_transcription_does_not_create_enemy(self):
        self.p["evidence_index"][1]["text"] = "我们要到这条猎系底下"
        self.p["grounding"]["transcripts"][0]["original"] = "我们要到这条猎系底下"
        registry = build_registry(self.p)
        self.assertFalse(any(t["kind"] == "enemy" for t in registry["entities"]))
        self.assertTrue(any(t["kind"] == "location" and "猎系" in t["label"] for t in registry["entities"]))
    def test_reprocess_preserves_original_and_source_artifacts(self):
        p, _ = self.run_plan()
        dest = self.out / "reprocessed"
        result = reprocess_project(self.out / "project.json", dest, ReviewModel(), "test_digest")
        self.assertEqual(protocol.validate(result, dest), [])
        self.assertEqual(json.loads((dest / "previous-project.json").read_text(encoding="utf-8")), p)
        self.assertEqual(result["evidence_index"], p["evidence_index"])
        self.assertEqual(result["simulation_runs"], [])
        self.assertEqual(result["execution_runs"], [])

if __name__ == "__main__":
    unittest.main()
