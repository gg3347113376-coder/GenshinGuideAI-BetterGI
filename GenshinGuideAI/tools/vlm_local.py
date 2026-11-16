"""本地 VLM 复核：用 transformers 跑 Qwen2.5-VL，对证据帧做场景分类。

用法：
  python tools/vlm_local.py --project runs\p002_full_v7.json --samples 8 \
      --model models\Qwen2.5-VL-3B-Instruct --out runs\vlm_local.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROMPT = (
    "你是游戏画面审阅器。请判断这张《原神》截图属于哪种画面，只输出一行 JSON，不要解释、不要复制示例："
    "{\"scene\":\"<从 对话/开放世界/菜单/战斗/读条/其他 中选恰好一个>\","
    "\"subtitle\":<true或false>,\"minimap\":<true或false>,\"confidence\":<0到1>}"
)


def extract_json(text: str) -> dict | None:
    match = re.search(r"\{.*?\}", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--model", default=r"models\Qwen2.5-VL-3B-Instruct")
    parser.add_argument("--out", default="runs/vlm_local.json")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dtype", default="auto")
    parser.add_argument("--max-new-tokens", type=int, default=48)
    parser.add_argument("--max-pixels", type=int, default=262144)
    args = parser.parse_args()

    import torch
    from qwen_vl_utils import process_vision_info
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

    model_path = ROOT / args.model
    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if args.dtype != "auto":
        dtype = getattr(torch, args.dtype)
    else:
        dtype = torch.float16 if device == "cuda" else torch.float32
    started = time.time()
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        str(model_path), torch_dtype=dtype, device_map=device, low_cpu_mem_usage=True
    )
    processor = AutoProcessor.from_pretrained(str(model_path))
    load_s = round(time.time() - started, 1)

    project = json.loads((ROOT / args.project).read_text(encoding="utf-8"))
    picked = []
    for event in project.get("events", []):
        frame = next((v.get("path") for v in event.get("evidence", []) if v.get("path")), None)
        if not frame:
            continue
        path = Path(frame) if Path(frame).is_absolute() else ROOT / frame
        if not path.exists():
            continue
        picked.append((event, path))
        if len(picked) >= args.samples:
            break

    results = []
    for event, path in picked:
        messages = [
            {
                "role": "user",
                "content": [{"type": "image", "image": str(path), "max_pixels": args.max_pixels}, {"type": "text", "text": PROMPT}],
            }
        ]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        images, _ = process_vision_info(messages)
        inputs = processor(text=[text], images=images, return_tensors="pt").to(device)
        start = time.time()
        with torch.no_grad():
            output = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
        latency = round(time.time() - start, 1)
        generated = processor.batch_decode(output[:, inputs["input_ids"].shape[1] :], skip_special_tokens=True)[0]
        parsed = extract_json(generated)
        results.append(
            {
                "t": event["video_time"]["start_s"],
                "type": event["action"]["type"],
                "text": event["action"]["params"].get("text", "")[:30],
                "frame": str(path),
                "raw": generated.strip()[:200],
                "parsed": parsed,
                "latency_s": latency,
            }
        )
        print(json.dumps({"t": results[-1]["t"], "parsed": parsed, "latency_s": latency}, ensure_ascii=False))

    out = {
        "model": str(model_path),
        "device": device,
        "load_s": load_s,
        "samples": len(results),
        "results": results,
    }
    path = ROOT / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"load_s": load_s, "samples": len(results), "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
