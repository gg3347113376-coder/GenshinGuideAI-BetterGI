# VLM 接入尝试（客户端就绪，模型安装被网络阻塞）

- 日期：2026-11-06
- 客户端：`src/ggai/vlm.py`（Ollama HTTP API）
- 复核脚本：`tools/vlm_check.py`
- 测试：`tests/test_vlm.py`（3 个，解析逻辑）
- 结论：**Ollama 与 qwen3-vl:4b 未能安装**，原因是下载网络不可用；客户端代码与解析逻辑已完成并通过测试

## 一、已实现

| 组件 | 说明 |
|---|---|
| `OllamaVLM.available()` | 检查服务与模型是否存在，返回明确错误信息 |
| `OllamaVLM.describe()` | 图片 base64 → `/api/generate`，temperature=0 |
| `SCENE_PROMPT` | 场景分类提示词（dialogue/combat/travel/menu/cutscene） |
| `classify_scene()` | 从模型输出中提取并校验 JSON，失败返回 unknown |
| `tools/vlm_check.py` | 抽样关键帧 → 分类 → 与事件类型对照 → 输出准确率与逐条结果 |

## 二、安装尝试记录

| 来源 | 结果 |
|---|---|
| ollama.com 安装包（1.69GB） | 两次连接被重置，未生成文件 |
| GitHub Release `ollama-windows-amd64.zip`（1.54GB） | 约 **0.02 MB/s**，10 分钟仅 15.5MB |
| ghproxy.net 加速 | 20 秒 0 字节 |
| mirror.ghproxy.com | 20 秒 0 字节 |
| gh-proxy.com | 20 秒 1.2MB（不可用） |

按此速率，1.5GB 需要 20+ 小时，且随时可能中断，判定为**当前网络不可行**。

## 三、网络恢复后可直接执行的步骤

```powershell
# 1) 安装 Ollama（任选其一）
winget install Ollama.Ollama
# 或下载 OllamaSetup.exe 后静默安装：
# .\OllamaSetup.exe /VERYSILENT /NORESTART

# 2) 拉取模型（约 3GB）
ollama pull qwen3-vl:4b

# 3) 验证服务与模型
curl http://127.0.0.1:11434/api/tags

# 4) 跑关键帧复核（12 个样本）
python tools\vlm_check.py --project runs\p002_full_v7.json --samples 12
```

## 四、客户端验证（不依赖网络）

3 个单元测试覆盖：

1. 严格 JSON 输出解析；
2. 带前后说明文字的 JSON 提取；
3. 无法解析时返回 `unknown`。

`vlm_check.py` 在模型缺失时会输出明确提示（`缺少模型 qwen3-vl:4b`），不会静默失败。

## 五、备选方案（网络仍不可用时）

1. 用 ModelScope 的轻量 VLM（如 Qwen2.5-VL-3B）配合 llama.cpp；
2. 先做纯规则的场景分类（HUD 存在性 + 字幕检测），VLM 仅作离线复核；
3. 用云端 API（需要 Key 与费用）。
