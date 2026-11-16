"""生成微信可发送的紧凑压缩包（≤100MB）。

策略：
- 工作区 PNG 截图 → 1600px JPEG(q82)，显著减小体积；
- 原始会话 JSONL → zstd（保留完整记录）；
- 其余文件原样复制；
- 附说明文件。

用法：
  python tools\pack_wechat.py --out 成果包\微信版打包
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import zstandard
from PIL import Image

WORKSPACE = Path(os.environ.get(
    "DSH_WORKSPACE", r"C:\Users\20551\Documents\deepseek-harness\default-workspace"
))
TRANSCRIPT_DIR = Path(r"D:\OpenAI\GenshinGuideAI\成果包\工作区打包\会话记录")
PROJECT_ZIP = Path(r"D:\OpenAI\GenshinGuideAI\成果包\GenshinGuideAI_源码与文档_2026-11-06.zip")


def convert_png(src: Path, dst: Path, max_side: int = 1600, quality: int = 82) -> None:
    with Image.open(src) as image:
        image = image.convert("RGB")
        width, height = image.size
        scale = min(1.0, max_side / max(width, height))
        if scale < 1.0:
            image = image.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
        dst.parent.mkdir(parents=True, exist_ok=True)
        image.save(dst, "JPEG", quality=quality, optimize=True)


def copy_workspace(stage: Path) -> dict:
    target_root = stage / "工作区"
    stats = {"png_converted": 0, "copied": 0, "bytes_in": 0, "bytes_out": 0}
    for root, _dirs, files in os.walk(WORKSPACE):
        for name in files:
            src = Path(root) / name
            rel = src.relative_to(WORKSPACE)
            stats["bytes_in"] += src.stat().st_size
            if src.suffix.lower() == ".png":
                dst = target_root / rel.with_suffix(".jpg")
                try:
                    convert_png(src, dst)
                    stats["png_converted"] += 1
                    stats["bytes_out"] += dst.stat().st_size
                    continue
                except Exception:
                    pass
            dst = target_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            stats["copied"] += 1
            stats["bytes_out"] += dst.stat().st_size
    return stats


def pack_transcript(stage: Path) -> dict:
    out = stage / "会话记录"
    out.mkdir(parents=True, exist_ok=True)
    md = TRANSCRIPT_DIR / "对话全文.md"
    if md.exists():
        shutil.copyfile(md, out / md.name)
    raw = TRANSCRIPT_DIR / "session.v4.jsonl"
    result = {"md": md.exists(), "raw_zst": 0}
    if raw.exists():
        target = out / "session.v4.jsonl.zst"
        data = raw.read_bytes()
        target.write_bytes(zstandard.ZstdCompressor(level=19).compress(data))
        result["raw_zst"] = target.stat().st_size
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=r"D:\OpenAI\GenshinGuideAI\成果包\微信版打包")
    parser.add_argument("--max-side", type=int, default=1600)
    parser.add_argument("--quality", type=int, default=82)
    args = parser.parse_args()
    stage = Path(args.out)
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=True)

    ws_stats = copy_workspace(stage)
    tr_stats = pack_transcript(stage)

    related = stage / "相关项目"
    related.mkdir(parents=True, exist_ok=True)
    if PROJECT_ZIP.exists():
        shutil.copyfile(PROJECT_ZIP, related / PROJECT_ZIP.name)

    note = f"""本压缩包内容：
1. 工作区/         —— 会话工作区全部文件
2. 会话记录/       —— 对话全文.md（可读）与 session.v4.jsonl.zst（原始记录，zstd 压缩）
3. 相关项目/       —— GenshinGuideAI 源码与文档包

为满足微信单文件 100MB 限制做的处理：
- 工作区中的 {ws_stats['png_converted']} 张 PNG 截图已转为 1600px JPEG(q82)，文件名后缀由 .png 变为 .jpg；
- 会话原始记录已用 zstd 压缩（解压：zstd -d session.v4.jsonl.zst）；
- 其余文件原样保留。

原始工作区体积：{ws_stats['bytes_in'] / 1024 / 1024:.1f} MB
打包后工作区体积：{ws_stats['bytes_out'] / 1024 / 1024:.1f} MB
"""
    (stage / "说明.txt").write_text(note, encoding="utf-8-sig")
    print(json.dumps({"stage": str(stage), **ws_stats, "transcript": tr_stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
