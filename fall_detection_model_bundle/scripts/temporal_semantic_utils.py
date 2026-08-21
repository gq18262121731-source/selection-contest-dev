from __future__ import annotations

import math
from pathlib import Path

import numpy as np


def _safe_norm(vec: np.ndarray) -> float:
    return float(np.linalg.norm(vec)) + 1e-6


def _angle_from_vertical(vec: np.ndarray) -> float:
    # 0 means upright, magnitude grows as the trunk rotates toward horizontal.
    return float(np.arctan2(vec[0], -vec[1]) / np.pi)


def semantic_features_from_pose_sequence(keypoints: np.ndarray, boxes: np.ndarray | None = None) -> np.ndarray:
    features = []
    prev = None
    for i, kp in enumerate(keypoints):
        xy = kp[:, :2].astype(np.float32)
        conf = kp[:, 2].astype(np.float32)

        def choose_point(primary: list[int], fallback: list[int]) -> np.ndarray:
            for idx in primary:
                if conf[idx] > 0:
                    return xy[idx]
            pts = [xy[idx] for idx in fallback if conf[idx] > 0]
            if pts:
                return np.mean(pts, axis=0)
            return np.zeros(2, dtype=np.float32)

        left_hip = choose_point([11], [12])
        right_hip = choose_point([12], [11])
        hip_center = np.mean([left_hip, right_hip], axis=0)
        left_shoulder = choose_point([5], [6])
        right_shoulder = choose_point([6], [5])
        shoulder_center = np.mean([left_shoulder, right_shoulder], axis=0)
        nose = choose_point([0], [1, 2, 3, 4, 5, 6])
        left_knee = choose_point([13], [14])
        right_knee = choose_point([14], [13])
        knee_center = np.mean([left_knee, right_knee], axis=0)

        torso = shoulder_center - hip_center
        trunk_len_raw = float(np.linalg.norm(torso))
        if trunk_len_raw < 5.0:
            features.append(np.zeros(14, dtype=np.float32))
            prev = None
            continue
        trunk_len = trunk_len_raw + 1e-6
        all_pts = np.stack([left_hip, right_hip, shoulder_center, nose, left_knee, right_knee], axis=0)
        x_span = float(all_pts[:, 0].max() - all_pts[:, 0].min()) / trunk_len
        y_span = float(all_pts[:, 1].max() - all_pts[:, 1].min()) / trunk_len
        torso_angle = _angle_from_vertical(torso)
        body_height = float(knee_center[1] - nose[1]) / trunk_len
        head_to_hip_y = float(nose[1] - hip_center[1]) / trunk_len
        knee_to_hip_y = float(knee_center[1] - hip_center[1]) / trunk_len
        hip_width = float(abs(left_hip[0] - right_hip[0])) / trunk_len
        aspect_proxy = x_span / max(y_span, 1e-3)
        box_aspect = 0.0
        if boxes is not None and i < len(boxes):
            x1, y1, x2, y2 = boxes[i]
            box_aspect = float(max(x2 - x1, 1.0) / max(y2 - y1, 1.0))

        current = {
            "hip": hip_center,
            "nose": nose,
            "angle": torso_angle,
            "height": body_height,
        }
        if prev is None:
            hip_v = np.zeros(2, dtype=np.float32)
            head_vy = 0.0
            angle_v = 0.0
            height_v = 0.0
        else:
            hip_v = (current["hip"] - prev["hip"]) / trunk_len
            head_vy = float((current["nose"][1] - prev["nose"][1]) / trunk_len)
            angle_v = float(current["angle"] - prev["angle"])
            height_v = float(current["height"] - prev["height"])
        prev = current

        frame_feat = np.asarray(
            [
                torso_angle,
                body_height,
                head_to_hip_y,
                knee_to_hip_y,
                hip_width,
                x_span,
                aspect_proxy,
                box_aspect,
                float(hip_v[0]),
                float(hip_v[1]),
                head_vy,
                angle_v,
                height_v,
                float(conf.mean()),
            ],
            dtype=np.float32,
        )
        features.append(frame_feat)
    return np.asarray(features, dtype=np.float32)


def parse_falldb_skeleton(path: Path) -> np.ndarray:
    rows = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        header = f.readline()
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(";")
            values = [float(x) for x in parts if x != ""]
            if len(values) < 1 + 7 * 4:
                continue
            rows.append(values)
    return np.asarray(rows, dtype=np.float32)


def semantic_features_from_falldb_rows(rows: np.ndarray) -> np.ndarray:
    features = []
    prev = None
    for row in rows:
        # FrameNr + 7 joints * (x, y, z, conf)
        vals = row[1:]
        joints = vals.reshape(7, 4)
        invalid = np.abs(joints[:, :3]) > 1e6
        if invalid.any():
            joints[invalid.any(axis=1), :3] = 0.0
            joints[invalid.any(axis=1), 3] = 0.0
        hip_left = joints[0, :2]
        hip_right = joints[1, :2]
        spine = joints[2, :2]
        shoulder_center = joints[3, :2]
        head = joints[4, :2]
        knee_left = joints[5, :2]
        knee_right = joints[6, :2]

        def valid_or_zero(pt: np.ndarray, conf: float) -> np.ndarray:
            return pt if conf > 0 else np.zeros(2, dtype=np.float32)

        hip_left = valid_or_zero(hip_left, joints[0, 3])
        hip_right = valid_or_zero(hip_right, joints[1, 3])
        spine = valid_or_zero(spine, joints[2, 3])
        shoulder_center = valid_or_zero(shoulder_center, joints[3, 3])
        head = valid_or_zero(head, joints[4, 3])
        knee_left = valid_or_zero(knee_left, joints[5, 3])
        knee_right = valid_or_zero(knee_right, joints[6, 3])
        hip_center = np.mean([hip_left, hip_right], axis=0)
        knee_center = np.mean([knee_left, knee_right], axis=0)

        torso = shoulder_center - hip_center
        trunk_len_raw = float(np.linalg.norm(torso))
        if trunk_len_raw < 100.0:
            features.append(np.zeros(14, dtype=np.float32))
            prev = None
            continue
        trunk_len = trunk_len_raw + 1e-6
        all_pts = np.stack([hip_left, hip_right, spine, shoulder_center, head, knee_left, knee_right], axis=0)
        x_span = float(all_pts[:, 0].max() - all_pts[:, 0].min()) / trunk_len
        y_span = float(all_pts[:, 1].max() - all_pts[:, 1].min()) / trunk_len
        torso_angle = _angle_from_vertical(torso)
        body_height = float(knee_center[1] - head[1]) / trunk_len
        head_to_hip_y = float(head[1] - hip_center[1]) / trunk_len
        knee_to_hip_y = float(knee_center[1] - hip_center[1]) / trunk_len
        hip_width = float(abs(hip_left[0] - hip_right[0])) / trunk_len
        aspect_proxy = x_span / max(y_span, 1e-3)

        current = {"hip": hip_center, "head": head, "angle": torso_angle, "height": body_height}
        if prev is None:
            hip_v = np.zeros(2, dtype=np.float32)
            head_vy = 0.0
            angle_v = 0.0
            height_v = 0.0
        else:
            hip_v = (current["hip"] - prev["hip"]) / trunk_len
            head_vy = float((current["head"][1] - prev["head"][1]) / trunk_len)
            angle_v = float(current["angle"] - prev["angle"])
            height_v = float(current["height"] - prev["height"])
        prev = current

        conf_mean = float(joints[:, 3].mean())
        frame_feat = np.asarray(
            [
                torso_angle,
                body_height,
                head_to_hip_y,
                knee_to_hip_y,
                hip_width,
                x_span,
                aspect_proxy,
                aspect_proxy,
                float(hip_v[0]),
                float(hip_v[1]),
                head_vy,
                angle_v,
                height_v,
                conf_mean,
            ],
            dtype=np.float32,
        )
        features.append(frame_feat)
    return np.asarray(features, dtype=np.float32)
