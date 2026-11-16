import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai import protocol, store
from ggai.grounding import (anchor_candidates, catalog_points, classify_frame, compare_transcripts,
                             grounded_input, review_plan, region_terms, instruction_hints)
from ggai.understanding import grounded_draft_schema, understand_grounded
from test_task_planning import draft
from ggai.planning import dump, sha256
from test_task_planning import with_plan


def row(text, x, y, score=.99, width=1280, height=720):
    return [[[x*width, y*height], [(x+.06)*width, y*height], [(x+.06)*width, (y+.025)*height], [x*width, (y+.025)*height]], text, score]


CATALOG = {"data": [{"sceneId": 3, "points": [
    {"id": 1, "type": "TeleportWaypoint", "name": "传送锚点", "country": "蒙德", "areas": ["星落湖"]},
    {"id": 2, "type": "TeleportWaypoint", "name": "传送锚点", "country": "蒙德", "areas": ["星落湖"]},
    {"id": 3, "type": "Goddess", "name": "七天神像-风", "country": "蒙德", "areas": ["星落湖"]}]}]}
POINTS = catalog_points(CATALOG)


def grounded_fixture(output):
    p = with_plan(output)
    rows = [row("第12层第3间", .73, .03), row("200/200", .61, .03), row("星落湖", .4, .4),
            row("纳塔部族声望奖励", .04, .08)]
    frame = classify_frame("frame_001", rows, 1280, 720, region_terms(POINTS))
    raw = {"frames": [{"evidence_id": "frame_001", "frame_sha256": p["evidence_index"][0]["sha256"],
                       "width": 1280, "height": 720, "rows": rows}]}
    dump(raw, output / "evidence/ocr_raw.json"); dump(CATALOG, output / "evidence/catalog.json")
    p["schema_version"] = "1.2.0"
    ref = lambda name: {"path": name, "sha256": sha256(output / name)}
    p["grounding"] = {"version": "1.0.0", "ocr_artifact": ref("evidence/ocr_raw.json"),
        "catalog_artifact": ref("evidence/catalog.json"), "retry_artifact": None, "frames": [frame],
        "transcripts": compare_transcripts(p["evidence_index"], [], [frame], region_terms(POINTS)),
        "anchors": [anchor_candidates(frame, POINTS)], "plan_review": {}}
    p["grounding"]["plan_review"] = review_plan(p)
    return p


class GroundingTests(unittest.TestCase):
    def test_map_status_is_not_task_but_same_words_in_quest_tracker_survive(self):
        r = [row("200/200", .61, .03), row("第12层第3间", .73, .03), row("纳塔部族声望奖励", .04, .08), row("星落湖", .4, .4)]
        f = classify_frame("frame_001", r, 1280, 720, {"星落湖"})
        self.assertEqual(f["scene"], "map")
        self.assertFalse(f["rows"][1]["eligible"])
        self.assertFalse(f["rows"][2]["eligible"])
        tracker = classify_frame("frame_001", [row("领取声望奖励", .04, .25), row("前往第12层第3间", .04, .3)], 1280, 720, set())
        self.assertTrue(all(r["role"] == "quest_tracker" and r["eligible"] for r in tracker["rows"]))

    def test_classification_is_resolution_independent(self):
        a = classify_frame("f", [row("烹饪", .64, .49)], 1280, 720, set())
        b = classify_frame("f", [row("烹饪", .64, .49, width=1920, height=1080)], 1920, 1080, set())
        self.assertEqual(a["rows"][0]["role"], "interaction_prompt")
        self.assertEqual(a["rows"][0]["role"], b["rows"][0]["role"])

    def test_low_confidence_and_truncated_location_not_completed(self):
        a = classify_frame("f", [row("回声之", .4, .4), row("传送锚点", .75, .05, score=.4)], 1280, 720, {"回声之子"})
        self.assertFalse(any(r["eligible"] for r in a["rows"]))
        self.assertEqual(anchor_candidates(a, POINTS)["anchor_type"], "unknown")

    def test_hp_and_icon_contaminated_text_are_not_precise_targets(self):
        f = classify_frame("f", [row("3140/44103", .45, .90), row("D传送锚点", .64, .49)], 1280, 720, set())
        self.assertFalse(any(r["eligible"] for r in f["rows"]))

    def test_waypoint_not_confused_with_statue_and_ambiguity_not_promoted(self):
        f = classify_frame("f", [row("传送锚点", .76, .04), row("蒙德 星落湖", .76, .09)], 1280, 720, region_terms(POINTS))
        a = anchor_candidates(f, POINTS)
        self.assertEqual(a["anchor_type"], "TeleportWaypoint")
        self.assertEqual([p["id"] for p in a["candidates"]], [1, 2])
        self.assertEqual(a["identity_status"], "ambiguous_candidates")
        self.assertIsNone(a["verified_point_id"])
        self.assertEqual(a["current_player_unlocked"], "unknown")
        f = classify_frame("f", [row("七天神像", .76, .04), row("蒙德 星落湖", .76, .09)], 1280, 720, region_terms(POINTS))
        a = anchor_candidates(f, POINTS)
        self.assertEqual([p["id"] for p in a["candidates"]], [3])
        self.assertEqual(a["identity_status"], "candidate_unique")
        self.assertIsNone(a["verified_coordinates"])

    def test_map_label_alone_is_not_selected_anchor(self):
        f = classify_frame("f", [row("200/200", .61, .03), row("星落湖", .4, .4)], 1280, 720, region_terms(POINTS))
        self.assertEqual(anchor_candidates(f, POINTS)["candidates"], [])

    def test_asr_keeps_original_and_records_ocr_supported_candidate(self):
        evidence = [{"id": "f", "kind": "frame", "time": {"start_s": 3, "end_s": 3}},
                    {"id": "a", "kind": "asr", "text": "来到祖仪庙与右上方这个传统猫点", "time": {"start_s": 2, "end_s": 5}}]
        original = copy.deepcopy(evidence)
        f = classify_frame("f", [row("200/200", .61, .03), row("祖遗庙宇", .4, .4)], 1280, 720, {"祖遗庙宇"})
        rows = compare_transcripts(evidence, [{"start": 2, "end": 5, "text": "来到祖仪庙与右上方传送锚点"}], [f], {"祖遗庙宇", "传送锚点"})
        self.assertEqual(evidence, original)
        self.assertEqual(rows[0]["status"], "alternative_unverified")
        self.assertEqual(rows[0]["lexical_candidates"][0]["candidate"], "祖遗庙宇")
        self.assertIn("传送锚点", rows[0]["proposed_terms"])
        self.assertEqual(rows[0]["corroborated_terms"], [])

    def test_old_frame_cannot_support_new_transcription(self):
        evidence = [{"id": "f", "kind": "frame", "time": {"start_s": 100, "end_s": 100}},
                    {"id": "a", "kind": "asr", "text": "传统猫点", "time": {"start_s": 2, "end_s": 5}}]
        f = classify_frame("f", [row("传送锚点", .64, .49)], 1280, 720, set())
        result = compare_transcripts(evidence, [{"start": 2, "end": 5, "text": "传送锚点"}], [f], {"传送锚点"})[0]
        self.assertEqual(result["corroborated_terms"], [])
        self.assertEqual(result["lexical_candidates"], [])

    def test_new_protocol_lossless_roundtrip_and_old_protocol_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p = grounded_fixture(out)
            self.assertEqual(protocol.validate(p, out), [])
            store.import_project(p, out / "store.sqlite")
            self.assertEqual(store.export_project(out / "store.sqlite"), p)
            self.assertNotIn("grounding", protocol.load_schema("1.1.0")["properties"])

    def test_excluded_ui_not_sent_to_model_and_bad_goal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = grounded_fixture(Path(tmp))
            data = json.dumps(grounded_input(p), ensure_ascii=False)
            self.assertNotIn("第12层第3间", data)
            self.assertNotIn("声望奖励", data)
            p["task_plan"]["goal"] = "到地图第12层第3间开宝箱"
            self.assertEqual(review_plan(p)["status"], "rejected")
            self.assertTrue(any("semantic review" in e for e in protocol.validate(p)))

    def test_exact_interaction_text_needs_matching_step_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = grounded_fixture(Path(tmp)); step = p["task_plan"]["steps"][1]
            step["params"]["target_text"] = "烹饪"
            self.assertIn("unsupported_exact_text", [r["code"] for r in review_plan(p)["issues"]])

    def test_tampered_ocr_role_or_anchor_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p = grounded_fixture(out)
            p["grounding"]["frames"][0]["rows"][0]["eligible"] = True
            self.assertTrue(any("classification differs" in e for e in protocol.validate(p, out)))
            p["grounding"]["frames"][0]["rows"][0]["eligible"] = False
            p["grounding"]["anchors"][0]["verified_point_id"] = 1
            self.assertTrue(protocol.validate(p, out))

    def test_tampered_or_missing_grounding_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p = grounded_fixture(out)
            (out / "evidence/ocr_raw.json").write_text("{}", encoding="utf-8")
            self.assertTrue(any("sha256 mismatch" in e for e in protocol.validate(p, out)))
            p["grounding"]["ocr_artifact"]["path"] = "../outside.json"
            self.assertTrue(any("escapes" in e for e in protocol.validate(p, out)))

    def test_original_asr_cannot_be_replaced_by_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p = grounded_fixture(out)
            p["grounding"]["transcripts"][0]["original"] = "偷偷改了原文"
            self.assertTrue(any("original" in e for e in protocol.validate(p, out)))

    def test_explicit_action_coverage_but_not_negated_or_hypothetical_actions(self):
        p = {"evidence_index": [{"id": "a", "kind": "asr", "text": "这是把怪清一下"},
                               {"id": "b", "kind": "asr", "text": "不要把怪清一下"},
                               {"id": "c", "kind": "asr", "text": "如果要打开宝箱"},
                               {"id": "d", "kind": "asr", "text": "朝这个方向走"}]}
        self.assertEqual([(r["evidence_id"], r["action_id"]) for r in instruction_hints(p)], [("a", "fight"), ("d", "move_to")])

    def test_exact_text_schema_cannot_choose_narration(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = grounded_fixture(Path(tmp))
            fields = grounded_draft_schema(p)["properties"]["steps"]["items"]["properties"]
            self.assertEqual(fields["target_text"], {"enum": [None]})
            self.assertEqual(fields["option_text"], {"const": None})

    def test_bounded_repair_preserves_first_draft_and_failure(self):
        class Model:
            model = "test_fake_no_real_inference"
            calls = 0
            def structured(self, *args, **kwargs):
                self.calls += 1
                result = draft()
                result["goal"] = "前往第12层第3间" if self.calls == 1 else "前往宝箱"
                return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(result, ensure_ascii=False)}}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p = grounded_fixture(out); model = Model()
            result = understand_grounded(p, out, model, "fake_digest")
            self.assertEqual(model.calls, 2)
            self.assertEqual(result["grounding"]["plan_review"]["status"], "pending_human_review")
            self.assertEqual(json.loads((out / "plan-review-task_002.json").read_text(encoding="utf-8"))["status"], "rejected")
            self.assertTrue((out / "model-draft-task_002.json").is_file())
            self.assertTrue((out / "model-draft-task_003.json").is_file())
            self.assertEqual(protocol.validate(result, out), [])

    def test_bad_second_draft_stays_rejected_without_infinite_retry(self):
        class Model:
            model = "test_fake_no_real_inference"
            calls = 0
            def structured(self, *args, **kwargs):
                self.calls += 1; result = draft(); result["goal"] = "前往第12层第3间"
                return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(result, ensure_ascii=False)}}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p = grounded_fixture(out); model = Model()
            result = understand_grounded(p, out, model, "fake_digest")
            self.assertEqual(model.calls, 2)
            self.assertEqual(result["grounding"]["plan_review"]["status"], "rejected")
            self.assertFalse(result["task_plan"]["execution_allowed"])

    def test_missing_asr_and_cross_frame_references_rejected_without_filesystem(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = grounded_fixture(Path(tmp))
            p["grounding"]["transcripts"] = []
            self.assertTrue(any("transcript ids" in e for e in protocol.validate(p)))
            p["grounding"]["anchors"][0]["text_ids"] = ["does_not_exist"]
            self.assertTrue(any("another frame" in e for e in protocol.validate(p)))

    def test_semantic_review_detects_omitted_explicit_fight(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = grounded_fixture(Path(tmp))
            p["evidence_index"][1]["text"] = "把怪清一下"
            issues = review_plan(p)["issues"]
            self.assertTrue(any(i["code"] == "uncovered_instruction" and "fight" in i["detail"] for i in issues))

    def test_map_background_location_cannot_be_promoted_to_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = grounded_fixture(Path(tmp)); p["task_plan"]["goal"] = "前往星落湖开箱"
            self.assertIn("unconfirmed_region_as_goal", [i["code"] for i in review_plan(p)["issues"]])
            self.assertNotIn("星落湖", json.dumps(grounded_input(p), ensure_ascii=False))

    def test_waypoint_mention_does_not_authorize_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = grounded_fixture(Path(tmp)); step = p["task_plan"]["steps"][1]
            step["params"]["target_label"] = "传送锚点"
            self.assertIn("unsupported_anchor_activation", [i["code"] for i in review_plan(p)["issues"]])

    def test_clicking_teleport_instruction_is_not_lost_to_asr_typo(self):
        p = {"evidence_index": [{"id": "a", "kind": "asr", "text": "你点击这个传送某点"}]}
        self.assertEqual(instruction_hints(p)[0]["action_id"], "teleport")

    def test_original_ocr_from_real_guide_frames(self):
        data = json.loads((ROOT / "tests/fixtures/grounding_real_ocr.json").read_text(encoding="utf-8"))
        for case in data["frames"]:
            raw = case["raw"]
            frame = classify_frame(raw["evidence_id"], raw["rows"], raw["width"], raw["height"], set(case["regions"]))
            roles = {}
            for r in frame["rows"]:
                roles.setdefault(r["text"], []).append(r["role"])
            for text, role in case["expected_roles"].items():
                with self.subTest(case=case["case"], text=text):
                    self.assertIn(role, roles[text])

    def test_long_retry_segment_cannot_leak_later_words_into_earlier_evidence(self):
        evidence = [{"id": "a", "kind": "asr", "text": "本期是隐藏锚点", "time": {"start_s": 0, "end_s": 2}}]
        retry = [{"start": 0, "end": 9, "text": "本期是隐藏锚点，先来到祖遗庙宇右上方"}]
        row = compare_transcripts(evidence, retry, [], {"祖遗庙宇", "传送锚点"})[0]
        self.assertEqual(row["status"], "context_only")
        self.assertEqual(row["proposed_terms"], [])
        p = {"evidence_index": evidence, "grounding": {"frames": [], "anchors": [], "transcripts": [row]}}
        self.assertNotIn("祖遗庙宇", json.dumps(grounded_input(p), ensure_ascii=False))
        retry[0]["words"] = [{"start": 0, "end": 1.8, "word": "本期是隐藏锚点"}, {"start": 2.2, "end": 5, "word": "先来到祖遗庙宇右上方"}]
        row = compare_transcripts(evidence, retry, [], {"祖遗庙宇"})[0]
        self.assertEqual(row["alternative"], "本期是隐藏锚点")
        self.assertEqual(row["status"], "agrees")

    def test_visible_unrelated_cooking_prompt_is_not_a_model_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = grounded_fixture(Path(tmp))
            p["grounding"]["frames"][0]["rows"].append({"text": "烹饪", "role": "interaction_prompt"})
            field = grounded_draft_schema(p)["properties"]["steps"]["items"]["properties"]["target_text"]
            self.assertEqual(field, {"enum": [None]})
            p["evidence_index"][1]["text"] = "到锅边烹饪"
            field = grounded_draft_schema(p)["properties"]["steps"]["items"]["properties"]["target_text"]
            self.assertIn("烹饪", field["enum"])

    def test_unclear_terrain_word_cannot_become_an_enemy(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = grounded_fixture(Path(tmp)); p["task_plan"]["goal"] = "前往猎系怪物区域"
            self.assertIn("unsupported_combat_target", [i["code"] for i in review_plan(p)["issues"]])


if __name__ == "__main__":
    unittest.main()
