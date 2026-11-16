"""Run the bounded BetterGI selected-waypoint teleport / short-walk check."""
import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

DEFAULT_BGI = Path(r"D:\OpenAI\原神寻路\outputs\BetterGI-guide-smoke")
GROUP = "GuideAI-LiveSmoke"
SCRIPT = '''(async function () {
    const receipt = await genshin.runTeleportWalkSmoke();
    log.info("GuideAI 实机测试记录：" + receipt);
})();
'''


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare(bgi):
    """Install only the fixed test script; never turn on guide plan execution."""
    capability = json.loads((bgi / "guideai-live-capability.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((bgi / "BetterGI.dll").read_bytes()).hexdigest()
    if capability.get("bettergi_dll_sha256") != digest:
        raise ValueError("BetterGI 构建与实测接口记录不一致")
    script = bgi / "User/JsScript" / GROUP
    script.mkdir(parents=True, exist_ok=True)
    files = {
        script / "main.js": SCRIPT,
        script / "manifest.json": json.dumps({
            "manifest_version": 1, "name": "传送与短距离移动实测", "version": "0.1.0",
            "bgi_version": "0.66.0", "description": "已选锚点传送、短走600毫秒并验证停稳",
            "authors": [{"name": "GenshinGuideAI"}], "main": "main.js"
        }, ensure_ascii=False, indent=2) + "\n",
        bgi / "User/ScriptGroup" / (GROUP + ".json"): json.dumps({
            "index": 0, "name": GROUP,
            "config": {"pathingConfig": {"enabled": True, "skipPartySwitch": True,
                "autoPickEnabled": False, "autoSkipEnabled": False, "autoFightEnabled": False,
                "autoEatEnabled": False, "jsScriptUseEnabled": True, "recoverTiming": 2}},
            "projects": [{"name": "传送与短距离移动实测", "folderName": GROUP,
                "jsScriptSettingsObject": {}, "index": 0, "type": "Javascript", "status": "Enabled",
                "schedule": "Daily", "runNum": 1, "allowJsNotification": False, "allowJsHTTPHash": ""}]
        }, ensure_ascii=False, indent=2) + "\n"
    }
    for path, content in files.items():
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise ValueError("测试入口已被修改，未覆盖：" + str(path))
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return capability


def game_state():
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user.FindWindowW.restype = wintypes.HWND
    user.GetForegroundWindow.restype = wintypes.HWND
    user.IsIconic.argtypes = [wintypes.HWND]
    handle = user.FindWindowW("UnityWndClass", "原神") or user.FindWindowW("UnityWndClass", "Genshin Impact")
    return {"handle": int(handle or 0), "foreground": bool(handle and user.GetForegroundWindow() == handle),
            "minimized": bool(handle and user.IsIconic(handle))}


def validate_receipt(receipt):
    if receipt.get("kind") != "selected_waypoint_teleport_walk" or receipt.get("status") != "passed":
        return False
    return (all(receipt.get(k) is True for k in ("execution_attempted", "teleport_confirmed", "walk_confirmed", "stop_confirmed"))
            and receipt.get("held_input_count") == 0 and receipt.get("forward_key_down") is False
            and bool(receipt.get("finished_utc")))


def run(bgi, output):
    output.mkdir(parents=True, exist_ok=False)
    state = game_state()
    result = {"status": "preflight", "game": state, "execution_attempted": False, "bettergi": str(bgi)}
    if not state["handle"] or state["minimized"] or not state["foreground"]:
        result.update(status="blocked", reason="game_missing" if not state["handle"] else "game_not_foreground")
        write_json(output / "attempt.json", result)
        return result
    prepare(bgi)
    receipts = bgi / "User/LiveSmoke"
    old = set(receipts.glob("*/receipt.json"))
    args = [str(bgi / "BetterGI.exe"), "--startGroups", GROUP]
    try:
        subprocess.Popen(args, cwd=bgi)
    except OSError as error:
        if getattr(error, "winerror", None) != 740:
            raise
        os.startfile(args[0], "runas", subprocess.list2cmdline(args[1:]), str(bgi))
    result.update(status="waiting_for_receipt", execution_attempted=None)
    write_json(output / "attempt.json", result)
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        new = set(receipts.glob("*/receipt.json")) - old
        if len(new) > 1:
            raise RuntimeError("出现多份新执行记录，无法确认本次测试结果")
        if new:
            path = next(iter(new))
            try:
                report = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                time.sleep(0.2)
                continue
            if report.get("finished_utc"):
                result.update(status="passed" if validate_receipt(report) else "not_passed",
                    execution_attempted=report.get("execution_attempted", False), receipt=str(path))
                shutil.copytree(path.parent, output / "evidence")
                write_json(output / "attempt.json", result)
                return result
        time.sleep(0.25)
    result.update(status="unconfirmed", reason="no_final_receipt_within_150s",
                  execution_attempted=None)
    write_json(output / "attempt.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bettergi", type=Path, default=DEFAULT_BGI)
    parser.add_argument("--run", action="store_true", help="游戏前台且已选锚点时执行一次实测")
    parser.add_argument("--output", type=Path, help="本次实测的新记录目录")
    args = parser.parse_args()
    if args.run and args.output is None:
        parser.error("--run 需要 --output 指定新的记录目录")
    result = run(args.bettergi, args.output) if args.run else prepare(args.bettergi)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not args.run or result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
