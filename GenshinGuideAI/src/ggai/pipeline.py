"""方向一 MVP 管线：视频 → 采样 → OCR → 规则事件 → 协议 JSON。"""
from __future__ import annotations

import json
import time
from pathlib import Path

import cv2

from . import protocol, regions, strips, video
from .extract import Observation, extract_events
from .ocr import make_ocr
from .images import save_image


def build_project(
    video_path: str | Path,
    out_json: str | Path,
    project_id: str = "proj_auto",
    name: str | None = None,
    start_s: float = 0.0,
    duration_s: float | None = None,
    sample_fps: float = 1.0,
    frames_dir: str | Path | None = None,
    ocr_backend: str = "rapidocr",
    ocr_mode: str = "strips",
    region_names: tuple[str, ...] = ("quest_tracker", "subtitle", "choices"),
    db_path: str | Path | None = None,
    verbose: bool = True,
) -> dict:
    video_path = Path(video_path)
    info = video.probe(video_path)
    end_s = None if duration_s is None else start_s + duration_s
    project = protocol.new_project(
        project_id,
        name or f"{video_path.stem} 解析",
        description="方向一 MVP 自动生成；坐标缺失处为 unknown",
    )
    project["project"]["model_versions"] = {
        "ocr": ocr_backend,
        "rules": "ggai-0.1.0",
        "pipeline": "ggai-pipeline-0.1.0",
    }
    protocol.add_source(
        project,
        "src_1",
        str(video_path),
        info.duration_s,
        sha256=info.sha256,
        fps=info.fps,
        width=info.width,
        height=info.height,
    )
    segment = {
        "id": "seg_1",
        "source_id": "src_1",
        "start_s": start_s,
        "end_s": end_s or info.duration_s,
        "kind": "unknown",
        "confidence": 0.0,
        "notes": "占位，采样后替换为分类结果",
    }
    project["segments"].append(segment)

    frames_path = Path(frames_dir) if frames_dir else None
    if frames_path:
        frames_path.mkdir(parents=True, exist_ok=True)

    ocr = make_ocr(ocr_backend)
    fast = ocr_mode == "strips" and hasattr(ocr, "raw_engine")
    raw_engine = ocr.raw_engine() if fast else None
    observations: list[Observation] = []
    last_text: dict[str, str] = {}
    saved_frames = 0
    started = time.time()
    for index, (t_s, frame) in enumerate(
        video.iter_sampled_frames(video_path, sample_fps=sample_fps, start_s=start_s, end_s=end_s)
    ):
        region_items = {}
        changed = False
        if fast:
            region_items = strips.read_hud(frame, raw_engine)
            for region_name, items in region_items.items():
                text = " ".join(i.text for i in items)
                if text != last_text.get(region_name):
                    changed = True
                    last_text[region_name] = text
        else:
            for region_name in region_names:
                crop = regions.crop(frame, region_name)
                if crop.size == 0:
                    region_items[region_name] = []
                    continue
                items = ocr.recognize(crop)
                region_items[region_name] = items
                text = " ".join(i.text for i in items)
                if text != last_text.get(region_name):
                    changed = True
                    last_text[region_name] = text
        observation = Observation(t_s=t_s, regions=region_items)
        if changed and frames_path is not None:
            frame_file = frames_path / f"f_{t_s:08.2f}.jpg"
            save_image(frame_file, frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
            observation.frame_path = str(frame_file)
            saved_frames += 1
        observations.append(observation)
        if verbose and index % 30 == 0:
            print(
                f"  sampled {index} frames, t={t_s:.1f}s, saved={saved_frames}, elapsed={time.time() - started:.0f}s",
                flush=True,
            )

    from .segmentation import classify_segments, coverage

    segments = classify_segments(observations, total_end_s=end_s or info.duration_s)
    project["segments"] = segments
    events = extract_events(project, "src_1", observations)
    for event in events:
        t = event["video_time"]["start_s"]
        for seg in segments:
            if seg["start_s"] - 0.5 <= t <= seg["end_s"] + 0.5:
                event["segment_id"] = seg["id"]
                break
    seg_coverage = coverage(segments)
    project["project"]["model_versions"]["sampled_frames"] = str(len(observations))
    project["project"]["model_versions"]["saved_frames"] = str(saved_frames)

    # 观测落盘：规则调整后可只重跑抽取，不必重新 OCR
    obs_path = Path(out_json).with_suffix(".obs.jsonl")
    with obs_path.open("w", encoding="utf-8") as handle:
        for observation in observations:
            handle.write(
                json.dumps(
                    {
                        "t": observation.t_s,
                        "frame": observation.frame_path,
                        "regions": {
                            name: [item.to_dict() for item in items]
                            for name, items in observation.regions.items()
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    project["project"]["model_versions"]["observations_file"] = obs_path.name

    errors = protocol.validate(project)
    if errors:
        raise ValueError("生成的协议 JSON 未通过校验：" + "; ".join(errors[:3]))
    protocol.dump_project(project, out_json)

    if db_path:
        from . import store

        store.import_project(project, db_path)

    return {
        "video": str(video_path),
        "duration_s": info.duration_s,
        "sampled": len(observations),
        "saved_frames": saved_frames,
        "segments": len(segments),
        "coverage": seg_coverage,
        "events": len(events),
        "output": str(out_json),
        "elapsed_s": round(time.time() - started, 1),
    }
