from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

from config_utils import existing_model_path, get_profile, load_yaml
from realtime_fall_monitor import classify_posture, iou_xyxy


ROOT = Path(__file__).resolve().parents[1]


def run_image(args: argparse.Namespace) -> int:
    registry = load_yaml(args.model_registry)
    models = registry.get("models", {})
    pose_entry = models.get("pose", {})
    posture_entry = models.get("posture_risk", {})
    detector_entry = models.get("fall_detector", {})

    pose_path = args.pose_model or str(existing_model_path(pose_entry) or "yolo11n-pose.pt")
    posture_path = args.posture_model or str(existing_model_path(posture_entry) or "")
    detector_path = args.fall_detector or str(existing_model_path(detector_entry) or "")
    fall_labels = set(detector_entry.get("fall_labels", ["fall", "fallen", "lying"]))

    frame = cv2.imread(str(args.source))
    if frame is None:
        raise RuntimeError(f"Failed to read image: {args.source}")

    pose_model = YOLO(pose_path)
    posture_model = YOLO(posture_path) if posture_path and Path(posture_path).exists() else None
    detector_model = YOLO(detector_path) if detector_path and Path(detector_path).exists() else None

    pose_result = pose_model.predict(frame, verbose=False, imgsz=args.imgsz, conf=args.conf, max_det=args.max_det)[0]
    detector_result = detector_model.predict(frame, verbose=False, imgsz=args.imgsz, conf=args.detector_conf)[0] if detector_model else None
    detector_boxes = []
    if detector_result is not None and detector_result.boxes is not None:
        boxes = detector_result.boxes.xyxy.detach().cpu().numpy()
        scores = detector_result.boxes.conf.detach().cpu().numpy()
        classes = detector_result.boxes.cls.detach().cpu().numpy().astype(int)
        for box, score, cls_idx in zip(boxes, scores, classes):
            label = str(detector_model.names.get(int(cls_idx), cls_idx))
            if label in fall_labels:
                detector_boxes.append((box, float(score), label))

    records = []
    if pose_result.boxes is not None:
        boxes = pose_result.boxes.xyxy.detach().cpu().numpy()
        scores = pose_result.boxes.conf.detach().cpu().numpy()
        for idx, (box, person_conf) in enumerate(zip(boxes, scores), start=1):
            x1, y1, x2, y2 = box.astype(int)
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(frame.shape[1], x2)
            y2 = min(frame.shape[0], y2)
            crop = frame[y1:y2, x1:x2]
            posture_label, posture_score = classify_posture(crop, posture_model, imgsz=320, device=None, half=False)
            detector_score = 0.0
            detector_label = "none"
            for det_box, det_score, det_label in detector_boxes:
                overlap = iou_xyxy(box, det_box)
                if overlap >= 0.15 and det_score > detector_score:
                    detector_score = det_score
                    detector_label = det_label
            fall_score = max(posture_score, detector_score)
            risk_level = "L3" if fall_score >= args.threshold else ("L2" if fall_score >= args.threshold * 0.75 else "L0")
            color = (0, 0, 255) if risk_level == "L3" else ((0, 215, 255) if risk_level == "L2" else (0, 255, 0))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"id={idx} risk={risk_level} score={fall_score:.2f}", (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            records.append(
                {
                    "person_id": idx,
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    "person_confidence": float(person_conf),
                    "posture_label": posture_label,
                    "posture_score": float(posture_score),
                    "detector_label": detector_label,
                    "detector_score": float(detector_score),
                    "fall_score": float(fall_score),
                    "risk_level": risk_level,
                }
            )

    output_image = Path(args.output_image)
    output_json = Path(args.output_json)
    output_image.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_image), frame)
    output_json.write_text(json.dumps({"source": str(args.source), "detections": records}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output_image": str(output_image), "output_json": str(output_json), "detections": records}, indent=2, ensure_ascii=False))
    return 0


def run_stream(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "realtime_fall_monitor.py"),
        "--source",
        str(args.source),
        "--model-registry",
        str(args.model_registry),
        "--threshold",
        str(args.threshold),
    ]
    if args.profile:
        cmd.extend(["--profile", str(args.profile)])
    if args.fall_detector:
        cmd.extend(["--fall-detector", str(args.fall_detector), "--detector-weight", str(args.detector_weight)])
    if args.save_path:
        cmd.extend(["--save-path", str(args.save_path)])
    if args.event_log:
        cmd.extend(["--event-log", str(args.event_log)])
    if args.snapshot_dir:
        cmd.extend(["--snapshot-dir", str(args.snapshot_dir)])
    if args.status_log_interval is not None:
        cmd.extend(["--status-log-interval", str(args.status_log_interval)])
    cmd.extend(["--analysis-width", str(args.analysis_width)])
    cmd.extend(["--process-every", str(args.process_every)])
    cmd.extend(["--opencv-buffer-size", str(args.opencv_buffer_size)])
    cmd.extend(["--device", str(args.device)])
    if args.half:
        cmd.append("--half")
    if args.no_display:
        cmd.append("--no-display")
    subprocess.run(cmd, check=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified fall inference entrypoint for image, video, and camera sources.")
    parser.add_argument("--mode", choices=["image", "video", "camera"], required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--model-registry", default=str(ROOT / "configs" / "model_registry.yaml"))
    parser.add_argument("--profile", default=None)
    parser.add_argument("--pose-model", default=None)
    parser.add_argument("--posture-model", default=None)
    parser.add_argument("--fall-detector", default=None)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.2)
    parser.add_argument("--detector-conf", type=float, default=0.25)
    parser.add_argument("--max-det", type=int, default=8)
    parser.add_argument("--threshold", type=float, default=0.65)
    parser.add_argument("--detector-weight", type=float, default=0.2)
    parser.add_argument("--output-image", default=str(ROOT / "outputs" / "image_result.jpg"))
    parser.add_argument("--output-json", default=str(ROOT / "outputs" / "image_result.json"))
    parser.add_argument("--save-path", default=None)
    parser.add_argument("--event-log", default=None)
    parser.add_argument("--snapshot-dir", default=None)
    parser.add_argument("--status-log-interval", type=float, default=1.0)
    parser.add_argument("--analysis-width", type=int, default=0)
    parser.add_argument("--process-every", type=int, default=1)
    parser.add_argument("--opencv-buffer-size", type=int, default=1)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--half", action="store_true")
    parser.add_argument("--no-display", action="store_true")
    args = parser.parse_args()

    registry = load_yaml(args.model_registry)
    profile = get_profile(registry, args.profile)
    if args.threshold == 0.65 and "threshold" in profile:
        args.threshold = float(profile["threshold"])

    if args.mode == "image":
        return run_image(args)
    return run_stream(args)


if __name__ == "__main__":
    raise SystemExit(main())
