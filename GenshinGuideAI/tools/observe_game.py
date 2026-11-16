"""只读观测：截取游戏窗口画面，OCR 字幕/任务文本，输出 JSONL。

不做任何输入/注入，只读屏幕。用于 B 类（本机正式客户端）的合法观测。

用法：
  python tools\observe_game.py --image data\frames\explore_dbg\e_00060.00.jpg --out runs\observe_test.jsonl
  python tools\observe_game.py --interval 5 --duration 60 --out runs\game_observations.jsonl
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai.extract import norm_text  # noqa: E402
from ggai.ocr import make_ocr  # noqa: E402

SPEAKER_BAND = (0.30, 0.690, 0.40, 0.065)
SUBTITLE_BAND = (0.10, 0.755, 0.80, 0.095)
# 多组候选条带：录像(1080p)与实机窗口字幕位置不同，取第一个能读出的
BAND_CANDIDATES = [
    ((0.30, 0.690, 0.40, 0.065), (0.10, 0.755, 0.80, 0.095)),
    ((0.30, 0.815, 0.40, 0.045), (0.08, 0.855, 0.84, 0.075)),
    ((0.30, 0.780, 0.40, 0.050), (0.10, 0.820, 0.80, 0.080)),
]
QUEST_BAND = (0.00, 0.33, 0.28, 0.09)
DIALOGUE_MARK_BAND = (0.02, 0.06, 0.24, 0.09)


def yellow_ratio(crop: np.ndarray) -> float:
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, (15, 120, 140), (40, 255, 255))
    return float(yellow.mean()) / 255.0


def cjk_count(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def ocr_band(engine, image: np.ndarray, band: tuple[float, float, float, float], scale: float = 2.0) -> str:
    h, w = image.shape[:2]
    x, y, bw, bh = band
    crop = image[int(y * h) : int((y + bh) * h), int(x * w) : int((x + bw) * w)]
    if crop.size == 0:
        return ""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    raw, _ = engine(gray, use_det=False, use_cls=False, use_rec=True)
    texts = [norm_text(str(row[0])) for row in (raw or []) if isinstance(row, (list, tuple)) and len(row) >= 2]
    return "".join(texts).strip()


def window_rect(title: str = "原神") -> tuple[int, int, int, int] | None:
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return None
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    width, height = rect.right, rect.bottom
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    x = max(0, min(origin.x, screen_w - 1))
    y = max(0, min(origin.y, screen_h - 1))
    width = min(width, screen_w - x)
    height = min(height, screen_h - y)
    return x, y, width, height


def grab_wgc(window_name: str = "原神") -> np.ndarray | None:
    try:
        from windows_capture import WindowsCapture, Frame, InternalCaptureControl
    except Exception:
        return None
    frames: list[np.ndarray] = []
    capture = WindowsCapture(cursor_capture=False, draw_border=False, window_name=window_name)

    @capture.event
    def on_frame_arrived(frame: Frame, control: InternalCaptureControl):
        frames.append(frame.frame_buffer[:, :, :3].copy())
        control.stop()

    @capture.event
    def on_closed():
        return None

    try:
        capture.start()
    except Exception:
        return None
    return frames[0] if frames else None


def grab(region: tuple[int, int, int, int] | None, backend: str = "auto") -> np.ndarray | None:
    if backend in ("auto", "wgc"):
        image = grab_wgc()
        if image is not None:
            return image
        if backend == "wgc":
            return None
    from PIL import ImageGrab

    image = ImageGrab.grab(bbox=region) if region else ImageGrab.grab()
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def observe(engine, image: np.ndarray) -> dict:
    h, w = image.shape[:2]
    x, y, bw, bh = SUBTITLE_BAND
    band_crop = image[int(y * h) : int((y + bh) * h), int(x * w) : int((x + bw) * w)]
    subtitle = ""
    if not (band_crop.size and yellow_ratio(band_crop) > 0.03):
        for speaker_band, text_band in BAND_CANDIDATES:
            speaker = ocr_band(engine, image, speaker_band, scale=2.5)
            text = ocr_band(engine, image, text_band, scale=2.5)
            candidate = (speaker + "：" + text).strip("：") if text else ""
            if cjk_count(candidate) >= 2:
                subtitle = candidate
                break
    quest = ocr_band(engine, image, QUEST_BAND, scale=3.0)
    if cjk_count(quest) < 2:
        quest = ""
    mark = ocr_band(engine, image, DIALOGUE_MARK_BAND, scale=2.5)
    if subtitle or any(word in mark for word in ("自动", "跳过", "选项")):
        scene = "dialogue"
    elif quest:
        scene = "open_world"
    else:
        scene = "unknown"
    return {"scene": scene, "subtitle": subtitle, "quest": quest}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="", help="单张图片模式（验证用）")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--out", default="runs/game_observations.jsonl")
    parser.add_argument("--save-dir", default="")
    parser.add_argument("--save-all", action="store_true")
    parser.add_argument("--allow-fullscreen", action="store_true")
    parser.add_argument("--backend", default="auto", choices=["auto", "wgc", "grab"])
    args = parser.parse_args()

    engine = make_ocr("rapidocr").raw_engine()
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("", encoding="utf-8")

    if args.image:
        image = cv2.imread(str(ROOT / args.image))
        if image is None:
            print(json.dumps({"error": f"无法读取 {args.image}"}, ensure_ascii=False))
            return 1
        result = observe(engine, image)
        result.update({"ts": time.time(), "source": args.image})
        out.write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 0

    region = window_rect()
    if args.backend == "wgc" or (args.backend == "auto" and region is not None):
        pass
    if region is None and args.backend != "wgc":
        if not args.allow_fullscreen:
            print(json.dumps({"error": "未找到标题为「原神」的窗口；请先启动游戏，或加 --allow-fullscreen"}, ensure_ascii=False))
            return 1
        print(json.dumps({"warning": "未找到游戏窗口，按全屏截取"}, ensure_ascii=False))
    started = time.time()
    count = 0
    while time.time() - started < args.duration:
        image = grab(region, backend=args.backend)
        result = observe(engine, image)
        if args.save_dir and args.save_all:
            save_dir = ROOT / args.save_dir
            save_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(save_dir / f"all_{count:04d}.jpg"), image)
        if args.save_dir and result.get("subtitle"):
            save_dir = ROOT / args.save_dir
            save_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(save_dir / f"sub_{count:03d}.jpg"), image)
        result.update({"ts": round(time.time(), 3), "t_rel": round(time.time() - started, 1)})
        with out.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        count += 1
        time.sleep(max(1.0, args.interval))
    print(json.dumps({"observations": count, "out": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
