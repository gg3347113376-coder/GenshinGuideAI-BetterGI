"""Local, escaped HTML viewer for evidence-linked task plans."""
import html
import json
from pathlib import Path

from .planning import catalog


def write_report(project: dict, path: Path) -> None:
    esc = lambda value: html.escape(str(value), quote=True)
    plan = project["task_plan"]
    evidence = {e["id"]: e for e in project["evidence_index"]}
    names = {a["id"]: a["name"] for a in catalog()["actions"]}
    def bullets(values):
        return "<ul>" + "".join("<li>" + esc(v) + "</li>" for v in values) + "</ul>"
    def evidence_card(item):
        time = item["time"]
        title = f"{item['id']} · {time['start_s']:.2f}–{time['end_s']:.2f} 秒"
        body = ('<a href="' + esc(item["path"]) + '"><img loading="lazy" src="' + esc(item["path"]) + '" alt="' + esc(title) + '"></a>') if item["kind"] == "frame" else ('<blockquote>' + esc(item["text"]) + '</blockquote>')
        return '<figure><figcaption>' + esc(title) + '</figcaption>' + body + '</figure>'
    targets = {t["id"]: t for t in project.get("target_registry", {}).get("entities", [])}
    cards = []
    for i, step in enumerate(plan["steps"], 1):
        status = "参数或前置能力未齐" if step["status"] == "blocked" else "待人工复核"
        body = f'<article id="{esc(step["id"])}"><div class="row"><span class="number">{i:02}</span><h2>{esc(step["title"])}</h2><span class="badge">{status}</span></div>'
        body += '<p>' + esc(step["intent"]) + '</p><p class="meta">动作：' + esc(names[step["action_id"]]) + ' · 依赖：' + esc(", ".join(step["depends_on"]) or "无") + ' · 模型自评分：' + esc(step["confidence"]) + '</p>'
        body += '<div class="columns"><section><h3>前置检查（均未检查）</h3>' + bullets([c["description"] for c in step["preconditions"]]) + '</section><section><h3>成功判据（均未验证）</h3><p>' + esc(step["expected_result"]["text"]) + '</p>' + bullets([c["description"] for c in step["expected_result"]["checks"]]) + '</section></div>'
        if step.get("target_ref") in targets:
            target = targets[step["target_ref"]]
            body += '<p class="blocked"><strong>绑定目标：</strong>' + esc(target["label"]) + '<br>' + esc(target["id"] + ' · 类型 ' + target["kind"] + ' · 状态 ' + target["resolution"]) + '<br>具体身份、坐标与当前玩家解锁状态均未核实。</p>'
        if step.get("instruction_evidence_ids"):
            body += '<p class="meta">动作指令依据：' + esc('、'.join(step['instruction_evidence_ids'])) + '；对象来源与动作指令分别记录。</p>'
        if step["blockers"]:
            body += '<div class="blocked"><strong>尚缺</strong>' + bullets([b["detail"] for b in step["blockers"]]) + '</div>'
        if step["uncertainties"]:
            body += '<h3>尚未核实的信息</h3>' + bullets(step["uncertainties"])
        body += '<details><summary>查看动作参数</summary><pre>' + esc(json.dumps(step["params"], ensure_ascii=False, indent=2)) + '</pre></details>'
        body += '<details open><summary>查看原始证据</summary><div class="evidence">' + ''.join(evidence_card(evidence[eid]) for eid in step["evidence_ids"]) + '</div></details><p class="meta">执行结果：未执行；审核状态：待复核。</p></article>'
        cards.append(body)
    total_time = sum(r["elapsed_s"] for r in project["analysis_runs"])
    source = project["sources"][0]
    notes = source.get("notes", "")
    source_url = notes.split("source_url=", 1)[-1].split(";", 1)[0] if "source_url=" in notes else ""
    link = '<a href="' + esc(source_url) + '">原攻略页面</a>' if source_url.startswith(("https://", "http://")) else ''
    nav = '<a href="project.json">完整协议 JSON</a><a href="task-plan.json">任务计划</a><a href="model-draft.json">模型原始计划</a><a href="validation.json">验证记录</a><a href="action-catalog.json">动作目录</a>'
    if (path.parent / "plan-order.json").is_file():
        nav += '<a href="plan-order.json">指令时间与排序记录</a>'
    if (path.parent / "observations.json").is_file():
        nav += '<a href="observations.json">画面观察</a>'
    if "grounding" in project:
        nav += '<a href="grounding.json">文字与锚点核验记录</a>'
    if "semantic_review" in project:
        nav += '<a href="targets.json">目标绑定记录</a><a href="semantic-review.json">独立复核记录</a>'
    if (path.parent / "previous-project.json").is_file():
        nav += '<a href="previous-project.json">复核前计划</a><a href="review-input.json">复核依据</a>'
    banner = '<header><p class="eyebrow">GENSHIN GUIDE AI · PHASE 01</p><h1>' + esc(project["project"]["name"]) + '</h1><p>' + esc(plan["goal"]) + '</p><p class="notice">仅生成计划 · 未操作游戏 · 所有步骤待人工复核</p>'
    banner += '<div class="stats"><div><b>' + str(len(plan["steps"])) + '</b><span>任务步骤</span></div><div><b>' + str(len(evidence)) + '</b><span>本地证据</span></div><div><b>' + str(len(project["analysis_runs"])) + '</b><span>Qwen 调用</span></div><div><b>' + f'{total_time:.1f}s' + '</b><span>Qwen 累计耗时</span></div></div><nav>' + nav + '</nav></header>'
    intro = '<section class="intro"><p>' + link + ' · 片段 ' + esc(project["segments"][0]["start_s"]) + '–' + esc(project["segments"][0]["end_s"]) + ' 秒。画面来自攻略作者，不能证明用户当前游戏状态。</p><p>原始转写保留错字；图中文字与模型描述需要对照。证据链接能追溯判断来源，不代表判断已经正确。</p><p>' + esc(plan["confidence_note"]) + '</p></section>'
    grounding_section = ""
    if "grounding" in project:
        g = project["grounding"]
        status = "发现语义问题，拒绝用于后续执行" if g["plan_review"]["status"] == "rejected" else "规则未发现上述误判，仍待人工复核"
        grounding_section = '<article><h2>文字与目标核验</h2><p>' + esc(status) + '</p>'
        grounding_section += bullets([i["step_id"] + '：' + i["detail"] for i in g["plan_review"]["issues"]])
        for f in g["frames"]:
            grounding_section += '<details><summary>' + esc(f["evidence_id"]) + ' · OCR 文字分类</summary>'
            grounding_section += evidence_card(evidence[f["evidence_id"]])
            grounding_section += bullets([('仅供地名候选核对' if r["role"] == 'map_region' else ('任务文字候选' if r["eligible"] else '不送入任务模型')) + '：' + r["text"] + ' — ' + r["reason"] for r in f["rows"]]) + '</details>'
        grounding_section += '<h3>语音原文与候选（原文未修改）</h3>'
        for t in g["transcripts"]:
            grounding_section += '<details><summary>' + esc(t["evidence_id"] + ' · ' + t["original"]) + '</summary><p>第二次识别：' + esc(t["alternative"] or '未复听') + ('（跨句上下文，未送入本句任务证据）' if t["status"] == 'context_only' else '') + '</p>'
            grounding_section += bullets(['画面支持词：' + c["term"] + '（' + c["frame_id"] + '）' for c in t["corroborated_terms"]])
            grounding_section += bullets(['拼字候选，尚未替换：' + c["original_fragment"] + ' → ' + c["candidate"] + '（' + c["frame_id"] + '）' for c in t["lexical_candidates"]]) + '</details>'
        grounding_section += '<h3>锚点识别边界</h3><p>类型、区域、具体锚点和用户解锁状态分别记录。这里的候选都来自攻略视频，不能直接用于定位或传送。</p>'
        for a in g["anchors"]:
            if a["identity_status"] == "not_identified":
                continue
            grounding_section += '<p>' + esc(a["frame_id"] + '：' + a["anchor_type"] + '；区域 ' + '/'.join(a["region_labels"]) + '；候选 ' + str(len(a["candidates"])) + ' 个；精确坐标未知，当前玩家解锁状态未知。') + '</p>'
        grounding_section += '</article>'
    if "semantic_review" in project:
        review = project["semantic_review"]
        labels = {"supported_with_unknowns": "任务意图获得证据支持；具体目标仍待定位", "needs_review": "语义仍有疑点，需要复核", "rejected": "复核发现问题，不能采用本计划", "failed": "复核未完成，不能采用本计划"}
        models = project["project"]["model_versions"]
        relation = "规划与复核使用相同模型权重，不等于不同模型交叉验证" if models.get("task_understanding") == models.get("semantic_review") else "规划与复核使用不同模型，分别保留原始请求和回复"
        section = '<article><h2>独立语义复核</h2><p><strong>' + esc(labels[review["status"]]) + '</strong></p><p>通过无历史对话的模型调用核对原始转写、复听与界面文字；新版本分别复核总目标与各步骤，对象断言和行动意图分别判断；遗漏指令另行检查。' + esc(relation) + '；此结论不批准游戏执行。</p>'
        section += bullets([i["step_id"] + '：' + i["detail"] for i in review["issues"]])
        if review["failure"]:
            section += '<p>' + esc(review["failure"]) + '</p>'
        if review["result"]:
            for item in [{"step_id": "最终目标", **review["result"]["goal"]}, *review["result"]["steps"]]:
                section += '<details><summary>' + esc(item["step_id"] + ' · ' + item["verdict"]) + '</summary><p>' + esc(item["reason"]) + '</p>' + bullets([c["unit_id"] + '：“' + c["quote"] + '”' for c in item["citations"]])
                item_key = "goal" if item["step_id"] == "最终目标" else item["step_id"]
                item_run = review.get("item_run_ids", {}).get(item_key)
                if item_run:
                    item_trace = next(t for t in project["analysis_runs"] if t["id"] == item_run)
                    section += '<p><a href="' + esc(item_trace['request_path']) + '">本项复核输入</a> · <a href="' + esc(item_trace['response_path']) + '">本项原始回复</a></p>'
                section += '</details>'
            coverage_id = review.get("item_run_ids", {}).get("coverage")
            if coverage_id:
                coverage = next(t for t in project["analysis_runs"] if t["id"] == coverage_id)
                section += '<p>遗漏指令复核：<a href="' + esc(coverage["request_path"]) + '">输入</a> · <a href="' + esc(coverage["response_path"]) + '">原始回复</a></p>'
            trace = next(t for t in project["analysis_runs"] if t["id"] == review["analysis_run_id"])
            section += '<p><a href="' + esc(trace["request_path"]) + '">复核输入</a> · <a href="' + esc(trace["response_path"]) + '">模型原始回复</a></p>'
        section += '<h3>目标候选与未解信息</h3>' + bullets([t["id"] + ' · ' + t["kind"] + ' · ' + t["label"] + ('；目录候选 ' + str(len(t["candidate_points"])) + ' 个' if t["candidate_points"] else '') for t in targets.values()]) + '</article>'
        grounding_section = section + grounding_section
    visual_section = ""
    observations_path = path.parent / "observations.json"
    if observations_path.is_file():
        rows = json.loads(observations_path.read_text(encoding="utf-8"))["observations"]
        visual_section = '<article><h2>模型如何理解画面</h2><p>以下是原始模型描述，可能误读界面或解说贴图。高自评分也不代表正确。</p>'
        for row in rows:
            item = evidence.get(row["evidence_id"])
            if item:
                visual_section += '<details><summary>' + esc(row["evidence_id"]) + ' · ' + esc(item["time"]["start_s"]) + ' 秒 · 自评分 ' + esc(row["confidence"]) + '</summary>'
                visual_section += bullets(row["observations"]) + '<p>识别文字：' + esc(' / '.join(row["visible_text"])) + '</p>' + evidence_card(item) + '</details>'
        visual_section += '</article>'
    review_section = ""
    review_path = path.parent / "quality-review.json"
    if review_path.is_file():
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review_section = '<article><h2>本次结果核对</h2><p>' + esc(review["scope"]) + '</p>' + bullets(review["findings"]) + '</article>'
    tail = '<article><h2>计划级疑点</h2>' + bullets(plan["uncertainties"]) + '<p>本轮未验证：当前任务状态、锚点解锁、地图坐标和层、路线可通行性、战斗队伍适配，以及暂停 / 失焦 / 停止的实机行为。</p><p>后续需要把目录动作接到受控执行适配器，并用执行后的新画面判定完成。</p></article>'
    css = """*{box-sizing:border-box}body{margin:0;background:#eef2f4;color:#182c38;font:16px/1.65 'Segoe UI','Microsoft YaHei',sans-serif}main{max-width:1180px;margin:auto;padding:32px 24px 64px}header{background:#133e4b;color:#fff;border-radius:18px;padding:32px}h1{font-size:30px;margin:8px 0}h2{font-size:21px;margin:0;flex:1}h3{font-size:15px;margin:8px 0}.eyebrow{letter-spacing:2px;font-size:12px;color:#a8d8dc}.notice{color:#ffdb94;font-weight:600}.stats{display:flex;gap:38px;flex-wrap:wrap;margin:20px 0}.stats b{display:block;font-size:27px}.stats span{font-size:13px;color:#b9d2d8}nav{display:flex;flex-wrap:wrap;gap:16px}nav a{color:#d4f1f3;font-size:14px}.intro{padding:16px 4px;font-size:14px}article{background:#fff;padding:26px;border:1px solid #dce4e8;border-radius:14px;margin:18px 0}.row{display:flex;gap:14px;align-items:center;flex-wrap:wrap}.number{font-size:22px;color:#527785}.badge{background:#fff0ce;color:#77541c;padding:5px 12px;border-radius:18px;font-size:12px}.meta{color:#637682;font-size:13px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:28px}ul{padding-left:22px}li{margin:4px 0}.blocked{border-left:4px solid #cc9b40;background:#fff8e9;padding:12px 18px;margin:14px 0}details{margin:14px 0}summary{cursor:pointer;color:#176578;font-weight:600}.evidence{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:12px}figure{margin:0;background:#f3f6f7;padding:12px;border-radius:8px}figcaption{font-size:12px;color:#637682;margin-bottom:8px}img{max-width:100%;border-radius:5px}blockquote{margin:0;border-left:3px solid #95acb5;padding-left:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;background:#f3f6f7;padding:14px}a{color:#146277}@media(max-width:740px){.columns,.evidence{grid-template-columns:1fr}main{padding:12px}header{padding:22px}article{padding:18px}}"""
    document = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>' + esc(project["project"]["name"]) + '</title><style>' + css + '</style><main>' + banner + intro + grounding_section + ''.join(cards) + review_section + visual_section + tail + '</main></html>'
    path.write_text(document, encoding="utf-8")
