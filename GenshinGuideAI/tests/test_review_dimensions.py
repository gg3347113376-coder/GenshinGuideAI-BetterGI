import copy
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai.semantic_review import item_inputs, item_schema, item_judgment, review_issues
from ggai.targets import object_claim_issues
import test_semantic_review


class ReviewDimensionTests(unittest.TestCase):
    def setUp(self):
        self.case = test_semantic_review.SemanticReviewTests(); self.case.setUp()
        self.p, _ = self.case.run_plan()
    def tearDown(self):
        self.case.tearDown()
    def test_goal_is_independent_of_step_coverage(self):
        payloads = item_inputs(self.p)
        self.assertNotIn("proposed_order", payloads["goal"])
        self.assertEqual(len(payloads["coverage"]["proposed_order"]), len(self.p["task_plan"]["steps"]))
        self.assertNotIn("claim", payloads["coverage"])
        self.assertIn("proposed_order", item_inputs(self.p, version="1.4.0")["goal"])
    def test_unused_persistent_ui_is_not_in_positive_claim_review(self):
        items = item_inputs(self.p)
        self.assertFalse(any(u["text"] == "纳塔部族声望奖励" for u in items["goal"]["evidence"]))
        self.p["task_plan"]["goal"] = "领取纳塔部族声望奖励"
        self.assertTrue(any(u["text"] == "纳塔部族声望奖励" for u in item_inputs(self.p)["goal"]["evidence"]))
    def test_added_category_is_reviewed_but_quoted_source_is_not_assertion(self):
        step = self.p["task_plan"]["steps"][0]
        step.update(title="接近虚构怪物", intent="这个对象就是敌人")
        self.assertIn("object_assertions", item_inputs(self.p)[step["id"]])
        step.update(title="前往原文“怪物底下”所指位置", intent="待辨认")
        self.assertNotIn("object_assertions", item_inputs(self.p)[step["id"]])
    def test_supported_action_does_not_override_unsupported_object(self):
        payload = item_inputs(self.p)["step_001"]
        for a, b, expected in [("unsupported", "supported", "unsupported"), ("supported", "uncertain", "uncertain"), ("supported", "supported", "supported")]:
            raw = {"object_details": {"decision": a, "citations": [{"unit_id": "asr_001:original"}]},
                   "intent": {"decision": b, "citations": [{"unit_id": "asr_001:original"}]}}
            import jsonschema
            jsonschema.validate(raw, item_schema(payload))
            judgment = item_judgment(self.p, payload, raw)
            self.assertEqual(judgment["verdict"], expected)
            self.assertEqual(len(judgment["citations"]), 1)
            self.assertEqual(judgment["citations"][0]["quote"], self.p["grounding"]["transcripts"][0]["original"])
    def test_positive_verdict_cannot_cite_excluded_ui_even_when_same_text_exists(self):
        import jsonschema
        self.p["task_plan"]["goal"] = "领取纳塔部族声望奖励"
        payload = item_inputs(self.p)["goal"]
        ui = next(u for u in payload["evidence"] if u["text"] == "纳塔部族声望奖励")
        self.assertFalse(ui["positive_support"])
        part = {"decision": "supported", "citations": [{"unit_id": ui["id"]}]}
        raw = {"object_details": copy.deepcopy(part), "intent": copy.deepcopy(part)}
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(raw, item_schema(payload))
        for part in raw.values(): part["decision"] = "unsupported"
        jsonschema.validate(raw, item_schema(payload))

    def test_coverage_trace_is_required_and_tampering_is_detected(self):
        record = self.p["semantic_review"]
        self.assertIn("coverage", record["item_run_ids"])
        record["item_run_ids"].pop("coverage")
        from ggai import protocol
        self.assertTrue(any("every item" in e for e in protocol.validate(self.p, self.case.out)))
    def test_false_support_cannot_bypass_local_object_proof(self):
        step = self.p["task_plan"]["steps"][0]
        step.update(title="接近猎系怪物", intent="到达怪物的位置")
        self.assertIn("unproven_object_category", [i["code"] for i in review_issues(self.p, self.p["semantic_review"]["result"])])
        self.assertNotIn("unproven_object_category", [i["code"] for i in review_issues(self.p, self.p["semantic_review"]["result"], version="1.4.0")])
    def test_unrelated_enemy_in_other_sentence_does_not_prove_local_category(self):
        step = self.p["task_plan"]["steps"][0]
        step.update(title="接近猎系怪物", intent="到达怪物的位置", instruction_evidence_ids=["asr_001"])
        old = copy.deepcopy(self.p["grounding"]["transcripts"][0])
        old.update(evidence_id="other_asr", original="先把怪清一下", alternative=None)
        self.p["grounding"]["transcripts"].append(old)
        ev = copy.deepcopy(self.p["evidence_index"][1]); ev["id"] = "other_asr"
        self.p["evidence_index"].append(ev)
        self.assertTrue(object_claim_issues(self.p))
        # The same explicit source is valid for a step that actually cites that instruction.
        step["instruction_evidence_ids"] = ["other_asr"]
        self.assertFalse(any(i["step_id"] == step["id"] for i in object_claim_issues(self.p)))
    def test_unclear_location_is_retained_without_enemy_claim(self):
        step = self.p["task_plan"]["steps"][0]
        step.update(title="前往原文“我们要到这条猎系底下”所指位置", intent="保留原词，位置待辨认")
        self.assertEqual(object_claim_issues(self.p), [])


if __name__ == "__main__":
    unittest.main()
