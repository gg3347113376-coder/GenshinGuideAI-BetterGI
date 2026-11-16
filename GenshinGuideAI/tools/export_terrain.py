"""把指定区域内的 OBJ 网格合并成高度图（JSON + 预览图）。

用法：
  python tools/export_terrain.py --target 1470,195,10950 --radius 1200 --grid 256 ^
      --out sandbox/data/terrain.json --preview docs/reports/terrain_preview.png
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PKG = Path(r"D:\OpenAI\原神寻路\outputs\GenshinMaps_7.1")
MESH_DIR = PKG / "data" / "client7_1" / "meshes"
MANIFEST = PKG / "manifests" / "legacy_202602_all_hlod_manifest.json"


def load_nearby(target: tuple[float, float, float], radius: float) -> list[dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    picked = []
    for group in ("city_hlod", "area_hlod", "ares_hlod"):
        for item in manifest.get(group, []):
            pos = item.get("position", {})
            point = (pos.get("x", 0.0), pos.get("y", 0.0), pos.get("z", 0.0))
            if point == (0.0, 0.0, 0.0):
                continue
            distance = math.dist(point, target)
            if distance > radius:
                continue
            lods = item.get("lods", {})
            obj_name = lods.get("0") or next(iter(lods.values()), None)
            if not obj_name:
                continue
            path = MESH_DIR / obj_name
            if not path.exists():
                continue
            picked.append(
                {
                    "name": item.get("name"),
                    "path": path,
                    "offset": np.array(point, dtype=np.float64),
                    "distance": distance,
                }
            )
    picked.sort(key=lambda x: x["distance"])
    return picked


def read_vertices(path: Path) -> np.ndarray:
    verts = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if line.startswith("v "):
                parts = line.split()
                if len(parts) >= 4:
                    verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
    return np.asarray(verts, dtype=np.float64)


def build_heightmap(cloud: np.ndarray, grid: int, margin: float = 60.0) -> dict:
    lo = cloud.min(axis=0)
    hi = cloud.max(axis=0)
    lo[0] -= margin
    lo[2] -= margin
    hi[0] += margin
    hi[2] += margin
    span_x = hi[0] - lo[0]
    span_z = hi[2] - lo[2]
    cell = max(span_x, span_z) / (grid - 1)
    ix = np.clip(((cloud[:, 0] - lo[0]) / cell).astype(np.int32), 0, grid - 1)
    iz = np.clip(((cloud[:, 2] - lo[2]) / cell).astype(np.int32), 0, grid - 1)
    heights = np.full((grid, grid), np.nan, dtype=np.float32)
    ys = cloud[:, 1].astype(np.float32)
    order = np.argsort(ys)
    heights[iz[order], ix[order]] = ys[order]  # 后写覆盖：每格保留最高点
    valid = ~np.isnan(heights)
    if not valid.any():
        raise ValueError("没有有效顶点")
    # 最近邻填补空洞
    mask = valid.astype(np.uint8)
    dist, labels = cv2.distanceTransformWithLabels(
        mask, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL
    )
    ys_idx, xs_idx = np.where(mask == 1)
    label_to_value = np.zeros(labels.max() + 1, dtype=np.float32)
    label_to_value[labels[ys_idx, xs_idx]] = heights[ys_idx, xs_idx]
    filled = label_to_value[labels]
    # 轻微平滑，避免单点尖刺
    filled = cv2.GaussianBlur(filled, (3, 3), 0)
    return {
        "bbox": {"min": lo.tolist(), "max": hi.tolist()},
        "grid": grid,
        "cell": float(cell),
        "heights": np.round(filled, 2).tolist(),
        "valid_cells": int(valid.sum()),
    }


def preview(terrain: dict, out: Path) -> None:
    h = np.asarray(terrain["heights"], dtype=np.float32)
    norm = cv2.normalize(h, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    color = cv2.applyColorMap(norm, cv2.COLORMAP_TURBO)
    color = cv2.flip(color, 0)
    color = cv2.resize(color, (768, 768), interpolation=cv2.INTER_NEAREST)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), color)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="1470,195,10950")
    parser.add_argument("--radius", type=float, default=1200.0)
    parser.add_argument("--grid", type=int, default=256)
    parser.add_argument("--max-meshes", type=int, default=6)
    parser.add_argument("--out", default="sandbox/data/terrain.json")
    parser.add_argument("--preview", default="docs/reports/terrain_preview.png")
    args = parser.parse_args()
    target = tuple(float(v) for v in args.target.split(","))
    meshes = load_nearby(target, args.radius)[: args.max_meshes]
    if not meshes:
        print(json.dumps({"error": "目标范围内没有网格"}, ensure_ascii=False))
        return 1
    clouds = []
    used = []
    for mesh in meshes:
        verts = read_vertices(mesh["path"])
        if verts.size == 0:
            continue
        clouds.append(verts + mesh["offset"])
        used.append(
            {
                "name": mesh["name"],
                "obj": mesh["path"].name,
                "distance_m": round(mesh["distance"], 1),
                "vertices": int(verts.shape[0]),
            }
        )
    cloud = np.vstack(clouds)
    terrain = build_heightmap(cloud, args.grid)
    terrain["sources"] = used
    terrain["target"] = list(target)
    terrain["vertex_count"] = int(cloud.shape[0])
    out = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(terrain, ensure_ascii=False), encoding="utf-8")
    preview(terrain, ROOT / args.preview if not Path(args.preview).is_absolute() else Path(args.preview))
    print(
        json.dumps(
            {
                "meshes": len(used),
                "vertices": int(cloud.shape[0]),
                "grid": args.grid,
                "cell_m": round(terrain["cell"], 2),
                "valid_cells": terrain["valid_cells"],
                "out": str(out),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
