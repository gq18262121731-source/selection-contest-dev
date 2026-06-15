from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import cv2
import numpy as np
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"


def keypoint_quality(result: Any) -> dict[str, float]:
    if result.boxes is None or result.keypoints is None or len(result.boxes) == 0:
        return {"people": 0.0, "mean_kp_conf": 0.0, "visible_ratio": 0.0}
    kps = result.keypoints.data.detach().cpu().numpy()
    scores = kps[:, :, 2] if kps.shape[-1] >= 3 else np.zeros(kps.shape[:2], dtype=np.float32)
    visible = scores >= 0.2
    return {
        "people": float(len(kps)),
        "mean_kp_conf": float(scores.mean()) if scores.size else 0.0,
        "visible_ratio": float(visible.mean()) if visible.size else 0.0,
    }


def sample_frames(source: Path, limit_frames: int, stride: int) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open source: {source}")
    idx = 0
    while len(frames) < limit_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            frames.append(frame)
        idx += 1
    cap.release()
    return frames


def evaluate_model(model_path: str, frames: list[np.ndarray], imgsz: int, conf: float) -> dict[str, Any]:
    model = YOLO(model_path)
    latencies: list[float] = []
    people_counts: list[float] = []
    kp_conf: list[float] = []
    visible_ratios: list[float] = []
    for frame in frames:
        started = time.perf_counter()
        result = model.predict(frame, verbose=False, imgsz=imgsz, conf=conf, max_det=10)[0]
        latencies.append((time.perf_counter() - started) * 1000)
        quality = keypoint_quality(result)
        people_counts.append(quality["people"])
        kp_conf.append(quality["mean_kp_conf"])
        visible_ratios.append(quality["visible_ratio"])
    avg_latency = mean(latencies) if latencies else 0.0
    return {
        "model": model_path,
        "frames": len(frames),
        "avg_latency_ms": avg_latency,
        "fps_estimate": 1000.0 / avg_latency if avg_latency > 0 else 0.0,
        "avg_people": mean(people_counts) if people_counts else 0.0,
        "avg_keypoint_confidence": mean(kp_conf) if kp_conf else 0.0,
        "avg_visible_keypoint_ratio": mean(visible_ratios) if visible_ratios else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare YOLO11/YOLO26 pose front-ends on local clips without changing production.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--limit-frames", type=int, default=80)
    parser.add_argument("--stride", type=int, default=5)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.18)
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    models = args.model or [
        str(ROOT / "yolo11n-pose.pt"),
        str(LAB / "weights" / "yolo26" / "yolo26n-pose.pt"),
        str(LAB / "weights" / "yolo26" / "yolo26s-pose.pt"),
    ]
    frames = sample_frames(source, args.limit_frames, args.stride)
    results = []
    for model_path in models:
        if not Path(model_path).exists() and not model_path.startswith("yolo"):
            results.append({"model": model_path, "status": "missing"})
            continue
        try:
            item = evaluate_model(model_path, frames, args.imgsz, args.conf)
            item["status"] = "ok"
            results.append(item)
        except Exception as exc:
            results.append({"model": model_path, "status": "failed", "error": f"{exc.__class__.__name__}: {exc}"})

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "sampled_frames": len(frames),
        "results": results,
    }
    out_dir = LAB / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"pose_frontend_compare_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
