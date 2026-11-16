"""Check saved real-guide plans; expected answers never enter model prompts."""
import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ggai import protocol
from ggai.planning import dump, sha256


def evaluate_case(case, folder):
    project = protocol.load_project(folder / "project.json")
    plan = project["task_plan"]; expected = case["expected"]
    actions = [s["action_id"] for s in plan["steps"]]
    errors = protocol.validate(project, folder)
    checks = []
    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
    check("协议与证据完整", not errors, errors)
    check("全部原始数据无损往返", json.loads((folder / "roundtrip.json").read_text(encoding="utf-8")) == project, "比较完整 JSON")
    check("有限语义检查", project["grounding"]["plan_review"]["status"] != "rejected", project["grounding"]["plan_review"]["issues"])
    if "semantic_review" in project:
        from ggai.targets import binding_issues
        check("目标类型与证据绑定", not binding_issues(project), binding_issues(project))
        if project["semantic_review"]["version"] != "1.0.0":
            from ggai.targets import sequence_issues
            check("总目标与指令来源及顺序", not sequence_issues(project), sequence_issues(project))
        check("独立语义复核完成且有支持", project["semantic_review"]["status"] == "supported_with_unknowns", project["semantic_review"]["issues"])
    check("任务目标关键词", all(word in plan["goal"] for word in expected["goal_contains"]), expected["goal_contains"])
    check("没有误用常驻界面文字", not any(word in plan["goal"] for word in expected["excluded_goals"]), expected["excluded_goals"])
    cursor = 0
    for action in actions:
        if cursor < len(expected["required_actions"]) and action == expected["required_actions"][cursor]:
            cursor += 1
    check("关键动作按序覆盖", cursor == len(expected["required_actions"]), expected["required_actions"])
    if expected.get("first_teleport_after_unlock"):
        ordered = "interact" in actions and "teleport" in actions and actions.index("interact") < actions.index("teleport")
        check("首次传送发生在解锁之后", ordered, "不能在解锁前额外插入传送")
    check("未出现预设禁止动作", not any(a in actions for a in expected["forbidden_actions"]), expected["forbidden_actions"])
    check("未冒认锚点坐标或解锁状态", all(a["verified_point_id"] is None and a["verified_coordinates"] is None and a["current_player_unlocked"] == "unknown" for a in project["grounding"]["anchors"]), "已知边界必须保留")
    check("未执行游戏", plan["execution_allowed"] is False and project["execution_runs"] == [] and all(s["observed_result"]["status"] == "not_executed" for s in plan["steps"]), "输出状态及本离线入口检查；不代表实机验收")
    review_path = folder / "quality-review.json"
    human_review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.is_file() else {"status": "not_reviewed", "findings": ["尚未进行人工语义核对"]}
    prior_path = folder / "previous-project.json"
    prior_ids = {r["id"] for r in json.loads(prior_path.read_text(encoding="utf-8"))["analysis_runs"]} if prior_path.is_file() else set()
    current_runs = [r for r in project["analysis_runs"] if r["id"] not in prior_ids]
    return {"semantic_review_status": project.get("semantic_review", {}).get("status", "not_available"), "human_review": human_review, "id": case["id"], "name": case["name"], "url": case["url"], "clip": [case["start"], case["end"]],
            "directory": folder.name, "project_sha256": sha256(folder / "project.json"), "goal": plan["goal"],
            "actions": actions, "steps": [{"title": s["title"], "target": s["params"].get("target_label"), "uncertainties": s["uncertainties"]} for s in plan["steps"]],
            "checks": checks, "passed_selected_checks": all(c["passed"] for c in checks),
            "plan_checks_passed": all(c["passed"] for c in checks if c["name"] != "独立语义复核完成且有支持"),
            "model_calls": len(current_runs), "model_seconds": round(sum(r["elapsed_s"] for r in current_runs), 3),
            "exact_waypoints_identified": 0,
            "ocr_rows": sum(len(f["rows"]) for f in project["grounding"]["frames"]),
            "original_transcript_rows": len(project["grounding"]["transcripts"])}


def write_comparison(result, base):
    esc = lambda v: html.escape(str(v), quote=True)
    content = '<h1>真实攻略离线回归</h1><p>任务理解 · 界面文字 · 转写候选 · 锚点歧义</p><div class="notice">未操作游戏。通过选定断言不等于任意攻略可用，也不代表路线或游戏执行成功。</div>'
    content += '<p><strong>' + str(sum(r.get("passed_selected_checks", False) for r in result["cases"])) + '/' + str(len(result["cases"])) + '</strong> 段通过本轮选定断言。<a href="evaluation.json">完整检查结果</a> · <a href="cases.json">预先记录的测试范围</a> · <a href="tests.json">代码回归结果</a></p>'
    content += '<p>这三段已用于发现并修复问题，属于开发回归样本。期望动作未传入模型；没有用人工逐步答案覆盖模型输出。历次运行按独立目录保留，旧结果未覆盖；旧结果适用当时的检查规则。</p>'
    if result.get("counterexamples"):
        negatives = result["counterexamples"]["cases"]
        blocked = sum(r.get("mutation_blocked", r["review_status"] == "rejected") for r in negatives)
        targeted = sum(r["model_detected_unsupported_claim"] for r in negatives)
        content += '<article><h2>定向反例复核</h2><p>针对注入错误拦截 ' + str(blocked) + '/' + str(len(negatives)) + '；模型按预设标准明确驳回注入错误 ' + str(targeted) + '/' + str(len(negatives)) + '。这只衡量本次定向错误，不能当作总体准确率。</p><ul>'
        for negative in negatives:
            content += '<li>' + esc(negative['case'] + '：' + negative['mutation']) + '；最终 ' + esc(negative['review_status']) + '；明确指出注入错误：' + ('是' if negative['model_detected_unsupported_claim'] else '未达到标准') + '</li>'
        content += '</ul><p>规则拦截与模型判断分别记录。引用是真实原文，不等于原文一定支持解释。原计划已拒绝的样本，不能仅凭再次拒绝就算模型识别成功。</p><a href="counterexample-results.json">完整反例结论与原句</a></article>'
    if result.get("model_comparison"):
        comparison = result["model_comparison"]
        rows = comparison["cases"]
        content += '<article><h2>本地模型对照</h2><p>' + esc(comparison["scope"]) + '</p><p>在相同生产提示与结构下：4B 满足预设判断 ' + str(sum(r["baseline_4b_matched"] for r in rows)) + '/' + str(len(rows)) + '；8B 满足 ' + str(sum(r["matched"] for r in rows)) + '/' + str(len(rows)) + '。</p><ul>'
        for trial in rows:
            verdict = trial.get("judgment", {}).get("verdict", "未完成")
            content += '<li>' + esc(trial["case"]) + '：8B ' + esc(verdict) + '；符合预设判断：' + ('是' if trial['matched'] else '否') + '；' + (esc(trial["failure"]) if trial["failure"] else esc(str(trial["elapsed_s"]) + " 秒")) + '</li>'
        content += '</ul><p>短例对照不代表整段攻略通过，也不能证明对陌生攻略的准确率。</p><a href="model-comparison.json">原始结论与对照范围</a></article>'
    for row in result["cases"]:
        content += '<article><h2>' + esc(row["name"]) + '</h2>'
        if "error" in row:
            content += '<p class="bad">运行失败：' + esc(row["error"]) + '</p></article>'; continue
        content += '<p><strong>计划有限检查：' + ('通过' if row.get('plan_checks_passed') else '未通过') + '；独立复核：' + esc(row['semantic_review_status']) + '</strong></p>'
        content += '<p>' + esc(row["goal"]) + '</p><p>原视频 ' + esc(row["clip"]) + ' 秒 · <a href="' + esc(row["url"]) + '">作者页面</a> · <a href="' + esc(row["directory"]) + '/report.html">展开任务与证据</a></p>'
        content += '<div class="notice"><strong>离线结果核对（' + esc(row['human_review'].get('author', '未注明来源')) + '）：</strong><ul>' + ''.join('<li>' + esc(v) + '</li>' for v in row['human_review']['findings']) + '</ul></div>'
        content += '<ol>' + ''.join('<li>' + esc(s["title"]) + ('<small>待核验：' + esc('；'.join(s["uncertainties"])) + '</small>' if s["uncertainties"] else '') + '</li>' for s in row["steps"]) + '</ol>'
        content += '<details><summary>查看 ' + str(len(row["checks"])) + ' 项选定断言</summary><ul>'
        content += ''.join('<li class="' + ('good' if c["passed"] else 'bad') + '">' + ('通过' if c["passed"] else '未通过') + ' · ' + esc(c["name"]) + '</li>' for c in row["checks"]) + '</ul></details>'
        content += '<p>本轮已解析并保存的模型调用 ' + str(row["model_calls"]) + ' 次，这些调用累计 ' + str(row["model_seconds"]) + ' 秒。精确识别锚点数：0；坐标、图层及玩家解锁状态仍未知。</p></article>'
    content += '<article><h2>仍然缺少</h2><ul><li>稳定的锚点地图定位与图层/坐标校准。</li><li>复杂转写、条件指令、指代和跨片段任务的理解。</li><li>无文字地形、机关与物体的可靠识别。</li><li>受控执行适配器，以及实机成功、暂停、失焦、停止的验收。</li></ul></article>'
    css = 'body{font:16px/1.7 "Segoe UI","Microsoft YaHei",sans-serif;background:#edf2f5;color:#173542;margin:0}main{max-width:1040px;margin:auto;padding:36px 24px}h1{font-size:32px}h2{font-size:22px}article{background:white;border:1px solid #d8e2e7;border-radius:14px;margin:20px 0;padding:24px}.notice{background:#fff0ce;padding:18px;border-radius:8px}a{color:#146477}li{margin:7px 0}small{display:block;color:#776445}.good{color:#26734d}.bad{color:#a13728}summary{cursor:pointer;font-weight:600}'
    (base / 'comparison.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>真实攻略离线回归</title><style>' + css + '</style><main>' + content + '</main></html>', encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--suffix', default='v6')
    a = p.parse_args(); base = a.manifest.resolve().parent
    cases = json.loads(a.manifest.read_text(encoding='utf-8'))['cases']
    if not re.fullmatch(r'[A-Za-z0-9_-]+', a.suffix) or any(not re.fullmatch(r'[A-Za-z0-9_-]+', c['id']) for c in cases):
        raise ValueError('invalid case identifier')
    result = {'scope': '开发回归样本的有限断言，不是整体准确率或实机测试', 'execution_attempted': False, 'cases': []}
    for case in cases:
        try:
            row = evaluate_case(case, base / (case['id'] + '-' + a.suffix))
        except (OSError, ValueError, KeyError) as e:
            row = {'id': case['id'], 'name': case['name'], 'error': str(e), 'passed_selected_checks': False}
        result['cases'].append(row)
    counterexamples = base / 'counterexample-results.json'
    if counterexamples.is_file():
        result['counterexamples'] = json.loads(counterexamples.read_text(encoding='utf-8'))
    comparison = base / 'model-comparison.json'
    if comparison.is_file():
        result['model_comparison'] = json.loads(comparison.read_text(encoding='utf-8'))
    dump(result, base / 'evaluation.json'); write_comparison(result, base)
    print(json.dumps({'passed': sum(r['passed_selected_checks'] for r in result['cases']), 'total': len(cases), 'report': str(base / 'comparison.html')}, ensure_ascii=False))
    return 0 if all(r['passed_selected_checks'] for r in result['cases']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
