"""Re-plan from a recorded project and explicit, evidence-linked reviewer notes. No game input."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai.understanding import model_identity, replan_from_review
from ggai.vlm import OllamaVLM


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--review", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--model", default="qwen3.5:4b-q4_K_M")
    p.add_argument("--host", default="http://127.0.0.1:11435")
    a = p.parse_args()
    vlm = OllamaVLM(a.model, a.host, think=False, context_size=16384)
    result = replan_from_review(a.project, a.output, json.loads(a.review.read_text(encoding="utf-8")), vlm, model_identity(vlm))
    print(json.dumps({"steps": len(result["task_plan"]["steps"]), "report": str(a.output / "report.html"), "execution_attempted": False}, ensure_ascii=False))
    return 2 if result.get("semantic_review", {}).get("status", "supported_with_unknowns") != "supported_with_unknowns" else 0


if __name__ == "__main__":
    raise SystemExit(main())
