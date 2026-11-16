"""小地图定位：用 BetterGI 的 Teyvat 底图做模板匹配，输出世界坐标。

原理（与 BetterGI 一致）：
- 粗匹配：底图缩小 5 倍，小地图缩到 52×52，TM_SQDIFF 全图搜索；
- 精匹配：底图原尺寸，小地图 260×260，在粗结果附近 ±20px 搜索；
- 坐标换算：worldX = Left - (mapX + size/2) * zoom / Scale（MapToWorld）。

用法：
  python tools/minimap_localize.py --video data\videos\bili_p002_1080.mp4 --times 600,605,610
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = Path(r"C:\Program Files\BetterGI\Assets\Map\Teyvat")
ORIGINAL_SIZE = 156
ROUGH_SIZE = 52
EXACT_SIZE = 260
ROUGH_ZOOM = 5
EXACT_ZOOM = 1
ROUGH_SEARCH_RADIUS = 50
EXACT_SEARCH_RADIUS = 20


def load_layers() -> list[dict]:
    layers: dict[str, dict] = {}
    for name in ("mapback_info.json", "mapback_6_0_info.json"):
        path = MAP_DIR / name
        if not path.exists():
            continue
        for item in json.loads(path.read_text(encoding="utf-8")):
            layers.setdefault(item["LayerId"], item)
    return list(layers.values())


def crop_minimap(frame: np.ndarray, center: tuple[int, int], size: int) -> np.ndarray:
    cx, cy = center
    half = size // 2
    h, w = frame.shape[:2]
    x0, y0 = max(0, cx - half), max(0, cy - half)
    x1, y1 = min(w, cx + half), min(h, cy + half)
    crop = frame[y0:y1, x0:x1]
    # BetterGI 约定：先把小地图归一到 156×156，再按 52/260 匹配
    return cv2.resize(crop, (ORIGINAL_SIZE, ORIGINAL_SIZE), interpolation=cv2.INTER_AREA)


def build_mask(size: int) -> np.ndarray:
    mask = np.zeros((size, size), dtype=np.uint8)
    cv2.circle(mask, (size // 2, size // 2), int(size * 0.46), 255, -1)
    cv2.circle(mask, (size // 2, size // 2), max(6, int(size * 0.13)), 0, -1)
    return mask


def map_to_world(pos: tuple[float, float], zoom: float, size: int, layer: dict) -> tuple[float, float]:
    scale = float(layer.get("Scale", 1))
    return (
        float(layer["Left"]) - (pos[0] + size / 2.0) * zoom / scale,
        float(layer["Top"]) - (pos[1] + size / 2.0) * zoom / scale,
    )


def world_to_map(world: tuple[float, float], zoom: float, layer: dict) -> tuple[int, int]:
    scale = float(layer.get("Scale", 1))
    return (
        int(round((float(layer["Left"]) - world[0]) * scale / zoom)),
        int(round((float(layer["Top"]) - world[1]) * scale / zoom)),
    )


def match_layer(gray_map: np.ndarray, mini_gray: np.ndarray, mask: np.ndarray, layer: dict) -> dict:
    rough_map = cv2.resize(gray_map, (max(1, gray_map.shape[1] // ROUGH_ZOOM), max(1, gray_map.shape[0] // ROUGH_ZOOM)), interpolation=cv2.INTER_AREA)
    rough_tpl = cv2.resize(mini_gray, (ROUGH_SIZE, ROUGH_SIZE), interpolation=cv2.INTER_AREA)
    rough_mask = cv2.resize(mask, (ROUGH_SIZE, ROUGH_SIZE), interpolation=cv2.INTER_NEAREST)
    if rough_map.shape[0] < ROUGH_SIZE or rough_map.shape[1] < ROUGH_SIZE:
        return {"layer": layer["LayerId"], "score": 1e9}
    res = cv2.matchTemplate(rough_map, rough_tpl, cv2.TM_SQDIFF, mask=rough_mask)
    res = np.nan_to_num(res, nan=1e9, posinf=1e9, neginf=1e9)
    _, _, min_loc, _ = cv2.minMaxLoc(res)
    rough_world = map_to_world(min_loc, ROUGH_ZOOM, ROUGH_SIZE, layer)

    # 精匹配：围绕粗结果裁剪
    cx, cy = world_to_map(rough_world, EXACT_ZOOM, layer)
    half_radius = EXACT_SEARCH_RADIUS + EXACT_SIZE // 2
    x0 = max(0, cx - half_radius)
    y0 = max(0, cy - half_radius)
    x1 = min(gray_map.shape[1], cx + half_radius)
    y1 = min(gray_map.shape[0], cy + half_radius)
    region = gray_map[y0:y1, x0:x1]
    if region.shape[0] < EXACT_SIZE or region.shape[1] < EXACT_SIZE:
        return {
            "layer": layer["LayerId"],
            "score": float(res[min_loc[1], min_loc[0]]) / (ROUGH_SIZE * ROUGH_SIZE * 255.0 ** 2),
            "world": [round(rough_world[0], 1), round(rough_world[1], 1)],
            "stage": "rough_only",
        }
    exact_tpl = cv2.resize(mini_gray, (EXACT_SIZE, EXACT_SIZE), interpolation=cv2.INTER_CUBIC)
    exact_mask = cv2.resize(mask, (EXACT_SIZE, EXACT_SIZE), interpolation=cv2.INTER_NEAREST)
    res2 = cv2.matchTemplate(region, exact_tpl, cv2.TM_SQDIFF, mask=exact_mask)
    res2 = np.nan_to_num(res2, nan=1e9, posinf=1e9, neginf=1e9)
    _, _, min_loc2, _ = cv2.minMaxLoc(res2)
    world = map_to_world((x0 + min_loc2[0], y0 + min_loc2[1]), EXACT_ZOOM, EXACT_SIZE, layer)
    score = float(res2[min_loc2[1], min_loc2[0]]) / (EXACT_SIZE * EXACT_SIZE * 255.0 ** 2)
    return {
        "layer": layer["LayerId"],
        "score": round(score, 5),
        "world": [round(world[0], 1), round(world[1], 1)],
        "stage": "exact",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--times", default="600,605,610,615,620")
    parser.add_argument("--center", default="190,140")
    parser.add_argument("--size", type=int, default=230)
    parser.add_argument("--out", default="runs/minimap_localize.json")
    args = parser.parse_args()
    cx, cy = (int(v) for v in args.center.split(","))
    times = [float(t) for t in args.times.split(",")]
    frames_dir = ROOT / "data" / "frames" / "minimap_probe"
    from ggai import video  # noqa: E402  (延迟导入，避免无视频时也加载依赖)

    saved = video.extract_frames(args.video, times, frames_dir, prefix="mm")
    layers = load_layers()
    gray_maps = {}
    for layer in layers:
        path = MAP_DIR / f"{layer['LayerId']}_gray.webp"
        if path.exists():
            gray_maps[layer["LayerId"]] = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    mask = build_mask(ORIGINAL_SIZE)
    results = []
    for path in saved:
        frame = cv2.imread(str(path))
        if frame is None:
            continue
        mini = crop_minimap(frame, (cx, cy), args.size)
        mini_gray = cv2.cvtColor(mini, cv2.COLOR_BGR2GRAY)
        candidates = []
        for layer in layers:
            gray = gray_maps.get(layer["LayerId"])
            if gray is None:
                continue
            candidates.append(match_layer(gray, mini_gray, mask, layer))
        candidates.sort(key=lambda item: item["score"])
        best = candidates[0] if candidates else {}
        results.append({"t": path.stem.split("_")[-1], "best": best, "top3": candidates[:3]})
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in results:
        best = row["best"]
        print(f"t={row['t']:>6}  {best.get('layer')}  score={best.get('score')}  world={best.get('world')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
