"""把目标区域内的多个 OBJ 合并为一个场景 OBJ（顶点按 manifest 偏移），供 Godot 导入。

用法：
  python tools/export_scene_obj.py --target 1470,195,10950 --radius 1200 --max-meshes 6 ^
      --out sandbox/data/scene.obj
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "tools"))
from export_terrain import load_nearby  # noqa: E402


def parse_obj(path: Path) -> tuple[np.ndarray, list[tuple[int, ...]]]:
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if line.startswith("v "):
                parts = line.split()
                if len(parts) >= 4:
                    verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif line.startswith("f "):
                idx = []
                for token in line.split()[1:]:
                    raw = token.split("/")[0]
                    if not raw:
                        continue
                    value = int(raw)
                    if value < 0:
                        value = len(verts) + value + 1
                    idx.append(value - 1)
                if len(idx) >= 3:
                    faces.append(tuple(idx))
    return np.asarray(verts, dtype=np.float64), faces


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="1470,195,10950")
    parser.add_argument("--radius", type=float, default=1200.0)
    parser.add_argument("--max-meshes", type=int, default=6)
    parser.add_argument("--out", default="sandbox/data/scene.obj")
    parser.add_argument("--meta", default="sandbox/data/scene_meta.json")
    args = parser.parse_args()
    target = tuple(float(v) for v in args.target.split(","))
    meshes = load_nearby(target, args.radius)[: args.max_meshes]
    if not meshes:
        print(json.dumps({"error": "没有网格"}, ensure_ascii=False))
        return 1

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total_v = 0
    total_f = 0
    used = []
    lo = np.array([np.inf, np.inf, np.inf])
    hi = np.array([-np.inf, -np.inf, -np.inf])
    with out_path.open("w", encoding="utf-8") as out:
        out.write("# merged by GenshinGuideAI\n")
        for mesh in meshes:
            verts, faces = parse_obj(mesh["path"])
            if verts.size == 0 or not faces:
                continue
            verts = verts + mesh["offset"]
            lo = np.minimum(lo, verts.min(axis=0))
            hi = np.maximum(hi, verts.max(axis=0))
            for v in verts:
                out.write(f"v {v[0]:.3f} {v[1]:.3f} {v[2]:.3f}\n")
            for face in faces:
                a, b, c = 0, 1, 2
                for k in range(1, len(face) - 1):
                    tri = (face[0], face[k], face[k + 1])
                    out.write(
                        "f %d %d %d\n"
                        % (tri[0] + total_v + 1, tri[1] + total_v + 1, tri[2] + total_v + 1)
                    )
            total_v += len(verts)
            total_f += sum(max(0, len(f) - 2) for f in faces)
            used.append(
                {
                    "name": mesh["name"],
                    "obj": mesh["path"].name,
                    "distance_m": round(mesh["distance"], 1),
                    "vertices": int(len(verts)),
                    "triangles": int(sum(max(0, len(f) - 2) for f in faces)),
                }
            )
    meta = {
        "target": list(target),
        "bbox": {"min": lo.tolist(), "max": hi.tolist()},
        "vertices": total_v,
        "triangles": total_f,
        "meshes": used,
        "out": str(out_path),
    }
    (ROOT / args.meta).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("vertices", "triangles")} | {"meshes": len(used)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
