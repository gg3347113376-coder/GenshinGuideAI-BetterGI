import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("live_smoke", Path(__file__).resolve().parents[1] / "tools/run_live_smoke.py")
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class LiveSmokeTests(unittest.TestCase):
    def test_no_game_never_launches_bettergi(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(live, "game_state", return_value={"handle": 0, "foreground": False, "minimized": False}), patch.object(live.subprocess, "Popen") as launch:
                result = live.run(Path(folder) / "not_an_install", Path(folder) / "result")
            launch.assert_not_called()
            self.assertEqual(result["reason"], "game_missing")
            self.assertFalse(result["execution_attempted"])
            self.assertEqual(json.loads((Path(folder) / "result/attempt.json").read_text(encoding="utf-8")), result)

    def test_other_foreground_never_launches(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(live, "game_state", return_value={"handle": 100, "foreground": False, "minimized": False}), patch.object(live.subprocess, "Popen") as launch:
                result = live.run(Path(folder), Path(folder) / "result")
            launch.assert_not_called()
            self.assertEqual(result["reason"], "game_not_foreground")

    def test_api_return_alone_is_not_real_success(self):
        self.assertFalse(live.validate_receipt({"status": "passed", "kind": "selected_waypoint_teleport_walk"}))

    def test_missing_stop_or_held_key_cannot_pass(self):
        result = {"kind": "selected_waypoint_teleport_walk", "status": "passed", "execution_attempted": True,
                  "teleport_confirmed": True, "walk_confirmed": True, "stop_confirmed": True,
                  "held_input_count": 0, "forward_key_down": False, "finished_utc": "2026-11-09T00:00:00Z"}
        self.assertTrue(live.validate_receipt(result))
        self.assertFalse(live.validate_receipt({**result, "stop_confirmed": False}))
        self.assertFalse(live.validate_receipt({**result, "held_input_count": 1}))
        self.assertFalse(live.validate_receipt({**result, "forward_key_down": True}))

    def test_stale_output_is_not_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileExistsError):
                live.run(Path(folder), Path(folder))

    def test_prepare_is_idempotent_and_preserves_modified_script(self):
        with tempfile.TemporaryDirectory() as folder:
            bgi = Path(folder)
            (bgi / "BetterGI.dll").write_bytes(b"test_binary")
            live.write_json(bgi / "guideai-live-capability.json", {"bettergi_dll_sha256": live.hashlib.sha256(b"test_binary").hexdigest()})
            live.prepare(bgi)
            live.prepare(bgi)
            script = bgi / "User/JsScript" / live.GROUP / "main.js"
            script.write_text("user edit", encoding="utf-8")
            with self.assertRaises(ValueError):
                live.prepare(bgi)
            self.assertEqual(script.read_text(encoding="utf-8"), "user edit")

    def test_wrong_binary_cannot_install_script(self):
        with tempfile.TemporaryDirectory() as folder:
            bgi = Path(folder)
            (bgi / "BetterGI.dll").write_bytes(b"wrong_binary")
            live.write_json(bgi / "guideai-live-capability.json", {"bettergi_dll_sha256": "not_matching"})
            with self.assertRaises(ValueError):
                live.prepare(bgi)
            self.assertFalse((bgi / "User/JsScript").exists())
