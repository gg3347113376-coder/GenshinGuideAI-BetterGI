"""Ollama VLM 客户端：对关键帧做语义分类/描述。"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3-vl:4b"


class OllamaVLM:
    def __init__(self, model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST, think: bool | None = None, context_size: int = 8192, gpu_layers: int | None = None) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.think = think
        self.context_size = context_size
        self.gpu_layers = gpu_layers

    def _post(self, path: str, payload: dict, timeout: int = 300) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.host + path, data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def available(self) -> tuple[bool, str]:
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=10) as response:
                tags = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            return False, f"服务不可用：{exc}"
        names = [m.get("name", "") for m in tags.get("models", [])]
        if any(name.startswith(self.model) for name in names):
            return True, "ok"
        return False, f"缺少模型 {self.model}；已有：{names[:5]}"

    def structured(self, prompt: str, schema: dict, images=(), timeout: int = 180,
                   max_tokens: int = 3072) -> dict:
        """Return the raw response so callers can persist it before parsing."""
        return self._post("/api/chat", {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt,
                          "images": [base64.b64encode(Path(p).read_bytes()).decode("ascii") for p in images]}],
            "stream": False, "format": schema,
            **({"think": self.think} if self.think is not None else {}),
            "options": {"temperature": 0, "num_ctx": self.context_size, "num_predict": max_tokens,
                        **({"num_gpu": self.gpu_layers} if self.gpu_layers is not None else {})},
            "keep_alive": "5m",
        }, timeout=timeout)

    def describe(self, image_path: str | Path, prompt: str, timeout: int = 300) -> str:
        data = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [data],
            "stream": False,
            "options": {"temperature": 0, **({"num_gpu": self.gpu_layers} if self.gpu_layers is not None else {})},
        }
        result = self._post("/api/generate", payload, timeout=timeout)
        return str(result.get("response", "")).strip()


SCENE_PROMPT = """你是原神游戏画面分类器。看这张截图，只输出一行 JSON：
{"scene": "dialogue|combat|travel|menu|cutscene", "confidence": 0到1的小数, "reason": "不超过20字"}
判定标准：
- dialogue：画面底部有对话字幕或角色对话特写
- combat：有敌人血条、伤害数字或战斗特效
- travel：开放世界跑图/探索
- menu：菜单、背包、任务面板、结算界面
- cutscene：过场动画（无 HUD 或黑边）
不要输出 JSON 以外的任何内容。"""


def classify_scene(vlm: OllamaVLM, image_path: str | Path) -> dict:
    text = vlm.describe(image_path, SCENE_PROMPT)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            payload = json.loads(text[start : end + 1])
            return {
                "scene": str(payload.get("scene", "unknown")),
                "confidence": float(payload.get("confidence", 0)),
                "reason": str(payload.get("reason", "")),
                "raw": text,
            }
        except (ValueError, TypeError):
            pass
    return {"scene": "unknown", "confidence": 0.0, "reason": "", "raw": text}
