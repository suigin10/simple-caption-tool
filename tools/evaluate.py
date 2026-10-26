"""Local-only integration check. Does not upload images. Synthetic test is not an NSFW benchmark."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from captioner.core import Settings, atomic_write, render
from captioner.runtime import LocalRuntime, PROMPT_VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", choices=["qwen4b", "joy8b"], required=True)
    parser.add_argument("--gpu-layers", type=int, default=99)
    parser.add_argument("--image", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    image = args.image or args.output / "synthetic-shapes.png"
    if not args.image:
        canvas = Image.new("RGB", (640, 480), "white")
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((55, 100, 230, 300), fill="red")
        draw.ellipse((340, 110, 530, 300), fill="blue")
        draw.text((90, 350), "RED RECTANGLE     BLUE CIRCLE", fill="black", font_size=24)
        canvas.save(image)
    runtime = LocalRuntime(args.cache)
    report = {"model": args.model, "gpu_layers": args.gpu_layers, "prompt_version": PROMPT_VERSION,
              "test_image": image.name, "scope": "synthetic smoke test; adult-content quality NOT tested"}
    last_update = [0.0]
    def progress(text):
        if time.monotonic() - last_update[0] > 5 or "取得中" not in text:
            print(text, flush=True)
            last_update[0] = time.monotonic()
    started = time.monotonic()
    try:
        runtime.start(args.model, args.gpu_layers, threading.Event(), progress)
        report["prepare_and_load_seconds"] = round(time.monotonic() - started, 2)
        started = time.monotonic()
        analysis, raw = runtime.analyze(image, 1024)
        report.update({"inference_seconds": round(time.monotonic() - started, 2), "analysis": analysis,
                       "raw": raw, "status": "passed"})
        report["outputs"] = {target + "_" + mode: render(analysis, Settings(target=target, format=mode))
                             for target in ("character", "style") for mode in ("natural", "tags", "mixed")}
        report["gpu_snapshot"] = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader"],
            text=True, creationflags=subprocess.CREATE_NO_WINDOW).strip()
    except Exception as error:
        report.update({"status": "failed", "error": str(error), "raw": getattr(error, "raw", "")})
        print(str(error), flush=True)
    finally:
        runtime.stop()
        atomic_write(args.output / (args.model + "-evaluation.json"), json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in ("analysis", "raw", "outputs")}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
