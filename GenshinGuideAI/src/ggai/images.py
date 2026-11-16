"""Evidence image writes that work with Windows Unicode paths and fail visibly."""
from pathlib import Path
import cv2


def save_image(path: str | Path, frame, params=()) -> None:
    path = Path(path)
    ok, encoded = cv2.imencode(path.suffix, frame, list(params))
    if not ok:
        raise OSError(f"证据图编码失败：{path}")
    encoded.tofile(str(path))
