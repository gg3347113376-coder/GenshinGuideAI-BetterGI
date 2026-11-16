"""Generate an evidence-linked task plan from a local guide clip, without controlling a game."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai.understanding import model_identity, prepare_evidence, understand
from ggai.vlm import OllamaVLM
from ggai.grounding import build_grounding, transcribe_audio


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--transcript", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True, help="Must be a new directory")
    p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True)
    p.add_argument("--frames", required=True, help="Comma-separated video times in seconds")
    p.add_argument("--id", default="guide_clip")
    p.add_argument("--name", default="真实攻略任务计划")
    p.add_argument("--source-url", default="")
    retry = p.add_mutually_exclusive_group()
    retry.add_argument("--retry-transcript", type=Path, help="Optional second ASR with video_sha256 provenance")
    retry.add_argument("--asr-model", type=Path, help="Existing local Whisper model for a fresh second opinion")
    p.add_argument("--audio", type=Path, help="Same-start audio when the video has no audio track")
    p.add_argument("--waypoints", type=Path, default=ROOT.parent / "BetterGI/BetterGenshinImpact/GameTask/AutoTrackPath/Assets/tp.json")
    p.add_argument("--model", default="qwen3.5:4b-q4_K_M")
    p.add_argument("--host", default="http://127.0.0.1:11435")
    args = p.parse_args()
    vlm = OllamaVLM(args.model, args.host, think=False, context_size=16384)
    digest = model_identity(vlm)
    project = prepare_evidence(args.video, args.transcript, args.output, args.start, args.end,
                               [float(x) for x in args.frames.split(",")], args.id, args.name, args.source_url)
    retry_path = args.retry_transcript
    if args.asr_model:
        retry_path = args.output / "asr-second-pass.json"
        transcribe_audio(args.video, args.audio or args.video, args.asr_model, retry_path, args.start, args.end, True)
    build_grounding(project, args.output, args.waypoints, retry_path)
    result = understand(project, args.output, vlm, digest)
    rejected = result["semantic_review"]["status"] != "supported_with_unknowns"
    print(json.dumps({"planning_status": "rejected" if rejected else "needs_review", "report": str(args.output / "report.html"), "steps": len(result["task_plan"]["steps"]),
                      "execution_attempted": False}, ensure_ascii=False))
    return 2 if rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
