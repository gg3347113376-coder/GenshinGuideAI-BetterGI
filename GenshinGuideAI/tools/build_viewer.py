r"""生成方向一的本地证据查看器（单文件 HTML + 证据帧目录）。

用法：
  python tools/build_viewer.py runs\p002_full_v7.json --out runs\viewer_p002
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>GenshinGuideAI 证据查看器</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background: #101418; color: #e6edf3; }
  header { padding: 12px 16px; background: #161b22; border-bottom: 1px solid #30363d; display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
  header h1 { font-size: 16px; margin: 0; }
  .stats { color: #8b949e; font-size: 13px; }
  main { display: grid; grid-template-columns: 420px 1fr; height: calc(100vh - 58px); }
  #list { overflow-y: auto; border-right: 1px solid #30363d; }
  #track { display: block; width: 420px; height: 260px; background: #0d1117; border-bottom: 1px solid #30363d; }
  .item { padding: 8px 12px; border-bottom: 1px solid #21262d; cursor: pointer; font-size: 13px; }
  .item:hover { background: #1f2630; }
  .item.active { background: #1f6feb33; border-left: 3px solid #58a6ff; }
  .meta { color: #8b949e; font-size: 12px; }
  .flag { color: #f0883e; font-size: 12px; }
  #detail { padding: 16px; overflow-y: auto; }
  #frame { max-width: 100%; border: 1px solid #30363d; border-radius: 6px; background: #000; }
  textarea, input { width: 100%; background: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 4px; padding: 6px; }
  .row { margin: 8px 0; }
  .btns { display: flex; gap: 8px; margin: 12px 0; flex-wrap: wrap; }
  button { background: #21262d; color: #e6edf3; border: 1px solid #30363d; border-radius: 4px; padding: 6px 10px; cursor: pointer; }
  button.ok { border-color: #2ea043; color: #3fb950; }
  button.bad { border-color: #da3633; color: #f85149; }
  .empty { color: #8b949e; padding: 24px; }
</style>
</head>
<body>
<header>
  <h1>GenshinGuideAI 证据查看器</h1>
  <span class="stats" id="stats"></span>
  <span style="flex:1"></span>
  <button onclick="exportCsv()">导出复核 CSV</button>
</header>
<main>
  <div id="list"><canvas id="track" width="420" height="260"></canvas><div id="items"></div></div>
  <div id="detail"><div class="empty">← 从左侧选择一条事件</div></div>
</main>
<script>
const DATA = %DATA%;
const FRAMES = %FRAMES%;
document.getElementById('stats').textContent =
  `事件 ${DATA.length} 条 · 待复核 ${DATA.filter(e => e.status === 'pending').length} · 已确认 ${DATA.filter(e => e.status === 'confirmed').length} · 已修正 ${DATA.filter(e => e.status === 'corrected').length}`;
let current = -1;

function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }

function renderList() {
  const list = document.getElementById('items');
  list.innerHTML = DATA.map((e, i) => `
    <div class="item" id="item${i}" onclick="select(${i})">
      <div><b>#${i + 1}</b> [${esc(e.t)}s] ${esc(e.type)} · ${esc(e.speaker || '—')}</div>
      <div>${esc((e.text || '').slice(0, 42))}</div>
      ${e.flags.length ? `<div class="flag">${esc(e.flags.join(' / '))}</div>` : ''}
      <div class="meta">状态：${esc(e.status)}${FRAMES[i] ? ' · 有证据帧' : ' · 无帧'}${e.x != null ? ` · (${e.x}, ${e.y})` : ''}</div>
    </div>`).join('');
}

function select(i) {
  current = i;
  document.querySelectorAll('.item').forEach(el => el.classList.remove('active'));
  document.getElementById('item' + i).classList.add('active');
  const e = DATA[i];
  const frame = FRAMES[i] ? `<img id="frame" src="${FRAMES[i]}">` : '<div class="empty">该事件没有证据帧</div>';
  document.getElementById('detail').innerHTML = `
    <h2 style="font-size:15px">#${i + 1} · ${esc(e.type)} · ${esc(e.t)}s</h2>
    <div class="row">${frame}</div>
    <div class="row"><label>说话人<br><input id="spk" value="${esc(e.speaker || '')}"></label></div>
    <div class="row"><label>文本<br><textarea id="txt" rows="4">${esc(e.text || '')}</textarea></label></div>
    <div class="row"><label>复核备注<br><input id="note" value="${esc(e.note || '')}"></label></div>
    <div class="btns">
      <button class="ok" onclick="verdict('confirmed')">确认无误</button>
      <button onclick="verdict('corrected')">保存修正</button>
      <button class="bad" onclick="verdict('rejected')">驳回</button>
    </div>
    <div class="meta">置信度 ${esc(e.conf)} · 证据：${esc((e.evidence || []).join(' | '))}</div>
    ${e.x != null ? `<div class="meta">坐标：(${e.x}, ${e.y}) · 方法 ${esc(e.pmethod)} · 置信度 ${esc(e.pconf)}</div>` : ''}`;
}

function verdict(kind) {
  if (current < 0) return;
  const e = DATA[current];
  const spk = document.getElementById('spk').value.trim();
  const txt = document.getElementById('txt').value.trim();
  const note = document.getElementById('note').value.trim();
  if (kind === 'corrected' && !txt) { alert('修正需要填写文本'); return; }
  e.status = kind;
  e.note = note;
  e.reviewed_speaker = spk;
  e.reviewed_text = txt;
  renderList();
  select(current);
}

function exportCsv() {
  const rows = [['序号', '人工结论', '修正文本', '修正说话人', '复核备注']];
  DATA.forEach((e, i) => {
    if (e.status === 'pending') return;
    rows.push([i + 1, e.status, e.reviewed_text || (e.status === 'corrected' ? e.text : ''), e.reviewed_speaker || (e.status === 'corrected' ? e.speaker : ''), e.note || '']);
  });
  const csv = rows.map(r => r.map(x => `"${String(x == null ? '' : x).replace(/"/g, '""')}"`).join(',')).join('\\r\\n');
  const blob = new Blob(['\\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'review.csv';
  a.click();
}

function drawTrack() {
  const c = document.getElementById('track');
  if (!c) return;
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, c.width, c.height);
  const pts = DATA.filter(e => e.x != null);
  if (pts.length < 2) {
    ctx.fillStyle = '#8b949e'; ctx.font = '12px sans-serif';
    ctx.fillText('无坐标数据', 12, 24);
    return;
  }
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const pad = 24, w = c.width - 2 * pad, h = c.height - 2 * pad;
  const sx = v => pad + (maxX === minX ? w / 2 : (v - minX) / (maxX - minX) * w);
  const sy = v => pad + (maxY === minY ? h / 2 : (maxY - v) / (maxY - minY) * h);
  ctx.strokeStyle = '#30363d';
  ctx.strokeRect(pad, pad, w, h);
  ctx.beginPath();
  pts.forEach((p, k) => {
    const X = sx(p.x), Y = sy(p.y);
    if (k === 0) ctx.moveTo(X, Y); else ctx.lineTo(X, Y);
  });
  ctx.strokeStyle = '#58a6ff';
  ctx.lineWidth = 1.5;
  ctx.stroke();
  pts.forEach(p => {
    const X = sx(p.x), Y = sy(p.y);
    ctx.beginPath();
    ctx.arc(X, Y, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = (p.pconf != null && p.pconf < 0.35) ? '#f0883e' : '#3fb950';
    ctx.fill();
  });
  ctx.fillStyle = '#8b949e';
  ctx.font = '11px sans-serif';
  ctx.fillText(`${pts.length} 点 · x ${minX.toFixed(0)}..${maxX.toFixed(0)} · y ${minY.toFixed(0)}..${maxY.toFixed(0)}`, pad, 14);
}

renderList();
drawTrack();
const params = new URLSearchParams(location.search);
const sel = parseInt(params.get('i'));
if (!isNaN(sel) && sel >= 1 && sel <= DATA.length) select(sel - 1);
</script>
</body>
</html>
"""


def build(project_path: Path, out_dir: Path) -> dict:
    project = json.loads(project_path.read_text(encoding="utf-8"))
    events = project.get("events", [])
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    frames = []
    copied = 0
    for index, event in enumerate(events):
        params = event.get("action", {}).get("params", {})
        review = event.get("review", {}) or {}
        evidence_paths = [v.get("path") for v in event.get("evidence", []) if v.get("path")]
        frame_rel = None
        for path in evidence_paths:
            source = Path(path)
            if not source.is_absolute():
                source = ROOT / source
            if source.exists():
                target = frames_dir / f"evt_{index + 1:04d}{source.suffix.lower()}"
                shutil.copyfile(source, target)
                frame_rel = f"frames/{target.name}"
                copied += 1
                break
        flags = []
        if float(event.get("confidence", 0)) < 0.6:
            flags.append("低置信")
        text = params.get("text") or params.get("quest_text") or ""
        if len(text) < 5:
            flags.append("文本过短")
        if not evidence_paths:
            flags.append("无证据")
        rows.append(
            {
                "i": index + 1,
                "t": event.get("video_time", {}).get("start_s"),
                "type": event.get("action", {}).get("type"),
                "speaker": params.get("speaker", ""),
                "text": text,
                "conf": event.get("confidence"),
                "status": review.get("status", "pending"),
                "note": (review.get("diff") or {}).get("note", "") if isinstance(review.get("diff"), dict) else "",
                "flags": flags,
                "evidence": evidence_paths,
                "x": (event.get("position") or {}).get("map", {}).get("x"),
                "y": (event.get("position") or {}).get("map", {}).get("y"),
                "pmethod": (event.get("position") or {}).get("map", {}).get("method", ""),
                "pconf": (event.get("position") or {}).get("map", {}).get("confidence"),
            }
        )
        frames.append(frame_rel)

    html = HTML_TEMPLATE.replace("%DATA%", json.dumps(rows, ensure_ascii=False)).replace(
        "%FRAMES%", json.dumps(frames, ensure_ascii=False)
    )
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    return {"events": len(events), "frames_copied": copied, "out": str(out_dir / "index.html")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--out", default="runs/viewer")
    args = parser.parse_args()
    result = build(Path(args.project), ROOT / args.out)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
