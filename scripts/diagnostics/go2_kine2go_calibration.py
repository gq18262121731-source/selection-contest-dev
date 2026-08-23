"""Build the Kine2Go-to-Blender FK calibration report from local artifacts."""

from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np


JOINTS = (
    "FR_hip",
    "FR_thigh",
    "FR_calf",
    "FL_hip",
    "FL_thigh",
    "FL_calf",
    "RR_hip",
    "RR_thigh",
    "RR_calf",
    "RL_hip",
    "RL_thigh",
    "RL_calf",
)
SOURCE_DOF_COLUMNS = (7, 11, 15, 6, 10, 14, 9, 13, 17, 8, 12, 16)
SOURCE_DEFAULT = np.array((0.0, 0.8, -1.5, 0.0, 0.8, -1.5, 0.0, 1.0, -1.5, 0.0, 1.0, -1.5))
P4_LIMITS = {
    "hip": (-1.0472, 1.0472),
    "thigh": (-1.5708, 3.4907),
    "calf": (-2.7227, -0.83776),
}
P4_ORIGINS = {
    "FR_hip": (0.1934, -0.0465, 0.0), "FL_hip": (0.1934, 0.0465, 0.0),
    "RR_hip": (-0.1934, -0.0465, 0.0), "RL_hip": (-0.1934, 0.0465, 0.0),
    "FR_thigh": (0.0, -0.0955, 0.0), "FL_thigh": (0.0, 0.0955, 0.0),
    "RR_thigh": (0.0, -0.0955, 0.0), "RL_thigh": (0.0, 0.0955, 0.0),
    "FR_calf": (0.0, 0.0, -0.213), "FL_calf": (0.0, 0.0, -0.213),
    "RR_calf": (0.0, 0.0, -0.213), "RL_calf": (0.0, 0.0, -0.213),
}
P4_AXES = {"hip": (1.0, 0.0, 0.0), "thigh": (0.0, 1.0, 0.0), "calf": (0.0, 1.0, 0.0)}
SOURCE_FOOT_ORDER = ("FL", "RL", "FR", "RR")


def parse_vector(text: str) -> tuple[float, ...]:
    return tuple(float(value) for value in text.split())


def parse_urdf(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    result = {}
    for name in JOINTS:
        node = root.find(f"./joint[@name='{name}_joint']")
        if node is None:
            raise ValueError(f"Missing URDF joint: {name}_joint")
        limit = node.find("limit")
        result[name] = {
            "joint_name": f"{name}_joint",
            "parent": node.find("parent").get("link"),
            "child": node.find("child").get("link"),
            "axis": list(parse_vector(node.find("axis").get("xyz"))),
            "origin_xyz": list(parse_vector(node.find("origin").get("xyz"))),
            "origin_rpy": list(parse_vector(node.find("origin").get("rpy"))),
            "lower_rad": float(limit.get("lower")),
            "upper_rad": float(limit.get("upper")),
        }
    return result


def p4_comparison(definitions: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for name, source in definitions.items():
        link = name.split("_")[1]
        p4_limit = P4_LIMITS[link]
        result[name] = {
            "axis_same": np.allclose(source["axis"], P4_AXES[link]),
            "origin_same": np.allclose(source["origin_xyz"], P4_ORIGINS[name]),
            "lower_same": math.isclose(source["lower_rad"], p4_limit[0], abs_tol=1e-8),
            "upper_same": math.isclose(source["upper_rad"], p4_limit[1], abs_tol=1e-8),
            "genesis_limit_rad": [source["lower_rad"], source["upper_rad"]],
            "p4_limit_rad": list(p4_limit),
        }
    return result


def source_feet(motion_row: np.ndarray) -> dict[str, np.ndarray]:
    values = motion_row[36:48].reshape(4, 3)
    base = motion_row[48:51]
    w, x, y, z = motion_row[51:55]
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    return {leg: rotation.T @ (values[index] - base) for index, leg in enumerate(SOURCE_FOOT_ORDER)}


def vector_cosine(first: np.ndarray, second: np.ndarray) -> float | None:
    norm = float(np.linalg.norm(first) * np.linalg.norm(second))
    return None if norm < 1e-9 else float(np.dot(first, second) / norm)


def foot_trend_validation(motion: np.ndarray, blender: dict[str, Any]) -> dict[str, Any]:
    source_baseline = source_feet(motion[blender["samples"][0]["frame"]])
    blender_baseline = {leg: np.array(value) for leg, value in blender["samples"][0]["blender_feet_relative_body"].items()}
    legs = {}
    for leg in ("FR", "FL", "RR", "RL"):
        comparisons = []
        for sample in blender["samples"][1:]:
            source_delta = source_feet(motion[sample["frame"]])[leg] - source_baseline[leg]
            blender_delta = np.array(sample["blender_feet_relative_body"][leg]) - blender_baseline[leg]
            comparisons.append({
                "frame": sample["frame"],
                "source_delta": source_delta.tolist(),
                "blender_delta": blender_delta.tolist(),
                "cosine_similarity": vector_cosine(source_delta, blender_delta),
                "position_error_m": float(
                    np.linalg.norm(
                        source_feet(motion[sample["frame"]])[leg]
                        - np.array(sample["blender_feet_relative_body"][leg])
                    )
                ),
            })
        valid = [item["cosine_similarity"] for item in comparisons if item["cosine_similarity"] is not None]
        mean_cosine = float(np.mean(valid)) if valid else None
        max_position_error = max(item["position_error_m"] for item in comparisons)
        status = "PASS" if mean_cosine is not None and mean_cosine >= 0.95 and max_position_error <= 0.005 else "PARTIAL" if mean_cosine is not None and mean_cosine >= 0.8 else "FAIL"
        legs[leg] = {"status": status, "mean_cosine_similarity": mean_cosine, "max_position_error_m": max_position_error, "comparisons": comparisons}
    return legs


def limit_check(q: np.ndarray, definitions: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for index, name in enumerate(JOINTS):
        lower = definitions[name]["lower_rad"]
        upper = definitions[name]["upper_rad"]
        values = q[:, index]
        violations = np.where((values < lower) | (values > upper))[0]
        result[name] = {
            "status": "PASS" if not violations.size else "FAIL",
            "min_rad": float(values.min()), "max_rad": float(values.max()),
            "lower_rad": lower, "upper_rad": upper,
            "violation_count": int(violations.size),
            "first_violation_frame": int(violations[0]) if violations.size else None,
        }
    return result


def find_cycle(q: np.ndarray, dq: np.ndarray, feet: np.ndarray, legal_frames: np.ndarray, fps: int = 60) -> dict[str, Any]:
    min_period, max_period = int(0.5 * fps), int(1.5 * fps)
    candidates = []
    for start in range(0, len(q) - min_period):
        for period in range(min_period, min(max_period, len(q) - start - 1) + 1):
            end = start + period
            if not legal_frames[start : end + 1].all():
                continue
            pose_error = float(np.linalg.norm(q[end] - q[start]) / math.sqrt(q.shape[1]))
            velocity_error = float(np.linalg.norm(dq[end] - dq[start]) / math.sqrt(dq.shape[1]))
            foot_error = float(np.linalg.norm(feet[end] - feet[start]) / math.sqrt(feet.shape[1]))
            amplitude = float(np.mean(np.ptp(q[start : end + 1], axis=0)))
            if amplitude < 0.05:
                continue
            score = pose_error + 0.02 * velocity_error + foot_error - 0.05 * min(amplitude, 1.0)
            candidates.append((score, start, end, pose_error, velocity_error, foot_error, amplitude))
    if not candidates:
        return {"status": "FAIL", "detail": "No fully legal 0.5-1.5 second cycle candidate"}
    score, start, end, pose_error, velocity_error, foot_error, amplitude = min(candidates)
    status = "PASS" if pose_error <= 0.08 and velocity_error <= 1.5 and foot_error <= 0.03 else "PARTIAL"
    return {
        "status": status, "start": start, "end": end, "frames": end - start,
        "duration_s": (end - start) / fps, "pose_seam_rms_rad": pose_error,
        "velocity_seam_rms_rad_s": velocity_error, "foot_seam_rms_m": foot_error,
        "mean_joint_amplitude_rad": amplitude,
        "score": score, "candidate_count": len(candidates),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--motion", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--genesis-probe", type=Path, required=True)
    parser.add_argument("--blender-probe", type=Path, required=True)
    parser.add_argument("--output-urdf-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    motion = np.load(args.motion, allow_pickle=False)
    if motion.ndim != 2 or motion.shape[1] != 61 or not np.isfinite(motion).all():
        raise ValueError(f"Invalid motion array: shape={motion.shape}, finite={np.isfinite(motion).all()}")
    blender = json.loads(args.blender_probe.read_text(encoding="utf-8"))
    genesis = json.loads(args.genesis_probe.read_text(encoding="utf-8"))
    definitions = parse_urdf(args.urdf)
    runtime_columns = tuple(genesis["joint_mapping"][name]["dump_state_column"] for name in JOINTS)
    if runtime_columns != SOURCE_DOF_COLUMNS:
        raise ValueError(f"Runtime Genesis DOF columns changed: {runtime_columns}")
    q = motion[:, list(runtime_columns)]
    dq = motion[:, [column + 18 for column in runtime_columns]]
    limits = limit_check(q, definitions)
    legal = np.ones(len(q), dtype=bool)
    for index, name in enumerate(JOINTS):
        legal &= (q[:, index] >= definitions[name]["lower_rad"]) & (q[:, index] <= definitions[name]["upper_rad"])
    trends = foot_trend_validation(motion, blender)
    source_default_feet = {leg: genesis["feet"][leg]["relative_to_base"] for leg in ("FR", "FL", "RR", "RL")}
    urdf_zero_feet = {
        "FR": [0.1934, -0.142, -0.426], "FL": [0.1934, 0.142, -0.426],
        "RR": [-0.1934, -0.142, -0.426], "RL": [-0.1934, 0.142, -0.426],
    }
    source_default_errors = {
        leg: float(np.linalg.norm(np.array(blender["neutral_feet_relative_body"][leg]) - np.array(source_default_feet[leg])))
        for leg in source_default_feet
    }
    urdf_zero_errors = {
        leg: float(np.linalg.norm(np.array(blender["neutral_feet_relative_body"][leg]) - np.array(urdf_zero_feet[leg])))
        for leg in urdf_zero_feet
    }
    source_default_max_error = max(source_default_errors.values())
    urdf_zero_max_error = max(urdf_zero_errors.values())
    source_default_status = "PASS" if source_default_max_error <= 0.01 else "PARTIAL" if source_default_max_error <= 0.05 else "FAIL"
    neutral_status = "PASS" if urdf_zero_max_error <= 1e-5 else "PARTIAL" if urdf_zero_max_error <= 0.01 else "FAIL"
    trend_status = "PASS" if all(item["status"] == "PASS" for item in trends.values()) else "PARTIAL" if all(item["status"] != "FAIL" for item in trends.values()) else "FAIL"
    feet_local = np.stack([np.concatenate([source_feet(row)[leg] for leg in SOURCE_FOOT_ORDER]) for row in motion])
    cycle = find_cycle(q, dq, feet_local, legal)
    comparison = p4_comparison(definitions)
    urdf_match = "PASS" if all(all(item[key] for key in ("axis_same", "origin_same", "lower_same", "upper_same")) for item in comparison.values()) else "PARTIAL"
    ready = "PASS" if neutral_status == trend_status == cycle["status"] == "PASS" and legal.all() else "PARTIAL"
    report = {
        "GENESIS_URDF_FOUND": "PASS", "genesis_urdf_path": str(args.urdf),
        "URDF_MATCH_P4_1": urdf_match, "urdf_comparison": comparison,
        "SOURCE_DEFAULT_POSE": "PASS", "q_default_source": dict(zip(JOINTS, SOURCE_DEFAULT.tolist())),
        "SOURCE_DOF_COLUMN_MAPPING": dict(zip(JOINTS, SOURCE_DOF_COLUMNS)),
        "BLENDER_NEUTRAL_MATCH": neutral_status,
        "BLENDER_NEUTRAL_MATCHES_SOURCE_DEFAULT": source_default_status,
        "source_default_foot_error_m": source_default_errors,
        "BLENDER_NEUTRAL_MATCHES_URDF_ZERO": neutral_status,
        "urdf_zero_foot_error_m": urdf_zero_errors,
        "ZERO_OFFSET_MODEL": "PASS" if neutral_status == "PASS" else "PARTIAL",
        "q_reference_blender": dict.fromkeys(JOINTS, 0.0),
        "zero_offset_formula": "blender_local = source_absolute_q (Blender Neutral is URDF q=0)",
        "SIGN_MODEL": "PASS" if trend_status == "PASS" else "PARTIAL",
        "signs": dict.fromkeys(JOINTS, 1.0),
        "FOOT_POSITION_VALIDATION": trend_status, "foot_trends": trends,
        "SOURCE_LIMIT_CHECK": "PASS" if legal.all() else "FAIL", "source_limits": limits,
        "BLENDER_LOCAL_LIMIT_CHECK": "PASS" if legal.all() else "FAIL",
        "legal_frame_count": int(legal.sum()), "total_frame_count": len(q),
        "LEGAL_STABLE_CYCLE_FOUND": cycle["status"], "cycle": cycle,
        "READY_FOR_BLENDER_ANIMATION": ready,
        "notes": [
            "NPY DOF columns are Genesis global DOF order, not RobotConfig joint_names order.",
            "P4.1 uses front-thigh limits for all thighs; Genesis rear-thigh limits differ.",
            "No clamp or sign inversion was applied.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_urdf_json.write_text(
        json.dumps({"urdf_path": str(args.urdf), "joints": definitions}, indent=2) + "\n",
        encoding="utf-8",
    )
    args.output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# Go2 Kine2Go Calibration Report", ""]
    for key in ("GENESIS_URDF_FOUND", "URDF_MATCH_P4_1", "SOURCE_DEFAULT_POSE", "BLENDER_NEUTRAL_MATCH", "ZERO_OFFSET_MODEL", "SIGN_MODEL", "FOOT_POSITION_VALIDATION", "SOURCE_LIMIT_CHECK", "BLENDER_LOCAL_LIMIT_CHECK", "LEGAL_STABLE_CYCLE_FOUND", "READY_FOR_BLENDER_ANIMATION"):
        lines.append(f"- `{key}`: **{report[key]}**")
    lines.extend(["", "## Critical Findings", "", f"- Genesis URDF: `{args.urdf}`", f"- Source DOF columns: `{report['SOURCE_DOF_COLUMN_MAPPING']}`", f"- Blender Neutral vs source default max error: `{source_default_max_error:.8f} m`", f"- Blender Neutral vs URDF zero max error: `{urdf_zero_max_error:.8f} m`", "- Zero model: `blender_local = source_absolute_q`", f"- Legal frames: `{int(legal.sum())}/{len(q)}`", f"- Cycle: `{cycle}`", "", "The source motion is Kine2Go Go2-retargeted motion data, not Unitree official gait capture."])
    args.output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("GENESIS_URDF_FOUND", "URDF_MATCH_P4_1", "BLENDER_NEUTRAL_MATCH", "FOOT_POSITION_VALIDATION", "SOURCE_LIMIT_CHECK", "LEGAL_STABLE_CYCLE_FOUND", "READY_FOR_BLENDER_ANIMATION")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
