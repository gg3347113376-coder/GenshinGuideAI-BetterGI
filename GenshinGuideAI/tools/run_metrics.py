"""生成方向一质量报告：覆盖率 + 对白金标准匹配。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggai import metrics  # noqa: E402


def to_markdown(project: dict, coverage: dict, summary: dict, matches: list[dict]) -> str:
    lines = [
        "# P4 方向一质量指标报告",
        "",
        f"- 项目：{project.get('project', {}).get('name', '')}",
        f"- 事件数：{coverage['events']}",
        "",
        "## 覆盖率",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 有证据帧 | {coverage['with_evidence']}（{coverage['evidence_ratio']:.1%}） |",
        f"| 有坐标 | {coverage['with_coords']}（{coverage['coords_ratio']:.1%}） |",
        f"| 待人工复核 | {coverage['review_pending']} |",
        f"| 平均置信度 | {coverage['mean_confidence']} |",
        "",
        "## 对白金标准匹配",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 金标准条数 | {summary['gold_items']} |",
        f"| 匹配到事件 | {summary['matched']}（{summary['match_rate']:.1%}） |",
        f"| 完全一致 | {summary['exact_match_rate']:.1%} |",
        f"| 平均字符相似度 | {summary['mean_similarity']:.3f} |",
        f"| 说话人准确率 | {summary['speaker_accuracy']:.1%} |",
        f"| 平均时间误差 | {summary['mean_time_error_s']} s |",
        "",
        "## 逐条对照",
        "",
        "| t(s) | 相似度 | 时间误差 | 说话人 | 预测文本 | 金标准 |",
        "|---|---|---|---|---|---|",
    ]
    for m in matches:
        if not m["matched"]:
            lines.append(f"| {m['gold_t']} | — | — | — | （未匹配） | {m['gold_text']} |")
            continue
        lines.append(
            "| {t} | {sim:.2f} | {dt}s | {sp} | {pred} | {gold} |".format(
                t=m["gold_t"],
                sim=m["text_similarity"],
                dt=m["time_error_s"],
                sp="✓" if m["speaker_match"] else f"✗({m.get('pred_speaker','')})",
                pred=m["pred_text"].replace("|", "/"),
                gold=m["gold_text"].replace("|", "/"),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--out", default="docs/reports/P4_metrics.md")
    parser.add_argument("--tolerance", type=float, default=8.0)
    args = parser.parse_args()
    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))["items"]
    coverage = metrics.project_coverage(project)
    matches = metrics.match_gold(project, gold, tolerance_s=args.tolerance)
    summary = metrics.summarize_matches(matches)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_markdown(project, coverage, summary, matches), encoding="utf-8")
    print(json.dumps({"coverage": coverage, "summary": summary, "report": str(out)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
