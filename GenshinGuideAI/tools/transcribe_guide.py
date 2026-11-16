"""Transcribe a local guide clip with source hashes. No game operations."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai.grounding import transcribe_audio


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--audio", type=Path, help="Same-start audio track; defaults to the video")
    p.add_argument("--model-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True)
    p.add_argument("--domain-prompt", action="store_true", help="Second opinion with game terms; may introduce bias")
    a = p.parse_args()
    result = transcribe_audio(a.video, a.audio or a.video, a.model_dir, a.output, a.start, a.end, a.domain_prompt)
    print(json.dumps({"output": str(a.output), "segments": len(result["segments"]), "execution_attempted": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
