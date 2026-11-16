"""Reprocess saved guide evidence with typed targets and a fresh independent review. No game input."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai.semantic_review import reprocess_project
from ggai.understanding import model_identity
from ggai.vlm import OllamaVLM


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--model", default="qwen3.5:4b-q4_K_M")
    p.add_argument("--review-model", help="独立语义复核模型；省略时与规划模型相同")
    p.add_argument("--host", default="http://127.0.0.1:11435")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--review-only", action="store_true", help="保留计划，只重试独立复核")
    mode.add_argument("--recompile", action="store_true", help="从原始模型草案重新编译顺序并复核，不重新生成任务")
    p.add_argument("--cpu", action="store_true", help="本次运行使用 CPU，不占用 GPU")
    a = p.parse_args()
    vlm = OllamaVLM(a.model, a.host, think=False, context_size=16384, gpu_layers=0 if a.cpu else None)
    reviewer = None
    if a.review_model:
        client = OllamaVLM(a.review_model, a.host, think=False, context_size=8192, gpu_layers=0 if a.cpu else None)
        reviewer = (client, model_identity(client))
    result = reprocess_project(a.project, a.output, vlm, model_identity(vlm), review_only=a.review_only, reviewer=reviewer, recompile=a.recompile)
    status = result["semantic_review"]["status"]
    print(json.dumps({"review_status": status, "steps": len(result["task_plan"]["steps"]),
        "report": str(a.output / "report.html"), "execution_attempted": False}, ensure_ascii=False))
    return 0 if status == "supported_with_unknowns" else 2


if __name__ == "__main__":
    raise SystemExit(main())
