"""视频读取、抽样、场景切分与证据帧导出（PyAV + OpenCV）。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import av
import cv2
import numpy as np

from .images import save_image


@dataclass
class VideoInfo:
    path: str
    duration_s: float
    fps: float
    width: int
    height: int
    sha256: str


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while data := handle.read(chunk):
            digest.update(data)
    return digest.hexdigest()


def probe(path: str | Path) -> VideoInfo:
    container = av.open(str(path))
    try:
        stream = container.streams.video[0]
        duration = float(container.duration / av.time_base) if container.duration else 0.0
        if not duration:
            duration = float(stream.duration * stream.time_base) if stream.duration else 0.0
        fps = float(stream.average_rate) if stream.average_rate else 0.0
        return VideoInfo(
            path=str(path),
            duration_s=duration,
            fps=fps,
            width=int(stream.codec_context.width),
            height=int(stream.codec_context.height),
            sha256=sha256_file(path),
        )
    finally:
        container.close()


def iter_sampled_frames(
    path: str | Path,
    sample_fps: float = 1.0,
    start_s: float = 0.0,
    end_s: float | None = None,
) -> Iterator[tuple[float, np.ndarray]]:
    """按固定采样率产出 (时间戳秒, BGR 帧)。"""
    if sample_fps <= 0:
        raise ValueError("sample_fps 必须大于 0")
    step = 1.0 / sample_fps
    container = av.open(str(path))
    try:
        stream = container.streams.video[0]
        next_t = start_s
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            t = float(frame.pts * frame.time_base)
            if t + 1e-6 < start_s:
                continue
            if end_s is not None and t > end_s:
                break
            if t + 1e-6 >= next_t:
                yield t, frame.to_ndarray(format="bgr24")
                next_t = t + step
    finally:
        container.close()


def _histogram(image: np.ndarray) -> np.ndarray:
    small = cv2.resize(image, (160, 90), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist


def scene_cuts(
    path: str | Path,
    sample_fps: float = 2.0,
    threshold: float = 0.55,
    start_s: float = 0.0,
    end_s: float | None = None,
) -> list[float]:
    """基于 HSV 直方图相关性的镜头切换点（秒）。

    threshold 越小越敏感；0.55 适合游戏录屏（HUD 常驻，画面变化有限）。
    """
    cuts: list[float] = []
    previous: np.ndarray | None = None
    previous_t = 0.0
    for t, frame in iter_sampled_frames(path, sample_fps=sample_fps, start_s=start_s, end_s=end_s):
        hist = _histogram(frame)
        if previous is not None:
            similarity = float(cv2.compareHist(previous, hist, cv2.HISTCMP_CORREL))
            if similarity < threshold:
                cuts.append(round(t, 2))
        previous, previous_t = hist, t
    return cuts


def extract_frames(
    path: str | Path,
    times: list[float],
    out_dir: str | Path,
    prefix: str = "frame",
    image_format: str = "jpg",
) -> list[Path]:
    """按给定时间点导出证据帧。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    wanted = sorted(times)
    saved: list[Path] = []
    index = 0
    container = av.open(str(path))
    try:
        stream = container.streams.video[0]
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            t = float(frame.pts * frame.time_base)
            while index < len(wanted) and t + 1e-6 >= wanted[index]:
                path_out = out / f"{prefix}_{wanted[index]:08.2f}.{image_format}"
                save_image(path_out, frame.to_ndarray(format="bgr24"))
                saved.append(path_out)
                index += 1
            if index >= len(wanted):
                break
    finally:
        container.close()
    return saved
