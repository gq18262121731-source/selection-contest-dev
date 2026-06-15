from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[0]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class Track:
    track_id: int
    box_history: deque[np.ndarray] = field(default_factory=lambda: deque(maxlen=12))
    kp_history: deque[np.ndarray] = field(default_factory=lambda: deque(maxlen=12))
    score_history: deque[float] = field(default_factory=lambda: deque(maxlen=12))
    posture_history: deque[str] = field(default_factory=lambda: deque(maxlen=12))
    last_box: np.ndarray | None = None
    last_keypoints: np.ndarray | None = None
    pose_score: float = 0.0
    state_label: str = "unknown"
    state_score: float = 0.0
    missed: int = 0


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def existing_pose_model_path(registry: dict[str, Any]) -> str:
    pose = registry.get("models", {}).get("pose", {})
    candidate = str(pose.get("ultralytics_path") or "yolo11n-pose.pt")
    resolved = (ROOT / candidate).resolve() if not Path(candidate).is_absolute() else Path(candidate)
    if resolved.exists():
        return str(resolved)
    fallback = (REPO_ROOT / "fall_detection_model_bundle" / "yolo11n-pose.pt").resolve()
    if fallback.exists():
        return str(fallback)
    return candidate


def parse_roi(raw: str) -> list[float] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        values = [float(item.strip()) for item in text.split(",")]
    except ValueError:
        return None
    if len(values) != 4:
        return None
    x1, y1, x2, y2 = values
    if x2 <= x1 or y2 <= y1:
        return None
    return values


def as_xyxy_pixel(box: list[float] | None, frame_w: int, frame_h: int) -> np.ndarray | None:
    if box is None:
        return None
    x1, y1, x2, y2 = box
    if max(abs(v) for v in box) <= 1.5:
        x1 *= frame_w
        x2 *= frame_w
        y1 *= frame_h
        y2 *= frame_h
    x1 = max(0.0, min(float(frame_w - 1), x1))
    x2 = max(0.0, min(float(frame_w - 1), x2))
    y1 = max(0.0, min(float(frame_h - 1), y1))
    y2 = max(0.0, min(float(frame_h - 1), y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return np.asarray([x1, y1, x2, y2], dtype=np.float32)


def iou_xyxy(a: np.ndarray, b: np.ndarray) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def center_distance_norm(a: np.ndarray, b: np.ndarray) -> float:
    ac = np.asarray([(a[0] + a[2]) / 2.0, (a[1] + a[3]) / 2.0], dtype=np.float32)
    bc = np.asarray([(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0], dtype=np.float32)
    ah = max(float(a[3] - a[1]), 1.0)
    bh = max(float(b[3] - b[1]), 1.0)
    return float(np.linalg.norm(ac - bc) / max((ah + bh) * 0.5, 1.0))


def update_tracks(
    tracks: dict[int, Track],
    detections: list[tuple[np.ndarray, np.ndarray, float]],
    next_id: int,
) -> int:
    unmatched = set(range(len(detections)))
    for track in tracks.values():
        best_idx = None
        best_score = -1.0
        best_iou = 0.0
        best_dist = 999.0
        for idx in list(unmatched):
            box, _kp, _score = detections[idx]
            if track.last_box is None:
                continue
            overlap = iou_xyxy(track.last_box, box)
            dist = center_distance_norm(track.last_box, box)
            score = overlap + max(0.0, 0.6 - dist) * 0.35
            if score > best_score:
                best_score = score
                best_iou = overlap
                best_dist = dist
                best_idx = idx
        if best_idx is not None and (best_iou >= 0.2 or best_dist <= 0.55):
            box, kp, pose_score = detections[best_idx]
            track.last_box = box
            track.last_keypoints = kp
            track.box_history.append(box)
            track.kp_history.append(kp)
            track.score_history.append(float(pose_score))
            track.pose_score = float(pose_score)
            track.missed = 0
            unmatched.remove(best_idx)
        else:
            track.missed += 1

    stale = [tid for tid, track in tracks.items() if track.missed > 15]
    for tid in stale:
        tracks.pop(tid, None)

    for idx in unmatched:
        box, kp, pose_score = detections[idx]
        track = Track(track_id=next_id)
        track.last_box = box
        track.last_keypoints = kp
        track.box_history.append(box)
        track.kp_history.append(kp)
        track.score_history.append(float(pose_score))
        track.pose_score = float(pose_score)
        tracks[next_id] = track
        next_id += 1
    return next_id


def overlap_ratio(box_a: np.ndarray, box_b: np.ndarray | None) -> float:
    if box_b is None:
        return 0.0
    inter = iou_xyxy(box_a, box_b)
    return float(max(0.0, min(1.0, inter)))


def get_keypoint(kps: np.ndarray, index: int) -> tuple[float, float, float] | None:
    if kps is None or len(kps) <= index:
        return None
    x, y = float(kps[index][0]), float(kps[index][1])
    conf = float(kps[index][2]) if kps.shape[1] >= 3 else 1.0
    return x, y, conf


def midpoint(points: list[tuple[float, float, float] | None]) -> tuple[float, float, float] | None:
    valid = [point for point in points if point and point[2] > 0.15]
    if not valid:
        return None
    x = sum(point[0] for point in valid) / len(valid)
    y = sum(point[1] for point in valid) / len(valid)
    conf = sum(point[2] for point in valid) / len(valid)
    return x, y, conf


def torso_angle_abs(kps: np.ndarray) -> float:
    shoulders = midpoint([get_keypoint(kps, 5), get_keypoint(kps, 6)])
    hips = midpoint([get_keypoint(kps, 11), get_keypoint(kps, 12)])
    if not shoulders or not hips:
        return 0.0
    dx = shoulders[0] - hips[0]
    dy = shoulders[1] - hips[1]
    angle = abs(math.atan2(dx, max(abs(dy), 1e-6)))
    return float(angle)


def avg_point_y(points: list[tuple[float, float, float] | None]) -> float | None:
    valid = [point[1] for point in points if point and point[2] > 0.15]
    if not valid:
        return None
    return float(sum(valid) / len(valid))


def classify_state(
    track: Track,
    *,
    frame_shape: tuple[int, int, int],
    floor_roi: np.ndarray | None,
    thresholds: dict[str, float],
) -> tuple[str, float, dict[str, float]]:
    if track.last_box is None or track.last_keypoints is None:
        return "unknown", 0.0, {}

    x1, y1, x2, y2 = track.last_box
    width = max(float(x2 - x1), 1.0)
    height = max(float(y2 - y1), 1.0)
    aspect = width / height
    torso_angle = torso_angle_abs(track.last_keypoints)
    floor_overlap = overlap_ratio(track.last_box, floor_roi)
    hips_y = avg_point_y([get_keypoint(track.last_keypoints, 11), get_keypoint(track.last_keypoints, 12)])
    knees_y = avg_point_y([get_keypoint(track.last_keypoints, 13), get_keypoint(track.last_keypoints, 14)])
    hip_knee_delta = 0.0
    if hips_y is not None and knees_y is not None:
        hip_knee_delta = max(0.0, (knees_y - hips_y) / height)

    standing_max_aspect = float(thresholds.get("standing_max_aspect", 0.95))
    standing_max_torso_angle = float(thresholds.get("standing_max_torso_angle", 0.35))
    sitting_min_hip_knee_delta = float(thresholds.get("sitting_min_hip_knee_delta", 0.04))
    bending_min_torso_angle = float(thresholds.get("bending_min_torso_angle", 0.35))
    bending_max_aspect = float(thresholds.get("bending_max_aspect", 1.25))
    lying_min_aspect = float(thresholds.get("lying_min_aspect", 1.15))
    floor_overlap_min = float(thresholds.get("floor_overlap_min", 0.20))

    label = "unknown"
    score = 0.35
    if aspect >= lying_min_aspect and floor_overlap >= floor_overlap_min:
        label = "floor_risk"
        score = min(0.98, 0.60 + min(0.35, (aspect - lying_min_aspect) * 0.35) + floor_overlap * 0.15)
    elif torso_angle >= bending_min_torso_angle and aspect <= bending_max_aspect:
        label = "low_posture"
        score = min(0.90, 0.45 + torso_angle * 0.55)
    elif hip_knee_delta >= sitting_min_hip_knee_delta and torso_angle < 0.55:
        label = "low_posture"
        score = min(0.88, 0.45 + hip_knee_delta * 2.5)
    elif aspect <= standing_max_aspect and torso_angle <= standing_max_torso_angle:
        label = "normal"
        score = min(0.92, 0.52 + max(0.0, standing_max_aspect - aspect) * 0.45)

    features = {
        "aspect_ratio": round(aspect, 4),
        "torso_angle": round(torso_angle, 4),
        "hip_knee_delta": round(hip_knee_delta, 4),
        "floor_overlap": round(floor_overlap, 4),
    }
    return label, float(max(0.0, min(1.0, score))), features


def current_vertical_velocity(track: Track) -> float:
    if len(track.box_history) < 2:
        return 0.0
    prev = track.box_history[-2]
    curr = track.box_history[-1]
    prev_cy = float((prev[1] + prev[3]) * 0.5)
    curr_cy = float((curr[1] + curr[3]) * 0.5)
    prev_h = max(float(prev[3] - prev[1]), 1.0)
    curr_h = max(float(curr[3] - curr[1]), 1.0)
    return float((curr_cy - prev_cy) / max((prev_h + curr_h) * 0.5, 1.0))


def extract_people_from_ultralytics(result, conf_threshold: float) -> list[tuple[np.ndarray, np.ndarray, float]]:
    people = []
    if result.boxes is None or result.keypoints is None or len(result.boxes) == 0:
        return people
    boxes = result.boxes.xyxy.detach().cpu().numpy()
    confs = result.boxes.conf.detach().cpu().numpy()
    kps = result.keypoints.data.detach().cpu().numpy()
    for box, conf, kp in zip(boxes, confs, kps):
        if conf < conf_threshold:
            continue
        people.append((box.astype(np.float32), kp.astype(np.float32), float(conf)))
    return people


def detect_pose_ultralytics(model, frame: np.ndarray, *, imgsz: int, conf: float, max_det: int, device: str | int | None, half: bool):
    result = model.predict(
        frame,
        verbose=False,
        imgsz=imgsz,
        conf=conf,
        max_det=max_det,
        device=device,
        half=half,
    )[0]
    return extract_people_from_ultralytics(result, conf)


def detect_pose_mmpose(frame: np.ndarray, inferencer, *, conf: float):
    prediction = next(inferencer(frame, return_vis=False, pred_out_dir=""))
    predictions = prediction.get("predictions") or []
    if predictions and isinstance(predictions[0], list):
        predictions = predictions[0]
    people = []
    for item in predictions:
        keypoints = np.asarray(item.get("keypoints") or [], dtype=np.float32)
        keypoint_scores = np.asarray(item.get("keypoint_scores") or [], dtype=np.float32)
        bbox = np.asarray(item.get("bbox") or [], dtype=np.float32)
        if keypoints.size == 0 or bbox.size < 4:
            continue
        mean_conf = float(np.mean(keypoint_scores)) if keypoint_scores.size > 0 else 0.0
        if mean_conf < conf:
            continue
        if keypoint_scores.ndim == 1 and keypoint_scores.size == len(keypoints):
            kp = np.concatenate([keypoints, keypoint_scores[:, None]], axis=1)
        else:
            kp = keypoints
        box = np.asarray([bbox[0], bbox[1], bbox[2], bbox[3]], dtype=np.float32)
        people.append((box, kp.astype(np.float32), mean_conf))
    return people


def build_runtime(args, registry: dict[str, Any]):
    try:
        from mmpose.apis import MMPoseInferencer

        inferencer = MMPoseInferencer("human")
        return {
            "backend": "mmpose",
            "infer": lambda frame: detect_pose_mmpose(frame, inferencer, conf=args.pose_conf),
        }
    except Exception:
        pass

    from ultralytics import YOLO
    import torch

    pose_model_path = existing_pose_model_path(registry)
    if args.device == "auto":
        torch_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        yolo_device: str | int | None = 0 if torch_device.type == "cuda" else "cpu"
    elif str(args.device).isdigit():
        torch_device = torch.device(f"cuda:{args.device}" if torch.cuda.is_available() else "cpu")
        yolo_device = int(args.device) if torch_device.type == "cuda" else "cpu"
    else:
        torch_device = torch.device(args.device if args.device == "cpu" or torch.cuda.is_available() else "cpu")
        yolo_device = args.device if torch_device.type == "cuda" else "cpu"
    yolo_half = bool(args.half and torch_device.type == "cuda")
    model = YOLO(pose_model_path)
    return {
        "backend": "ultralytics",
        "infer": lambda frame: detect_pose_ultralytics(
            model,
            frame,
            imgsz=args.pose_imgsz,
            conf=args.pose_conf,
            max_det=args.max_det,
            device=yolo_device,
            half=yolo_half,
        ),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_event(handle, payload: dict[str, Any]) -> None:
    if handle is None:
        return
    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    handle.flush()


def maybe_save_snapshot(frame: np.ndarray, snapshot_dir: Path | None, now_s: float) -> str | None:
    if snapshot_dir is None:
        return None
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"pose_{int(now_s * 1000):010d}.jpg"
    cv2.imwrite(str(path), frame)
    return str(path)


def track_payload(track: Track, features: dict[str, float]) -> dict[str, Any]:
    keypoints = []
    if track.last_keypoints is not None:
        keypoints = [[round(float(v), 2) for v in row.tolist()] for row in track.last_keypoints]
    box = []
    if track.last_box is not None:
        box = [round(float(v), 2) for v in track.last_box.tolist()]
    return {
        "track_id": int(track.track_id),
        "bbox": box,
        "pose_score": round(float(track.pose_score), 4),
        "state_label": track.state_label,
        "state_score": round(float(track.state_score), 4),
        "keypoints": keypoints,
        "features": {
            **features,
            "vertical_velocity": round(current_vertical_velocity(track), 4),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real-time pose monitoring from webcam or video.")
    parser.add_argument("--source", default="0")
    parser.add_argument("--model-registry", default=str(ROOT / "configs" / "model_registry.yaml"))
    parser.add_argument("--posture-rules", default=str(ROOT / "configs" / "posture_rules.yaml"))
    parser.add_argument("--profile", default=None)
    parser.add_argument("--pose-imgsz", type=int, default=640)
    parser.add_argument("--pose-conf", type=float, default=0.25)
    parser.add_argument("--max-det", type=int, default=8)
    parser.add_argument("--analysis-width", type=int, default=960)
    parser.add_argument("--process-every", type=int, default=1)
    parser.add_argument("--opencv-buffer-size", type=int, default=1)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--half", action="store_true")
    parser.add_argument("--event-log", default=None)
    parser.add_argument("--latest-json", default=None)
    parser.add_argument("--snapshot-dir", default=None)
    parser.add_argument("--status-log-interval", type=float, default=1.5)
    parser.add_argument("--floor-roi", default="")
    parser.add_argument("--no-display", action="store_true")
    args = parser.parse_args()

    registry = load_yaml(Path(args.model_registry))
    profile_name = args.profile or registry.get("default_profile") or "default"
    profile = registry.get("profiles", {}).get(profile_name, {})
    if args.process_every == 1 and "process_every" in profile:
        args.process_every = int(profile["process_every"])
    if args.pose_imgsz == 640 and "imgsz" in profile:
        args.pose_imgsz = int(profile["imgsz"])
    if args.pose_conf == 0.25 and "conf" in profile:
        args.pose_conf = float(profile["conf"])

    posture_rules = load_yaml(Path(args.posture_rules)).get("thresholds", {})
    runtime = build_runtime(args, registry)

    source = int(args.source) if str(args.source).isdigit() else args.source
    if isinstance(source, str) and source.lower().startswith("rtsp://"):
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|fflags;nobuffer|max_delay;0")

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open source: {args.source}")
    if args.opencv_buffer_size >= 0:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, max(0, args.opencv_buffer_size))

    event_handle = None
    if args.event_log:
        event_path = Path(args.event_log)
        event_path.parent.mkdir(parents=True, exist_ok=True)
        event_handle = event_path.open("a", encoding="utf-8")
    latest_json_path = Path(args.latest_json) if args.latest_json else None
    snapshot_dir = Path(args.snapshot_dir) if args.snapshot_dir else None

    tracks: dict[int, Track] = {}
    next_id = 1
    frame_idx = 0
    start_monotonic = time.monotonic()
    last_status_log_at = -999.0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1
        if args.process_every > 1 and frame_idx % args.process_every != 0:
            continue
        if args.analysis_width > 0 and frame.shape[1] > args.analysis_width:
            scale = args.analysis_width / float(frame.shape[1])
            frame = cv2.resize(frame, (args.analysis_width, max(1, int(frame.shape[0] * scale))), interpolation=cv2.INTER_AREA)

        now_s = time.monotonic() - start_monotonic
        detections = runtime["infer"](frame)
        next_id = update_tracks(tracks, detections, next_id)

        floor_roi = as_xyxy_pixel(parse_roi(args.floor_roi), frame.shape[1], frame.shape[0])
        track_payloads = []
        snapshot_path = None
        for track in tracks.values():
            label, state_score, features = classify_state(
                track,
                frame_shape=frame.shape,
                floor_roi=floor_roi,
                thresholds=posture_rules,
            )
            track.state_label = label
            track.state_score = state_score
            track.posture_history.append(label)
            track_payloads.append(track_payload(track, features))

            if track.last_box is not None:
                box = track.last_box.astype(int)
                color = (0, 80, 255) if label == "floor_risk" else ((0, 200, 255) if label == "low_posture" else (70, 220, 70))
                cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), color, 2)
                text = f"id={track.track_id} {label} {track.state_score:.2f}"
                cv2.putText(frame, text, (box[0], max(24, box[1] - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                if track.last_keypoints is not None:
                    for point in track.last_keypoints:
                        px, py = int(point[0]), int(point[1])
                        pconf = float(point[2]) if len(point) > 2 else 1.0
                        if pconf >= 0.15:
                            cv2.circle(frame, (px, py), 2, color, -1)

        payload = {
            "backend": runtime["backend"],
            "profile": profile_name,
            "source": str(args.source),
            "timestamp_s": round(float(now_s), 4),
            "frame_idx": int(frame_idx),
            "frame_width": int(frame.shape[1]),
            "frame_height": int(frame.shape[0]),
            "tracks": track_payloads,
        }
        if latest_json_path is not None:
            write_json(latest_json_path, payload)

        if now_s - last_status_log_at >= args.status_log_interval:
            if any(item["state_label"] == "floor_risk" for item in track_payloads):
                snapshot_path = maybe_save_snapshot(frame, snapshot_dir, now_s)
            event_payload = {
                **payload,
                "event_type": "pose_status",
                "snapshot_path": snapshot_path,
            }
            write_event(event_handle, event_payload)
            last_status_log_at = now_s

        if not args.no_display:
            cv2.imshow("Pose Monitor", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord("q"):
                break

    cap.release()
    if event_handle is not None:
        event_handle.close()
    if not args.no_display:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
