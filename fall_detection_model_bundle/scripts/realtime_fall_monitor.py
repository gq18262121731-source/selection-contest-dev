from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from config_utils import existing_model_path, get_profile, load_yaml
from temporal_semantic_utils import semantic_features_from_pose_sequence
from train_temporal_gru import GRUFallNet, normalize_pose
from train_temporal_semantic_mix import SemanticTemporalNet
from train_temporal_tcn_transformer import HybridTCNTransformer

try:
    import winsound
except Exception:  # pragma: no cover
    winsound = None


ALERT_RULES = {
    "severity": {
        "l1_recovered_down_seconds": 5.0,
        "l2_recovered_down_seconds": 15.0,
        "l3_down_seconds": 15.0,
        "l4_down_seconds": 40.0,
        "l4_immobile_seconds": 25.0,
    },
    "state_machine": {
        "suspect_ratio": 0.75,
        "suspect_floor": 0.35,
        "postfall_confirm_ratio": 0.72,
        "postfall_confirm_floor": 0.42,
        "persistence_confirm_score_floor": 0.22,
        "downed_persistence_seconds": 0.45,
        "suspected_timeout_seconds": 2.5,
        "confirmed_to_monitor_seconds": 1.0,
        "recovery_confirm_seconds": 3.0,
        "recovery_fail_seconds": 0.8,
        "recovered_reset_seconds": 4.0,
        "red_latch_seconds": 10.0,
    },
    "observations": {
        "posture_downed": 0.52,
        "posture_strong_downed": 0.60,
        "posture_upright": 0.28,
        "box_aspect_downed": 1.05,
        "box_aspect_strong_downed": 1.18,
        "box_aspect_upright": 0.85,
        "pose_angle_downed": 0.24,
        "pose_angle_upright": 0.18,
        "motion_low": 0.035,
        "posture_delta_rapid": 0.18,
        "score_range_rapid": 0.22,
    },
}

INJURY_RULES = {
    "observation": {
        "post_fall_observe_seconds": 180.0,
        "min_recovery_watch_seconds": 20.0,
        "short_recovery_seconds": 5.0,
        "delayed_recovery_seconds": 15.0,
        "difficult_recovery_seconds": 40.0,
        "emergency_down_seconds": 90.0,
        "emergency_immobile_seconds": 60.0,
    },
    "mobility": {
        "low_speed": 0.018,
        "very_low_speed": 0.008,
        "unstable_sway": 0.045,
        "severe_sway": 0.075,
        "limp_asymmetry": 0.35,
        "severe_limp_asymmetry": 0.55,
        "limp_min_motion": 0.006,
        "abnormal_score_i2": 0.35,
        "abnormal_score_i3": 0.55,
        "abnormal_score_i4": 0.75,
    },
}


def merge_alert_rules(overrides: dict) -> None:
    for section, values in overrides.items():
        if section in ALERT_RULES and isinstance(values, dict):
            ALERT_RULES[section].update(values)


def merge_injury_rules(overrides: dict) -> None:
    for section, values in overrides.items():
        if section in INJURY_RULES and isinstance(values, dict):
            INJURY_RULES[section].update(values)


@dataclass
class Track:
    track_id: int
    box_history: deque = field(default_factory=lambda: deque(maxlen=24))
    kp_history: deque = field(default_factory=lambda: deque(maxlen=24))
    posture_history: deque = field(default_factory=lambda: deque(maxlen=24))
    score_history: deque = field(default_factory=lambda: deque(maxlen=24))
    last_box: np.ndarray | None = None
    missed: int = 0
    alert_frames: int = 0
    score: float = 0.0
    gru_score: float = 0.0
    hybrid_score: float = 0.0
    semantic_score: float = 0.0
    posture_score: float = 0.0
    detector_score: float = 0.0
    posture_label: str = "unknown"
    last_alerted: bool = False
    state: str = "normal"
    severity: str = "NONE"
    state_since: float = 0.0
    confirmed_fall_since: float | None = None
    red_latch_until: float = 0.0
    down_since: float | None = None
    recovery_candidate_since: float | None = None
    recovery_fail_count: int = 0
    immobile_since: float | None = None
    last_peak_score: float = 0.0
    last_peak_time: float = 0.0
    last_recovery_time: float | None = None
    last_sound_time: float = -999.0
    injury_state: str = "none"
    injury_level: str = "I0"
    injury_reason: str = "normal"
    injury_observe_until: float = 0.0
    recovery_time: float | None = None
    mobility_score: float = 1.0
    stability_score: float = 1.0
    limp_score: float = 0.0
    injury_score: float = 0.0
    last_event_state: str = "normal"
    last_event_injury_level: str = "I0"
    detector_only: bool = False
    detector_hits: int = 0
    last_detector_seen_s: float = -999.0
    last_status_log_time: float = -999.0
    last_observations: dict = field(default_factory=dict)


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


def expand_box(box: np.ndarray, frame_shape: tuple[int, int, int], scale_x: float, scale_y: float) -> np.ndarray:
    height, width = frame_shape[:2]
    x1, y1, x2, y2 = [float(v) for v in box]
    cx = (x1 + x2) * 0.5
    cy = (y1 + y2) * 0.5
    bw = max(x2 - x1, 1.0) * scale_x
    bh = max(y2 - y1, 1.0) * scale_y
    return np.asarray(
        [
            max(0.0, cx - bw * 0.5),
            max(0.0, cy - bh * 0.5),
            min(float(width), cx + bw * 0.5),
            min(float(height), cy + bh * 0.5),
        ],
        dtype=np.float32,
    )


def horizontal_overlap_ratio(a: np.ndarray, b: np.ndarray) -> float:
    overlap = max(0.0, min(float(a[2]), float(b[2])) - max(float(a[0]), float(b[0])))
    width = min(max(float(a[2] - a[0]), 1.0), max(float(b[2] - b[0]), 1.0))
    return float(overlap / width)


def detector_track_affinity(track_box: np.ndarray, det_box: np.ndarray, frame_shape: tuple[int, int, int]) -> float:
    overlap = iou_xyxy(track_box, det_box)
    expanded_overlap = iou_xyxy(expand_box(track_box, frame_shape, 2.2, 1.45), det_box)
    dist = center_distance_norm(track_box, det_box)
    horizontal_overlap = horizontal_overlap_ratio(track_box, det_box)

    track_bottom = float(track_box[3])
    det_center_y = float((det_box[1] + det_box[3]) * 0.5)
    track_height = max(float(track_box[3] - track_box[1]), 1.0)
    vertical_near_feet = abs(det_center_y - track_bottom) / track_height <= 0.45

    score = max(overlap * 2.0, expanded_overlap * 1.35, max(0.0, 0.9 - dist))
    if horizontal_overlap >= 0.25 and vertical_near_feet:
        score = max(score, 0.62)
    elif horizontal_overlap >= 0.45 and dist <= 1.25:
        score = max(score, 0.50)
    return float(max(0.0, min(1.0, score)))


def extract_people(result) -> list[tuple[np.ndarray, np.ndarray]]:
    people = []
    if result.boxes is None or result.keypoints is None or len(result.boxes) == 0:
        return people
    boxes = result.boxes.xyxy.detach().cpu().numpy()
    conf = result.boxes.conf.detach().cpu().numpy()
    kps = result.keypoints.data.detach().cpu().numpy()
    for box, score, kp in zip(boxes, conf, kps):
        if score < 0.2:
            continue
        people.append((box.astype(np.float32), kp.astype(np.float32)))
    return people


def extract_tracked_people(result) -> list[tuple[int, np.ndarray, np.ndarray]]:
    people = []
    if result.boxes is None or result.keypoints is None or len(result.boxes) == 0:
        return people
    if result.boxes.id is None:
        return people
    ids = result.boxes.id.detach().cpu().numpy().astype(int)
    boxes = result.boxes.xyxy.detach().cpu().numpy()
    conf = result.boxes.conf.detach().cpu().numpy()
    kps = result.keypoints.data.detach().cpu().numpy()
    for track_id, box, score, kp in zip(ids, boxes, conf, kps):
        if score < 0.2:
            continue
        people.append((int(track_id), box.astype(np.float32), kp.astype(np.float32)))
    return people


def update_tracks(tracks: dict[int, Track], detections: list[tuple[np.ndarray, np.ndarray]], next_id: int) -> int:
    unmatched = set(range(len(detections)))
    for track in tracks.values():
        best_idx = None
        best_score = -1.0
        best_iou = 0.0
        best_dist = 999.0
        for idx in list(unmatched):
            box, _ = detections[idx]
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
            box, kp = detections[best_idx]
            track.last_box = box
            track.box_history.append(box)
            track.kp_history.append(kp)
            track.missed = 0
            unmatched.remove(best_idx)
        else:
            track.missed += 1

    stale = [tid for tid, track in tracks.items() if track.missed > 15]
    for tid in stale:
        tracks.pop(tid, None)

    for idx in unmatched:
        box, kp = detections[idx]
        track = Track(track_id=next_id)
        track.last_box = box
        track.box_history.append(box)
        track.kp_history.append(kp)
        track.posture_history.append(0.0)
        track.score_history.append(0.0)
        tracks[next_id] = track
        next_id += 1
    return next_id


def update_tracks_from_tracker(tracks: dict[int, Track], detections: list[tuple[int, np.ndarray, np.ndarray]]) -> None:
    seen: set[int] = set()
    for track_id, box, kp in detections:
        seen.add(track_id)
        track = tracks.get(track_id)
        if track is None:
            track = Track(track_id=track_id)
            track.posture_history.append(0.0)
            track.score_history.append(0.0)
            tracks[track_id] = track
        track.detector_only = False
        track.last_box = box
        track.box_history.append(box)
        track.kp_history.append(kp)
        track.missed = 0

    for track_id, track in list(tracks.items()):
        if track.detector_only:
            continue
        if track_id not in seen:
            track.missed += 1
            if track.missed > 30:
                tracks.pop(track_id, None)


def score_fall_detector_for_tracks(
    frame: np.ndarray,
    tracks: dict[int, Track],
    detector_model: YOLO | None,
    fall_labels: set[str],
    imgsz: int,
    conf: float,
    iou: float,
    device: str | int | None,
    half: bool,
    next_id: int,
    now_s: float,
) -> int:
    for track in tracks.values():
        track.detector_score = 0.0
    if detector_model is None:
        return next_id
    result = detector_model.predict(frame, verbose=False, imgsz=imgsz, conf=conf, iou=iou, device=device, half=half)[0]
    if result.boxes is None or len(result.boxes) == 0:
        return next_id
    boxes = result.boxes.xyxy.detach().cpu().numpy()
    scores = result.boxes.conf.detach().cpu().numpy()
    classes = result.boxes.cls.detach().cpu().numpy().astype(int)
    names = detector_model.names
    for box, score, cls_idx in zip(boxes, scores, classes):
        label = str(names.get(int(cls_idx), cls_idx))
        if label not in fall_labels:
            continue
        det_box = box.astype(np.float32)
        best_track: Track | None = None
        best_affinity = 0.0
        for track in tracks.values():
            if track.last_box is None:
                continue
            affinity = detector_track_affinity(track.last_box, det_box, frame.shape)
            if affinity > best_affinity:
                best_affinity = affinity
                best_track = track
        if best_track is not None and best_affinity >= 0.35:
            best_track.detector_score = max(best_track.detector_score, float(score * best_affinity))
            best_track.detector_hits += 1
            best_track.last_detector_seen_s = now_s
            best_track.detector_only = False
        elif float(score) >= 0.25:
            track = Track(track_id=next_id)
            track.detector_only = True
            track.detector_hits = 1
            track.last_detector_seen_s = now_s
            track.last_box = det_box
            track.box_history.append(det_box)
            track.posture_history.append(float(score))
            track.score_history.append(0.0)
            track.detector_score = float(score)
            tracks[next_id] = track
            next_id += 1
    for track in tracks.values():
        if track.detector_only and now_s - track.last_detector_seen_s > 1.2:
            track.missed += 4
    return next_id


def build_model(weights_path: Path, device: torch.device) -> tuple[torch.nn.Module, dict]:
    checkpoint = torch.load(weights_path, map_location=device)
    model_type = checkpoint.get("model_type", "gru")
    if model_type == "hybrid_tcn_transformer":
        model = HybridTCNTransformer(input_dim=checkpoint["input_dim"]).to(device)
    elif model_type == "semantic_temporal_mix":
        model = SemanticTemporalNet(input_dim=checkpoint["input_dim"]).to(device)
    else:
        model = GRUFallNet(input_dim=checkpoint["input_dim"]).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    return model, checkpoint


def score_track_gru(track: Track, model: torch.nn.Module, device: torch.device) -> float:
    if len(track.kp_history) < track.kp_history.maxlen:
        return 0.0
    kps = np.asarray(track.kp_history, dtype=np.float32)
    boxes = np.asarray(track.box_history, dtype=np.float32)
    features = normalize_pose(kps, boxes)
    x = torch.from_numpy(features).unsqueeze(0).to(device)
    with torch.no_grad():
        prob = torch.sigmoid(model(x)).item()
    return float(prob)


def score_track_hybrid(track: Track, model: torch.nn.Module, device: torch.device) -> float:
    if len(track.kp_history) < track.kp_history.maxlen or len(track.posture_history) < track.posture_history.maxlen:
        return 0.0
    kps = np.asarray(track.kp_history, dtype=np.float32)
    boxes = np.asarray(track.box_history, dtype=np.float32)
    base = normalize_pose(kps, boxes)
    posture = np.asarray(track.posture_history, dtype=np.float32)
    delta = np.concatenate([[0.0], np.diff(posture)]).astype(np.float32)
    smooth = np.asarray([posture[max(0, i - 2) : i + 1].mean() for i in range(len(posture))], dtype=np.float32)
    extra = np.stack([posture, delta, smooth], axis=1)
    features = np.concatenate([base, extra], axis=1)
    x = torch.from_numpy(features).unsqueeze(0).to(device)
    with torch.no_grad():
        prob = torch.sigmoid(model(x)).item()
    return float(prob)


def score_track_semantic(track: Track, model: torch.nn.Module, device: torch.device) -> float:
    if len(track.kp_history) < track.kp_history.maxlen:
        return 0.0
    kps = np.asarray(track.kp_history, dtype=np.float32)
    boxes = np.asarray(track.box_history, dtype=np.float32)
    features = semantic_features_from_pose_sequence(kps, boxes)
    x = torch.from_numpy(features).unsqueeze(0).to(device)
    with torch.no_grad():
        prob = torch.sigmoid(model(x)).item()
    return float(prob)


def classify_posture(crop: np.ndarray, posture_model: YOLO | None, *, imgsz: int, device: str | int | None, half: bool) -> tuple[str, float]:
    if posture_model is None or crop.size == 0:
        return "unknown", 0.0
    result = posture_model.predict(crop, verbose=False, imgsz=imgsz, device=device, half=half)[0]
    probs = result.probs
    if probs is None:
        return "unknown", 0.0
    names = posture_model.names
    top1 = int(probs.top1)
    prob_values = probs.data.detach().cpu().numpy()
    label = names[top1]
    label_set = set(names.values())
    if label_set == {"risk", "safe"}:
        risk_idx = next(idx for idx, name in names.items() if name == "risk")
        return label, float(prob_values[risk_idx])

    mapping = {name: idx for idx, name in names.items()}
    # Auxiliary fall-risk score from static posture
    score = 0.0
    if "lying" in mapping:
        score += float(prob_values[mapping["lying"]]) * 0.9
    if "crawling" in mapping:
        score += float(prob_values[mapping["crawling"]]) * 0.6
    if "bending" in mapping:
        score += float(prob_values[mapping["bending"]]) * 0.25
    if "standing" in mapping:
        score -= float(prob_values[mapping["standing"]]) * 0.35
    if "sitting" in mapping:
        score -= float(prob_values[mapping["sitting"]]) * 0.15
    return label, float(max(0.0, min(1.0, score)))


def names_inv(target: str, names: dict[int, str]) -> int:
    for idx, name in names.items():
        if name == target:
            return idx
    return -1


def play_alert_sound() -> None:
    if winsound is not None:
        try:
            winsound.MessageBeep(winsound.MB_ICONHAND)
            return
        except Exception:
            pass
    print("\a", end="", flush=True)


def current_observations(track: Track) -> dict[str, float | bool]:
    if track.last_box is None or len(track.box_history) == 0:
        return {
            "box_aspect": 0.0,
            "recent_posture": 0.0,
            "posture_delta": 0.0,
            "pose_angle_abs": 0.0,
            "movement": 0.0,
            "aspect_delta": 0.0,
            "center_drop": 0.0,
            "downed": False,
            "upright": False,
            "motion_low": False,
            "rapid_change": False,
        }

    x1, y1, x2, y2 = track.last_box
    box_aspect = float(max(x2 - x1, 1.0) / max(y2 - y1, 1.0))
    recent_posture = float(np.mean(track.posture_history)) if len(track.posture_history) else 0.0
    posture_delta = 0.0
    if len(track.posture_history) >= 4:
        posture_delta = float(track.posture_history[-1] - track.posture_history[-4])

    pose_feats = semantic_features_from_pose_sequence(
        np.asarray(track.kp_history, dtype=np.float32),
        np.asarray(track.box_history, dtype=np.float32),
    )
    pose_angle_abs = float(abs(pose_feats[-1, 0])) if len(pose_feats) else 0.0

    movement = 0.0
    aspect_delta = 0.0
    center_drop = 0.0
    if len(track.box_history) >= 5:
        centers = []
        heights = []
        aspects = []
        for box in list(track.box_history)[-5:]:
            bx1, by1, bx2, by2 = box
            centers.append(((bx1 + bx2) / 2.0, (by1 + by2) / 2.0))
            heights.append(max(by2 - by1, 1.0))
            aspects.append(max(bx2 - bx1, 1.0) / max(by2 - by1, 1.0))
        centers = np.asarray(centers, dtype=np.float32)
        heights = np.asarray(heights, dtype=np.float32)
        aspects = np.asarray(aspects, dtype=np.float32)
        deltas = np.diff(centers, axis=0)
        movement = float(np.linalg.norm(deltas, axis=1).mean() / max(heights.mean(), 1.0))
        aspect_delta = float(aspects[-1] - aspects[0])
        center_drop = float((centers[-1, 1] - centers[0, 1]) / max(heights.mean(), 1.0))

    recent_scores = list(track.score_history)[-4:] if len(track.score_history) >= 4 else list(track.score_history)
    score_range = float(max(recent_scores) - min(recent_scores)) if recent_scores else 0.0
    obs_rules = ALERT_RULES["observations"]
    rapid_change = posture_delta > obs_rules["posture_delta_rapid"] or score_range > obs_rules["score_range_rapid"]

    downed = (
        recent_posture >= obs_rules["posture_downed"]
        or box_aspect >= obs_rules["box_aspect_downed"]
        or pose_angle_abs >= obs_rules["pose_angle_downed"]
    )
    upright = (
        recent_posture <= obs_rules["posture_upright"]
        and box_aspect <= obs_rules["box_aspect_upright"]
        and pose_angle_abs <= obs_rules["pose_angle_upright"]
    )
    motion_low = movement <= obs_rules["motion_low"]

    return {
        "box_aspect": box_aspect,
        "recent_posture": recent_posture,
        "posture_delta": posture_delta,
        "pose_angle_abs": pose_angle_abs,
        "movement": movement,
        "aspect_delta": aspect_delta,
        "center_drop": center_drop,
        "downed": downed,
        "upright": upright,
        "motion_low": motion_low,
        "rapid_change": rapid_change,
    }


def gait_observations(track: Track) -> dict[str, float]:
    if len(track.box_history) < 8:
        return {
            "speed": 0.0,
            "sway": 0.0,
            "limp_asymmetry": 0.0,
            "mobility_score": 1.0,
            "stability_score": 1.0,
            "limp_score": 0.0,
            "injury_score": 0.0,
        }

    boxes = np.asarray(track.box_history, dtype=np.float32)
    centers = np.stack([(boxes[:, 0] + boxes[:, 2]) / 2.0, (boxes[:, 1] + boxes[:, 3]) / 2.0], axis=1)
    heights = np.maximum(boxes[:, 3] - boxes[:, 1], 1.0)
    norm = float(max(np.mean(heights), 1.0))
    deltas = np.diff(centers, axis=0) / norm
    speed = float(np.linalg.norm(deltas, axis=1).mean()) if len(deltas) else 0.0
    sway = float(np.std(centers[:, 0] / norm)) if len(centers) else 0.0

    limp_asymmetry = 0.0
    if len(track.kp_history) >= 8:
        kps = np.asarray(track.kp_history, dtype=np.float32)
        left_ankle = kps[:, 15, :]
        right_ankle = kps[:, 16, :]
        valid_l = left_ankle[:, 2] > 0.15
        valid_r = right_ankle[:, 2] > 0.15
        if valid_l.sum() >= 4 and valid_r.sum() >= 4:
            left_motion = np.linalg.norm(np.diff(left_ankle[:, :2], axis=0), axis=1) / norm
            right_motion = np.linalg.norm(np.diff(right_ankle[:, :2], axis=0), axis=1) / norm
            left_mean = float(left_motion[valid_l[1:] & valid_l[:-1]].mean()) if (valid_l[1:] & valid_l[:-1]).any() else 0.0
            right_mean = float(right_motion[valid_r[1:] & valid_r[:-1]].mean()) if (valid_r[1:] & valid_r[:-1]).any() else 0.0
            denom = max(left_mean + right_mean, 1e-6)
            if max(left_mean, right_mean) >= INJURY_RULES["mobility"]["limp_min_motion"]:
                limp_asymmetry = abs(left_mean - right_mean) / denom

    rules = INJURY_RULES["mobility"]
    mobility_score = 1.0 - min(1.0, speed / max(rules["low_speed"], 1e-6))
    stability_score = min(1.0, sway / max(rules["unstable_sway"], 1e-6))
    limp_score = min(1.0, limp_asymmetry / max(rules["limp_asymmetry"], 1e-6))
    injury_score = float(max(mobility_score * 0.45, stability_score * 0.35, limp_score * 0.70))
    return {
        "speed": speed,
        "sway": sway,
        "limp_asymmetry": limp_asymmetry,
        "mobility_score": float(mobility_score),
        "stability_score": float(stability_score),
        "limp_score": float(limp_score),
        "injury_score": injury_score,
    }


def update_injury_assessment(track: Track, now_s: float, obs: dict[str, float | bool]) -> None:
    if track.confirmed_fall_since is None:
        track.injury_state = "none"
        track.injury_level = "I0"
        track.injury_reason = "normal"
        track.injury_score = 0.0
        return

    observation = INJURY_RULES["observation"]
    mobility = INJURY_RULES["mobility"]
    down_duration = 0.0 if track.down_since is None else max(0.0, now_s - track.down_since)
    immobile_duration = 0.0 if track.immobile_since is None else max(0.0, now_s - track.immobile_since)
    recovery_delay = None if track.recovery_time is None else max(0.0, track.recovery_time - track.confirmed_fall_since)

    gait = gait_observations(track)
    track.mobility_score = gait["mobility_score"]
    track.stability_score = gait["stability_score"]
    track.limp_score = gait["limp_score"]
    track.injury_score = gait["injury_score"]

    if down_duration >= observation["emergency_down_seconds"] or immobile_duration >= observation["emergency_immobile_seconds"]:
        track.injury_level = "I5"
        track.injury_state = "emergency"
        track.injury_reason = "long_down_or_immobile"
        return
    if bool(obs["downed"]) and down_duration >= observation["difficult_recovery_seconds"]:
        track.injury_level = "I4"
        track.injury_state = "needs_assistance"
        track.injury_reason = "unable_to_recover"
        return

    if track.recovery_time is None:
        if down_duration >= observation["delayed_recovery_seconds"]:
            track.injury_level = "I3"
            track.injury_state = "post_fall_monitoring"
            track.injury_reason = "delayed_recovery"
        else:
            track.injury_level = "I2"
            track.injury_state = "post_fall_monitoring"
            track.injury_reason = "fall_confirmed_observing"
        return

    if now_s <= track.injury_observe_until:
        if track.injury_score >= mobility["abnormal_score_i4"]:
            track.injury_level = "I4"
            track.injury_state = "needs_assistance"
            track.injury_reason = "severe_abnormal_recovery"
        elif track.injury_score >= mobility["abnormal_score_i3"]:
            track.injury_level = "I3"
            track.injury_state = "abnormal_recovery"
            track.injury_reason = "limp_or_unstable_recovery"
        elif track.injury_score >= mobility["abnormal_score_i2"] or (recovery_delay is not None and recovery_delay >= observation["delayed_recovery_seconds"]):
            track.injury_level = "I2"
            track.injury_state = "injury_watch"
            track.injury_reason = "minor_abnormal_recovery"
        elif recovery_delay is not None and recovery_delay <= observation["short_recovery_seconds"]:
            track.injury_level = "I1"
            track.injury_state = "recovered_observing"
            track.injury_reason = "quick_recovery_observing"
        else:
            track.injury_level = "I2"
            track.injury_state = "injury_watch"
            track.injury_reason = "recovery_observation"
        return

    if track.injury_level in {"I3", "I4", "I5"}:
        return
    track.injury_level = "I1"
    track.injury_state = "resolved_observed"
    track.injury_reason = "observation_complete"


def set_state(track: Track, state: str, now_s: float) -> None:
    if track.state != state:
        track.state = state
        track.state_since = now_s


def update_severity(track: Track, now_s: float, obs: dict[str, float | bool]) -> None:
    if track.confirmed_fall_since is None:
        track.severity = "NONE"
        return

    down_duration = 0.0 if track.down_since is None else max(0.0, now_s - track.down_since)
    immobile_duration = 0.0 if track.immobile_since is None else max(0.0, now_s - track.immobile_since)

    severity_rules = ALERT_RULES["severity"]
    if track.state == "recovered":
        if down_duration <= severity_rules["l1_recovered_down_seconds"]:
            track.severity = "L1"
        elif down_duration <= severity_rules["l2_recovered_down_seconds"]:
            track.severity = "L2"
        else:
            track.severity = "L3"
        return

    if track.state in {"confirmed_fall", "post_fall_monitoring", "recovery_watch"}:
        if down_duration >= severity_rules["l4_down_seconds"] or immobile_duration >= severity_rules["l4_immobile_seconds"]:
            track.severity = "L4"
        elif down_duration >= severity_rules["l3_down_seconds"] or track.recovery_fail_count >= 1:
            track.severity = "L3"
        else:
            track.severity = "L2"
        return

    if track.state in {"injury_watch", "abnormal_recovery", "needs_assistance", "emergency"}:
        if track.injury_level == "I5":
            track.severity = "L4"
        elif track.injury_level == "I4":
            track.severity = "L4"
        elif track.injury_level == "I3":
            track.severity = "L3"
        elif track.injury_level == "I2":
            track.severity = "L2"
        else:
            track.severity = "L1"
        return

    if track.state == "suspected_fall":
        track.severity = "OBS"
    else:
        track.severity = "NONE"


def update_track_state(track: Track, now_s: float, confirm_threshold: float) -> bool:
    obs = current_observations(track)
    track.last_observations = dict(obs)
    state_rules = ALERT_RULES["state_machine"]
    obs_rules = ALERT_RULES["observations"]
    current_score = track.score
    recent_peak = max(track.score_history) if len(track.score_history) else current_score
    suspect_threshold = max(state_rules["suspect_floor"], confirm_threshold * state_rules["suspect_ratio"])
    just_confirmed = False
    strong_downed = bool(obs["downed"]) and (
        bool(obs["motion_low"])
        or float(obs["box_aspect"]) >= obs_rules["box_aspect_strong_downed"]
        or float(obs["recent_posture"]) >= obs_rules["posture_strong_downed"]
    )
    movement = float(obs["movement"])
    center_drop = float(obs["center_drop"])
    box_aspect = float(obs["box_aspect"])
    pose_angle_abs = float(obs["pose_angle_abs"])
    posture_delta = float(obs["posture_delta"])
    downward_transition = center_drop >= 0.06 and (posture_delta >= 0.18 or float(obs["aspect_delta"]) >= 0.18)
    collapse_transition = center_drop >= 0.08 and movement >= 0.035 and posture_delta >= 0.30
    horizontal_impact = movement >= 0.055 and box_aspect >= 1.45 and pose_angle_abs >= 0.28
    fall_motion_evidence = downward_transition or collapse_transition or horizontal_impact
    high_confidence_temporal = max(track.gru_score, track.hybrid_score, track.semantic_score) >= 0.72
    detector_supported = track.detector_score >= 0.45 or (track.detector_only and track.detector_hits >= 2)
    support_surface_like = (
        box_aspect >= 1.80
        and movement < 0.055
        and center_drop < 0.13
        and pose_angle_abs < 0.55
    )
    detector_motion_evidence = detector_supported and (
        center_drop >= 0.045 and (posture_delta >= 0.18 or float(obs["aspect_delta"]) >= 0.18)
    )
    temporal_motion_evidence = high_confidence_temporal and (
        fall_motion_evidence or horizontal_impact
    )
    if support_surface_like:
        detector_motion_evidence = False
        temporal_motion_evidence = False
        fall_motion_evidence = False
    confirmation_evidence = fall_motion_evidence or detector_motion_evidence or temporal_motion_evidence
    track.last_observations.update(
        {
            "fall_motion_evidence": fall_motion_evidence,
            "detector_motion_evidence": detector_motion_evidence,
            "temporal_motion_evidence": temporal_motion_evidence,
            "support_surface_like": support_surface_like,
            "confirmation_evidence": confirmation_evidence,
        }
    )

    if current_score > track.last_peak_score:
        track.last_peak_score = current_score
        track.last_peak_time = now_s
    elif now_s - track.last_peak_time > 2.0:
        track.last_peak_score = current_score
        track.last_peak_time = now_s

    if bool(obs["downed"]):
        if track.down_since is None:
            track.down_since = now_s
        if bool(obs["motion_low"]):
            if track.immobile_since is None:
                track.immobile_since = now_s
        else:
            track.immobile_since = None
    else:
        track.down_since = None
        track.immobile_since = None

    if track.state == "normal":
        if current_score >= suspect_threshold or bool(obs["rapid_change"]):
            set_state(track, "suspected_fall", now_s)
    elif track.state == "suspected_fall":
        confirm_by_score = current_score >= confirm_threshold and confirmation_evidence
        confirm_by_postfall = (
            strong_downed
            and confirmation_evidence
            and recent_peak >= max(
                confirm_threshold * state_rules["postfall_confirm_ratio"],
                state_rules["postfall_confirm_floor"],
            )
        )
        confirm_by_persistence = (
            strong_downed
            and (now_s - track.state_since) >= state_rules["downed_persistence_seconds"]
            and recent_peak >= state_rules["persistence_confirm_score_floor"]
        )
        if confirm_by_score or confirm_by_postfall:
            set_state(track, "confirmed_fall", now_s)
            track.confirmed_fall_since = now_s
            track.red_latch_until = now_s + state_rules["red_latch_seconds"]
            track.recovery_candidate_since = None
            track.recovery_fail_count = 0
            just_confirmed = True
        elif confirm_by_persistence:
            set_state(track, "confirmed_fall", now_s)
            track.confirmed_fall_since = now_s
            track.red_latch_until = now_s + state_rules["red_latch_seconds"]
            track.recovery_candidate_since = None
            track.recovery_fail_count = 0
            just_confirmed = True
        elif now_s - track.state_since > state_rules["suspected_timeout_seconds"] and not bool(obs["downed"]):
            set_state(track, "normal", now_s)
    elif track.state == "confirmed_fall":
        if now_s - track.state_since >= state_rules["confirmed_to_monitor_seconds"]:
            set_state(track, "post_fall_monitoring", now_s)
    elif track.state in {"post_fall_monitoring", "recovery_watch"}:
        if bool(obs["downed"]):
            track.recovery_candidate_since = None
            set_state(track, "post_fall_monitoring", now_s)
        elif bool(obs["upright"]):
            if track.recovery_candidate_since is None:
                track.recovery_candidate_since = now_s
                set_state(track, "recovery_watch", now_s)
            elif now_s - track.recovery_candidate_since >= state_rules["recovery_confirm_seconds"] and now_s >= track.red_latch_until:
                set_state(track, "recovered", now_s)
                track.last_recovery_time = now_s
                track.recovery_time = now_s
                track.injury_observe_until = now_s + INJURY_RULES["observation"]["post_fall_observe_seconds"]
                track.recovery_candidate_since = None
        else:
            if track.recovery_candidate_since is not None and now_s - track.recovery_candidate_since > state_rules["recovery_fail_seconds"]:
                track.recovery_fail_count += 1
            track.recovery_candidate_since = None
            set_state(track, "post_fall_monitoring", now_s)
    elif track.state == "recovered":
        update_injury_assessment(track, now_s, obs)
        if track.injury_level == "I5":
            set_state(track, "emergency", now_s)
        elif track.injury_level == "I4":
            set_state(track, "needs_assistance", now_s)
        elif track.injury_level == "I3":
            set_state(track, "abnormal_recovery", now_s)
        elif track.injury_level == "I2":
            set_state(track, "injury_watch", now_s)
        elif now_s >= track.injury_observe_until and now_s - track.state_since > state_rules["recovered_reset_seconds"]:
            track.confirmed_fall_since = None
            track.red_latch_until = 0.0
            track.last_peak_score = current_score
            track.down_since = None
            track.immobile_since = None
            track.recovery_fail_count = 0
            track.recovery_time = None
            track.injury_observe_until = 0.0
            set_state(track, "normal", now_s)
        elif current_score >= suspect_threshold:
            set_state(track, "suspected_fall", now_s)
    elif track.state in {"injury_watch", "abnormal_recovery", "needs_assistance", "emergency"}:
        update_injury_assessment(track, now_s, obs)
        if track.injury_level == "I5":
            set_state(track, "emergency", now_s)
        elif track.injury_level == "I4":
            set_state(track, "needs_assistance", now_s)
        elif track.injury_level == "I3":
            set_state(track, "abnormal_recovery", now_s)
        elif track.injury_level == "I2":
            set_state(track, "injury_watch", now_s)
        elif now_s >= track.injury_observe_until:
            track.confirmed_fall_since = None
            track.red_latch_until = 0.0
            track.last_peak_score = current_score
            track.down_since = None
            track.immobile_since = None
            track.recovery_fail_count = 0
            track.recovery_time = None
            track.injury_observe_until = 0.0
            set_state(track, "normal", now_s)

    update_injury_assessment(track, now_s, obs)
    update_severity(track, now_s, obs)
    return just_confirmed


def state_color(state: str) -> tuple[int, int, int]:
    if state == "suspected_fall":
        return (0, 215, 255)
    if state in {"confirmed_fall", "post_fall_monitoring"}:
        return (0, 0, 255)
    if state == "recovery_watch":
        return (0, 140, 255)
    if state == "recovered":
        return (255, 200, 0)
    if state == "injury_watch":
        return (0, 165, 255)
    if state == "abnormal_recovery":
        return (0, 80, 255)
    if state in {"needs_assistance", "emergency"}:
        return (0, 0, 180)
    return (0, 255, 0)


def injury_advice(track: Track) -> str:
    if track.injury_level == "I5":
        return "紧急风险：立即呼叫现场人员或紧急联系人，并持续关注是否静止无响应。"
    if track.injury_level == "I4":
        return "重伤风险：立即安排人员到场协助，避免让目标人物自行移动。"
    if track.injury_level == "I3":
        return "中度受伤风险：疑似跛行或恢复异常，建议尽快人工查看并询问身体状况。"
    if track.injury_level == "I2":
        return "轻伤风险：继续观察，建议提醒管理员关注是否疼痛、崴脚或行动变慢。"
    if track.injury_level == "I1":
        return "轻微风险：已恢复但仍处于观察期，暂不需要紧急处理。"
    if track.state == "suspected_fall":
        return "疑似跌倒：继续观察，等待后续姿态和运动确认。"
    return "正常：无需处理。"


def track_event_record(track: Track, now_s: float, frame_idx: int, event_type: str, source: str, snapshot_path: str | None = None) -> dict:
    down_secs = 0.0 if track.down_since is None else max(0.0, now_s - track.down_since)
    recovery_delay = None
    if track.confirmed_fall_since is not None and track.recovery_time is not None:
        recovery_delay = max(0.0, track.recovery_time - track.confirmed_fall_since)
    box = [] if track.last_box is None else [float(x) for x in track.last_box.tolist()]
    return {
        "event_type": event_type,
        "source": source,
        "timestamp_s": float(now_s),
        "frame_idx": int(frame_idx),
        "track_id": int(track.track_id),
        "bbox": box,
        "state": track.state,
        "severity": track.severity,
        "fall_score": float(track.score),
        "scores": {
            "gru": float(track.gru_score),
            "hybrid": float(track.hybrid_score),
            "semantic": float(track.semantic_score),
            "posture": float(track.posture_score),
            "detector": float(track.detector_score),
        },
        "posture_label": track.posture_label,
        "observations": track.last_observations,
        "injury": {
            "level": track.injury_level,
            "state": track.injury_state,
            "score": float(track.injury_score),
            "reason": track.injury_reason,
            "advice": injury_advice(track),
            "limp_score": float(track.limp_score),
            "mobility_score": float(track.mobility_score),
            "stability_score": float(track.stability_score),
            "down_seconds": float(down_secs),
            "recovery_delay_seconds": recovery_delay,
            "observe_until_s": float(track.injury_observe_until),
        },
        "snapshot_path": snapshot_path,
    }


def write_event(event_file, record: dict) -> None:
    if event_file is None:
        return
    event_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    event_file.flush()


def maybe_save_snapshot(frame: np.ndarray, snapshot_dir: Path | None, track: Track, now_s: float, event_type: str) -> str | None:
    if snapshot_dir is None:
        return None
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"track{track.track_id}_{event_type}_{int(now_s * 1000):010d}.jpg"
    cv2.imwrite(str(path), frame)
    return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real-time fall monitoring from webcam or video.")
    parser.add_argument("--source", default="0", help="Webcam index or a video path.")
    parser.add_argument("--model-registry", default=str(Path(__file__).resolve().parents[1] / "configs" / "model_registry.yaml"))
    parser.add_argument("--alert-rules", default=str(Path(__file__).resolve().parents[1] / "configs" / "alert_rules.yaml"))
    parser.add_argument("--injury-rules", default=str(Path(__file__).resolve().parents[1] / "configs" / "injury_rules.yaml"))
    parser.add_argument("--profile", default=None)
    parser.add_argument("--pose-model", default="yolo11n-pose.pt")
    parser.add_argument("--gru-weights", default=str(Path(__file__).resolve().parents[1] / "weights" / "gru_pose_fall_v1.pt"))
    parser.add_argument("--hybrid-weights", default=str(Path(__file__).resolve().parents[1] / "weights" / "hybrid_tcn_transformer_v2_matchgru.pt"))
    parser.add_argument("--semantic-weights", default=str(Path(__file__).resolve().parents[1] / "weights" / "semantic_mix_falldb_v1.pt"))
    parser.add_argument("--posture-model", default=str(Path(__file__).resolve().parents[1] / "runs" / "yolo_posture_person_binary_cls_v1" / "weights" / "best.pt"))
    parser.add_argument("--fall-detector", default=None, help="Optional YOLO detection model trained with fall/fallen labels.")
    parser.add_argument("--fall-detector-imgsz", type=int, default=640)
    parser.add_argument("--fall-detector-conf", type=float, default=0.25)
    parser.add_argument("--fall-detector-iou", type=float, default=0.45)
    parser.add_argument("--pose-imgsz", type=int, default=640)
    parser.add_argument("--pose-conf", type=float, default=0.2)
    parser.add_argument("--pose-max-det", type=int, default=8)
    parser.add_argument("--posture-imgsz", type=int, default=320)
    parser.add_argument("--analysis-width", type=int, default=0, help="Resize frames before inference; <=0 keeps source size.")
    parser.add_argument("--process-every", type=int, default=1, help="Run inference every Nth frame for live streams.")
    parser.add_argument("--start-seconds", type=float, default=0.0, help="Start processing at this timestamp for file sources.")
    parser.add_argument("--end-seconds", type=float, default=0.0, help="Stop processing at this timestamp for file sources; <=0 means no limit.")
    parser.add_argument("--opencv-buffer-size", type=int, default=1)
    parser.add_argument("--pose-tracker", choices=["none", "botsort", "bytetrack"], default="none")
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, or CUDA index such as 0.")
    parser.add_argument("--half", action="store_true", help="Use half precision for YOLO models when running on CUDA.")
    parser.add_argument("--window-size", type=int, default=24)
    parser.add_argument("--threshold", type=float, default=0.45)
    parser.add_argument("--alert-hold", type=int, default=3)
    parser.add_argument("--gru-weight", type=float, default=0.3)
    parser.add_argument("--hybrid-weight", type=float, default=0.45)
    parser.add_argument("--semantic-weight", type=float, default=0.0)
    parser.add_argument("--posture-weight", type=float, default=0.25)
    parser.add_argument("--detector-weight", type=float, default=0.0)
    parser.add_argument("--enable-sound", action="store_true")
    parser.add_argument("--sound-cooldown", type=float, default=3.0)
    parser.add_argument("--repeat-sound-interval", type=float, default=10.0)
    parser.add_argument("--save-path", default=None)
    parser.add_argument("--event-log", default=None, help="Write JSONL status/alert events for system integration.")
    parser.add_argument("--snapshot-dir", default=None, help="Save alert snapshots for downstream review.")
    parser.add_argument("--status-log-interval", type=float, default=1.0)
    parser.add_argument("--no-display", action="store_true")
    args = parser.parse_args()

    merge_alert_rules(load_yaml(args.alert_rules))
    merge_injury_rules(load_yaml(args.injury_rules))

    registry = load_yaml(args.model_registry)
    profile = get_profile(registry, args.profile)
    profile_weights = profile.get("weights", {})
    models = registry.get("models", {})
    pose_entry = models.get("pose", {})
    gru_entry = models.get("gru_temporal", {})
    hybrid_entry = models.get("hybrid_temporal", {})
    semantic_entry = models.get("semantic_temporal", {})
    posture_entry = models.get("posture_risk", {})
    detector_entry = models.get("fall_detector", {})

    if args.pose_model == "yolo11n-pose.pt" and pose_entry:
        args.pose_model = str(existing_model_path(pose_entry) or args.pose_model)
    if args.gru_weights.endswith("gru_pose_fall_v1.pt") and gru_entry:
        args.gru_weights = str(existing_model_path(gru_entry) or args.gru_weights)
    if args.hybrid_weights.endswith("hybrid_tcn_transformer_v2_matchgru.pt") and hybrid_entry:
        args.hybrid_weights = str(existing_model_path(hybrid_entry) or args.hybrid_weights)
    if args.semantic_weights.endswith("semantic_mix_falldb_v1.pt") and semantic_entry:
        args.semantic_weights = str(existing_model_path(semantic_entry) or args.semantic_weights)
    if args.posture_model.endswith("best.pt") and posture_entry:
        args.posture_model = str(existing_model_path(posture_entry) or args.posture_model)
    if args.fall_detector is None and detector_entry.get("enabled", False):
        detector_path = existing_model_path(detector_entry)
        args.fall_detector = str(detector_path) if detector_path is not None and detector_path.exists() else None

    if args.threshold == 0.45 and "threshold" in profile:
        args.threshold = float(profile["threshold"])
    if args.alert_hold == 3 and "alert_hold" in profile:
        args.alert_hold = int(profile["alert_hold"])
    if args.gru_weight == 0.3 and "gru" in profile_weights:
        args.gru_weight = float(profile_weights["gru"])
    if args.hybrid_weight == 0.45 and "hybrid" in profile_weights:
        args.hybrid_weight = float(profile_weights["hybrid"])
    if args.semantic_weight == 0.0 and "semantic" in profile_weights:
        args.semantic_weight = float(profile_weights["semantic"])
    if args.posture_weight == 0.25 and "posture" in profile_weights:
        args.posture_weight = float(profile_weights["posture"])
    if args.detector_weight == 0.0 and "detector" in profile_weights:
        args.detector_weight = float(profile_weights["detector"])

    if args.device == "auto":
        torch_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        yolo_device: str | int | None = 0 if torch_device.type == "cuda" else "cpu"
    elif args.device.isdigit():
        torch_device = torch.device(f"cuda:{args.device}" if torch.cuda.is_available() else "cpu")
        yolo_device = int(args.device) if torch_device.type == "cuda" else "cpu"
    else:
        torch_device = torch.device(args.device if args.device == "cpu" or torch.cuda.is_available() else "cpu")
        yolo_device = args.device if torch_device.type == "cuda" else "cpu"
    yolo_half = bool(args.half and torch_device.type == "cuda")
    pose_model = YOLO(args.pose_model)
    gru_model, _ = build_model(Path(args.gru_weights), torch_device)
    hybrid_model = None
    if args.hybrid_weights and Path(args.hybrid_weights).exists():
        hybrid_model, _ = build_model(Path(args.hybrid_weights), torch_device)
    semantic_model = None
    if args.semantic_weights and Path(args.semantic_weights).exists():
        semantic_model, _ = build_model(Path(args.semantic_weights), torch_device)
    posture_model = YOLO(args.posture_model) if args.posture_model and Path(args.posture_model).exists() else None
    fall_detector_model = YOLO(args.fall_detector) if args.fall_detector and Path(args.fall_detector).exists() else None
    fall_labels = set(detector_entry.get("fall_labels", ["fall", "fallen", "lying"]))
    detector_imgsz = int(detector_entry.get("imgsz", args.fall_detector_imgsz))
    detector_conf = float(detector_entry.get("conf", args.fall_detector_conf))
    detector_iou = float(detector_entry.get("iou", args.fall_detector_iou))

    source = int(args.source) if args.source.isdigit() else args.source
    if isinstance(source, str) and source.lower().startswith("rtsp://"):
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|fflags;nobuffer|max_delay;0")
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open source: {args.source}")
    if args.opencv_buffer_size >= 0:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, max(0, args.opencv_buffer_size))
    is_live_source = isinstance(source, int) or (
        isinstance(source, str) and source.lower().startswith(("rtsp://", "http://", "https://"))
    )
    if not is_live_source and args.start_seconds > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, args.start_seconds) * 1000.0)

    writer = None
    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    fourcc = cv2.VideoWriter_fourcc(*"mp4v") if args.save_path else None

    event_file = None
    if args.event_log:
        event_path = Path(args.event_log)
        event_path.parent.mkdir(parents=True, exist_ok=True)
        event_file = event_path.open("a", encoding="utf-8")
    snapshot_dir = Path(args.snapshot_dir) if args.snapshot_dir else None

    tracks: dict[int, Track] = {}
    next_id = 1
    last_sound_time = 0.0
    start_monotonic = time.monotonic()
    frame_idx = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1
        if is_live_source and args.process_every > 1 and frame_idx % args.process_every != 0:
            continue
        if args.analysis_width > 0 and frame.shape[1] > args.analysis_width:
            scale = args.analysis_width / float(frame.shape[1])
            frame = cv2.resize(frame, (args.analysis_width, max(1, int(frame.shape[0] * scale))), interpolation=cv2.INTER_AREA)
        if is_live_source:
            now_s = time.monotonic() - start_monotonic
        else:
            pos_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
            now_s = (
                float(pos_msec / 1000.0)
                if pos_msec and pos_msec > 0
                else max(0.0, args.start_seconds) + float(frame_idx / max(fps, 1e-6))
            )
            if args.end_seconds > 0 and now_s > args.end_seconds:
                break

        if args.pose_tracker == "none":
            result = pose_model.predict(
                frame,
                verbose=False,
                imgsz=args.pose_imgsz,
                conf=args.pose_conf,
                max_det=args.pose_max_det,
                device=yolo_device,
                half=yolo_half,
            )[0]
            detections = extract_people(result)
            next_id = update_tracks(tracks, detections, next_id)
        else:
            result = pose_model.track(
                frame,
                persist=True,
                tracker=f"{args.pose_tracker}.yaml",
                verbose=False,
                imgsz=args.pose_imgsz,
                conf=args.pose_conf,
                max_det=args.pose_max_det,
                device=yolo_device,
                half=yolo_half,
            )[0]
            update_tracks_from_tracker(tracks, extract_tracked_people(result))
            if tracks:
                next_id = max(next_id, max(tracks.keys()) + 1)
        next_id = score_fall_detector_for_tracks(
            frame,
            tracks,
            fall_detector_model,
            fall_labels,
            detector_imgsz,
            detector_conf,
            detector_iou,
            yolo_device,
            yolo_half,
            next_id,
            now_s,
        )

        for track in tracks.values():
            if track.last_box is None:
                continue
            x1, y1, x2, y2 = track.last_box.astype(int)
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(frame.shape[1], x2)
            y2 = min(frame.shape[0], y2)
            crop = frame[y1:y2, x1:x2]
            posture_label, posture_score = classify_posture(
                crop,
                posture_model,
                imgsz=args.posture_imgsz,
                device=yolo_device,
                half=yolo_half,
            )
            track.posture_label = posture_label
            if track.detector_only:
                posture_score = max(posture_score, track.detector_score)
                track.posture_label = "detector_fallen"
            track.posture_score = posture_score
            track.posture_history.append(posture_score)
            if not track.detector_only:
                track.gru_score = score_track_gru(track, gru_model, torch_device)
            if hybrid_model is not None and not track.detector_only:
                track.hybrid_score = score_track_hybrid(track, hybrid_model, torch_device)
            if semantic_model is not None and not track.detector_only:
                track.semantic_score = score_track_semantic(track, semantic_model, torch_device)
            combined = (
                track.gru_score * args.gru_weight
                + track.hybrid_score * args.hybrid_weight
                + track.semantic_score * args.semantic_weight
                + posture_score * args.posture_weight
                + track.detector_score * args.detector_weight
            )
            if track.detector_only:
                detector_confirm_floor = 0.36 if track.detector_hits >= 2 else 0.0
                combined = max(combined, detector_confirm_floor, track.detector_score * 0.85)
            track.score = float(max(0.0, min(1.0, combined)))
            track.score_history.append(track.score)
            prev_state = track.state
            prev_injury_level = track.injury_level
            just_confirmed = update_track_state(track, now_s, args.threshold)

            box = track.last_box.astype(int)
            is_alert = track.state in {"confirmed_fall", "post_fall_monitoring", "recovery_watch", "injury_watch", "abnormal_recovery", "needs_assistance", "emergency"}
            state_changed = track.state != prev_state or track.injury_level != prev_injury_level
            should_periodic_log = is_alert and now_s - track.last_status_log_time >= args.status_log_interval
            if just_confirmed or state_changed or should_periodic_log:
                event_type = "fall_confirmed" if just_confirmed else ("state_changed" if state_changed else "status")
                snapshot_path = maybe_save_snapshot(frame, snapshot_dir, track, now_s, event_type) if (just_confirmed or state_changed) else None
                write_event(event_file, track_event_record(track, now_s, frame_idx, event_type, str(args.source), snapshot_path))
                track.last_status_log_time = now_s
                track.last_event_state = track.state
                track.last_event_injury_level = track.injury_level
            if just_confirmed and args.enable_sound:
                now = time.monotonic()
                if now - last_sound_time >= args.sound_cooldown:
                    play_alert_sound()
                    last_sound_time = now
                    track.last_sound_time = now_s
            elif (
                args.enable_sound
                and is_alert
                and track.severity in {"L3", "L4"}
                and now_s - track.last_sound_time >= args.repeat_sound_interval
            ):
                now = time.monotonic()
                if now - last_sound_time >= args.sound_cooldown:
                    play_alert_sound()
                    last_sound_time = now
                    track.last_sound_time = now_s
            track.last_alerted = is_alert
            color = state_color(track.state)
            down_secs = 0.0 if track.down_since is None else max(0.0, now_s - track.down_since)
            label = (
                f"id={track.track_id} state={track.state} sev={track.severity} "
                f"fall={track.score:.2f} inj={track.injury_level}:{track.injury_score:.2f} "
                f"limp={track.limp_score:.2f} down={down_secs:.1f}s pose={track.posture_label}"
            )
            cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), color, 2)
            cv2.putText(frame, label, (box[0], max(20, box[1] - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            if is_alert:
                cv2.putText(
                    frame,
                    f"ALERT {track.severity} {track.injury_level} {track.injury_reason}",
                    (box[0], min(frame.shape[0] - 12, box[3] + 22)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    color,
                    2,
                )

        if args.save_path and writer is None:
            writer = cv2.VideoWriter(args.save_path, fourcc, fps, (frame.shape[1], frame.shape[0]))
        if writer is not None:
            writer.write(frame)

        if not args.no_display:
            cv2.imshow("Fall Monitor", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord("q"):
                break

    cap.release()
    if writer is not None:
        writer.release()
    if event_file is not None:
        event_file.close()
    if not args.no_display:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
