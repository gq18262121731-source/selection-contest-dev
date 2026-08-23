from __future__ import annotations

import math

import numpy as np

from scripts.diagnostics.go2_kine2go_calibration import (
    JOINTS,
    SOURCE_DOF_COLUMNS,
    find_cycle,
    source_feet,
)


def test_genesis_dump_columns_are_not_naive_contiguous_joint_order() -> None:
    assert dict(zip(JOINTS, SOURCE_DOF_COLUMNS)) == {
        "FR_hip": 7,
        "FR_thigh": 11,
        "FR_calf": 15,
        "FL_hip": 6,
        "FL_thigh": 10,
        "FL_calf": 14,
        "RR_hip": 9,
        "RR_thigh": 13,
        "RR_calf": 17,
        "RL_hip": 8,
        "RL_thigh": 12,
        "RL_calf": 16,
    }


def test_source_feet_are_transformed_from_world_to_body_local() -> None:
    row = np.zeros(61, dtype=np.float32)
    row[48:51] = (1.0, 2.0, 3.0)
    angle = math.pi / 2
    row[51:55] = (math.cos(angle / 2), 0.0, 0.0, math.sin(angle / 2))
    body_local = np.array(
        [
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (-1.0, 0.0, 0.0),
            (0.0, -1.0, 0.0),
        ]
    )
    rotation = np.array(((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)))
    row[36:48] = (body_local @ rotation.T + row[48:51]).reshape(-1)

    feet = source_feet(row)

    assert np.allclose(feet["FL"], body_local[0], atol=1e-6)
    assert np.allclose(feet["RL"], body_local[1], atol=1e-6)
    assert np.allclose(feet["FR"], body_local[2], atol=1e-6)
    assert np.allclose(feet["RR"], body_local[3], atol=1e-6)


def test_cycle_detector_finds_legal_periodic_motion() -> None:
    frames = np.arange(181)
    phase = 2 * np.pi * frames / 60
    q = np.stack([0.2 * np.sin(phase + index * 0.1) for index in range(12)], axis=1)
    dq = np.stack([0.2 * 2 * np.pi * np.cos(phase + index * 0.1) for index in range(12)], axis=1)
    feet = np.stack([0.05 * np.sin(phase + index * 0.2) for index in range(12)], axis=1)

    cycle = find_cycle(q, dq, feet, np.ones(len(frames), dtype=bool))

    assert cycle["status"] == "PASS"
    assert 30 <= cycle["frames"] <= 90
    assert cycle["pose_seam_rms_rad"] <= 0.08
    assert cycle["foot_seam_rms_m"] <= 0.03


def test_cycle_detector_rejects_all_illegal_frames() -> None:
    q = np.zeros((100, 12))
    dq = np.zeros((100, 12))
    feet = np.zeros((100, 12))

    cycle = find_cycle(q, dq, feet, np.zeros(100, dtype=bool))

    assert cycle["status"] == "FAIL"
