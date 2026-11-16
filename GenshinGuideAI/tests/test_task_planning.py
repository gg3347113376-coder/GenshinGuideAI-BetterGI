import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai import protocol, store
from ggai.planning import catalog, dump, make_plan, sha256
from ggai.understanding import understand, draft_schema, recorded_call, replan_from_review


def draft():
    return {"goal": "前往并开启宝箱", "uncertainties": ["没有坐标"], "steps": [
        {"id": "step_001", "action_id": "move_to", "title": "前往树下", "intent": "接近目标",
         "target_label": "树下宝箱", "target_text": None, "option_text": None, "condition": None,
         "evidence_ids": ["frame_001", "asr_001"], "depends_on": [], "expected_result": "到达宝箱附近",
         "uncertainties": ["路线未验证"], "confidence": .8},
        {"id": "step_002", "action_id": "interact", "title": "开启宝箱", "intent": "取得奖励",
         "target_label": "树下宝箱", "target_text": None, "option_text": None, "condition": None,
         "evidence_ids": ["frame_001", "asr_001"], "depends_on": ["step_001"], "expected_result": "有新奖励证据",
         "uncertainties": ["文字未知"], "confidence": .7}]}


def fixture(output):
    (output / "evidence").mkdir()
    (output / "model").mkdir()
    for rel in ["evidence/frame.png", "evidence/asr.json", "model/request.json", "model/response.json"]:
        (output / rel).write_text("{}", encoding="utf-8")
    dump({"segments": [{"id": "asr_001", "start_s": 1, "end_s": 1, "text": "去树下开箱"}]}, output / "evidence/asr.json")
    project = protocol.new_project("test_clip", "测试，不是实机结果")
    project["schema_version"] = "1.1.0"
    protocol.add_source(project, "test_source", "video.mp4", 20)
    project["segments"] = [{"id": "test_segment", "source_id": "test_source", "start_s": 0, "end_s": 20, "kind": "unknown"}]
    project.update(evidence_index=[], analysis_runs=[], simulation_runs=[], execution_runs=[])
    for eid, kind, rel in [("frame_001", "frame", "evidence/frame.png"), ("asr_001", "asr", "evidence/asr.json")]:
        project["evidence_index"].append({"id": eid, "source_id": "test_source", "kind": kind,
          "time": {"start_s": 1, "end_s": 1}, "path": rel, "sha256": sha256(output / rel),
          "text": "" if kind == "frame" else "去树下开箱", "method": "video_decode" if kind == "frame" else "existing_asr"})
    return project


def with_plan(output):
    project = fixture(output)
    project["analysis_runs"] = [{"id": "task_001", "stage": "task_understanding", "model": "test_only",
        "model_digest": "fake_digest", "request_path": "model/request.json", "response_path": "model/response.json",
        "request_sha256": sha256(output / "model/request.json"), "response_sha256": sha256(output / "model/response.json"),
        "elapsed_s": 0, "status": "parsed", "evidence_ids": ["frame_001", "asr_001"]}]
    make_plan(project, draft(), ["task_001"])
    return project


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name)
        self.project = with_plan(self.output)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_plan_roundtrip_and_unresolved_coordinates(self):
        self.assertEqual(protocol.validate(self.project, self.output), [])
        step = self.project["task_plan"]["steps"][0]
        self.assertIsNone(step["params"]["map_x"])
        self.assertEqual(step["params"]["layer"], "unknown")
        self.assertEqual(step["status"], "blocked")
        self.assertFalse(self.project["task_plan"]["execution_allowed"])
        store.import_project(self.project, self.output / "test.sqlite")
        self.assertEqual(store.export_project(self.output / "test.sqlite"), self.project)

    def test_dangling_evidence_rejected(self):
        self.project["task_plan"]["steps"][0]["evidence_ids"].append("not_exist")
        self.assertTrue(any("unknown evidence" in e for e in protocol.validate(self.project)))

    def test_cyclic_dependency_rejected(self):
        self.project["task_plan"]["steps"][0]["depends_on"] = ["step_002"]
        self.assertTrue(any("dependency" in e for e in protocol.validate(self.project)))

    def test_action_code_and_unregistered_action_rejected(self):
        step = self.project["task_plan"]["steps"][0]
        step["params"]["python_code"] = "keyDown('W')"
        self.assertTrue(protocol.validate(self.project))
        del step["params"]["python_code"]
        step["action_id"] = "arbitrary_keyboard"
        self.assertTrue(protocol.validate(self.project))

    def test_false_execution_or_completion_rejected(self):
        self.project["task_plan"]["execution_allowed"] = True
        self.assertTrue(protocol.validate(self.project))
        self.project["task_plan"]["execution_allowed"] = False
        self.project["task_plan"]["steps"][0]["observed_result"]["status"] = "completed"
        self.assertTrue(protocol.validate(self.project))

    def test_missing_or_changed_files_rejected(self):
        path = self.output / "evidence/frame.png"
        path.write_text("tampered", encoding="utf-8")
        self.assertTrue(any("sha256 mismatch" in e for e in protocol.validate(self.project, self.output)))
        path.unlink()
        self.assertTrue(any("missing artifact" in e for e in protocol.validate(self.project, self.output)))

    def test_transcript_text_must_match_original_file(self):
        self.project["evidence_index"][1]["text"] = "模型悄悄改写了原文"
        self.assertTrue(any("differs from original" in e for e in protocol.validate(self.project, self.output)))

    def test_path_traversal_rejected(self):
        self.project["evidence_index"][0]["path"] = "../outside.png"
        self.assertTrue(any("escapes" in e for e in protocol.validate(self.project, self.output)))

    def test_bad_time_or_source_rejected(self):
        self.project["evidence_index"][0]["time"]["start_s"] = 100
        self.assertTrue(protocol.validate(self.project))

    def test_cannot_clear_blockers_or_checks(self):
        step = self.project["task_plan"]["steps"][0]
        step["blockers"] = []
        step["status"] = "needs_review"
        self.assertTrue(any("blockers/status" in e for e in protocol.validate(self.project)))
        step["preconditions"] = step["preconditions"][:-1]
        self.assertTrue(any("catalog checks" in e for e in protocol.validate(self.project)))

    def test_duplicate_ids_and_missing_trace_rejected(self):
        self.project["task_plan"]["steps"].append(copy.deepcopy(self.project["task_plan"]["steps"][0]))
        self.project["task_plan"]["analysis_run_ids"] = ["absent"]
        errors = protocol.validate(self.project)
        self.assertTrue(any("duplicate" in e for e in errors))
        self.assertTrue(any("trace" in e for e in errors))

    def test_hallucinated_model_reference_rejected_before_build(self):
        candidate = draft()
        candidate["steps"][0]["evidence_ids"] = ["invented"]
        with self.assertRaises(ValueError):
            make_plan(self.project, candidate, ["task_001"])


class FakeVLM:
    model = "test_only"
    def structured(self, prompt, schema, images=(), **kwargs):
        value = {"scene": "travel", "visible_text": [], "observations": ["测试图"], "uncertainties": [], "confidence": .5} if images else draft()
        return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(value)}}


class UnderstandingTests(unittest.TestCase):
    def test_offline_end_to_end_persists_traces_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            project = fixture(output)
            with patch("urllib.request.urlopen", side_effect=AssertionError("test must not use network")):
                result = understand(project, output, FakeVLM(), "test_digest")
            self.assertEqual(protocol.validate(result, output), [])
            self.assertEqual(len(result["analysis_runs"]), 2)
            self.assertTrue((output / "model/task_001.response.json").is_file())
            self.assertTrue((output / "report.html").is_file())
            self.assertEqual(result["execution_runs"], [])

    def test_review_replan_preserves_original_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            original = with_plan(source)
            dump(original, source / "project.json")
            notes = {"author": "test reviewer", "findings": [{"evidence_ids": ["asr_001"], "text": "明确保留未知位置"}]}
            output = Path(tmp) / "reviewed"
            result = replan_from_review(source / "project.json", output, notes, FakeVLM(), "test_digest")
            self.assertEqual(protocol.validate(result, output), [])
            self.assertEqual(protocol.load_project(source / "project.json"), original)
            self.assertEqual(protocol.load_project(output / "previous-project.json"), original)
            self.assertEqual(result["task_plan"]["analysis_run_ids"], ["task_002"])
            self.assertEqual(result["project"]["model_versions"]["review_input"], sha256(output / "review-input.json"))
            self.assertEqual(len(result["analysis_runs"]), 2)
            self.assertFalse(result["task_plan"]["execution_allowed"])

    def test_review_rejects_invented_evidence_before_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            dump(with_plan(source), source / "project.json")
            output = Path(tmp) / "reviewed"
            with self.assertRaisesRegex(ValueError, "证据引用无效"):
                replan_from_review(source / "project.json", output,
                    {"author": "test", "findings": [{"text": "guess", "evidence_ids": ["invented"]}]}, FakeVLM(), "test_digest")
            self.assertFalse(output.exists())

    def test_truncated_response_saved_but_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            project = fixture(output)
            fake = FakeVLM()
            fake.structured = lambda *a, **k: {"done": True, "done_reason": "length", "message": {"content": "{"}}
            with self.assertRaises(ValueError):
                recorded_call(fake, "fake", output, "task_001", "task_understanding", "test", draft_schema(), project["evidence_index"], [])
            self.assertTrue((output / "model/task_001.response.json").is_file())
            self.assertTrue((output / "failure.json").is_file())
            self.assertFalse((output / "project.json").exists())

    def test_report_escapes_model_content(self):
        from ggai.plan_report import write_report
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            project = with_plan(output)
            project["task_plan"]["goal"] = "<script>alert(1)</script>"
            write_report(project, output / "report.html")
            content = (output / "report.html").read_text(encoding="utf-8")
            self.assertNotIn("<script>alert", content)
            self.assertIn("&lt;script&gt;", content)

if __name__ == "__main__":
    unittest.main()
