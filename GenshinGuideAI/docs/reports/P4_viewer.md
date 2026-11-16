# 证据查看器（最小人工纠正界面）

- 工具：`tools/build_viewer.py`
- 产物：`runs/viewer_p002/index.html` + `frames/`（196 条事件、196 张证据帧）
- 截图：`docs/reports/viewer_p002.png`

## 一、功能

| 功能 | 说明 |
|---|---|
| 事件列表 | 序号、时间、类型、说话人、文本摘要、可疑标记、复核状态、是否有证据帧 |
| 详情面板 | 证据帧大图 + 说话人/文本/备注编辑 + 置信度与证据说明 |
| 复核操作 | 「确认无误」「保存修正」「驳回」三种结论 |
| 导出 | 一键导出复核 CSV（UTF-8 BOM，列名与 `apply_review.py` 完全一致） |
| 深链 | `index.html?i=7` 直接选中第 7 条，便于分享定位 |

## 二、使用流程

```powershell
# 1. 生成查看器
python tools\build_viewer.py runs\p002_full_v7.json --out runs\viewer_p002

# 2. 本地打开（任选）
start runs\viewer_p002\index.html
# 或起一个本地服务
python -m http.server 8899 --directory runs\viewer_p002

# 3. 在页面里复核并「导出复核 CSV」

# 4. 把导出的 CSV 回填项目
python tools\apply_review.py --project runs\p002_full_v7.json `
  --csv downloads\review.csv --out runs\p002_reviewed.json
```

## 三、验证

- 生成结果：`{"events": 196, "frames_copied": 196}`
- 本地 HTTP 200，UTF-8 解码后包含页面标题与事件文本
- 无头 Edge 截图（`viewer_p002.png`）：列表、证据帧、字幕、编辑框均正常
- 单元测试：2 个（正常构建并对证据帧嵌入；缺帧项目也能生成）

## 四、限制

- 纯前端，无后端；复核结果靠导出 CSV 再回填；
- 没有多人协作与冲突解决；
- 证据帧是复制副本，项目更新后需要重新生成。
