# Go2 Kine2Go Calibration Report

- `GENESIS_URDF_FOUND`: **PASS**
- `URDF_MATCH_P4_1`: **PARTIAL**
- `SOURCE_DEFAULT_POSE`: **PASS**
- `BLENDER_NEUTRAL_MATCH`: **PASS**
- `ZERO_OFFSET_MODEL`: **PASS**
- `SIGN_MODEL`: **PASS**
- `FOOT_POSITION_VALIDATION`: **PASS**
- `SOURCE_LIMIT_CHECK`: **PASS**
- `BLENDER_LOCAL_LIMIT_CHECK`: **PASS**
- `LEGAL_STABLE_CYCLE_FOUND`: **PASS**
- `READY_FOR_BLENDER_ANIMATION`: **PASS**

## Critical Findings

- Genesis URDF: `C:\Users\13010\Downloads\kine2go-pipeline-master\.venv\Lib\site-packages\genesis\assets\urdf\go2\urdf\go2.urdf`
- Source DOF columns: `{'FR_hip': 7, 'FR_thigh': 11, 'FR_calf': 15, 'FL_hip': 6, 'FL_thigh': 10, 'FL_calf': 14, 'RR_hip': 9, 'RR_thigh': 13, 'RR_calf': 17, 'RL_hip': 8, 'RL_thigh': 12, 'RL_calf': 16}`
- Blender Neutral vs source default max error: `0.14601535 m`
- Blender Neutral vs URDF zero max error: `0.00000001 m`
- Zero model: `blender_local = source_absolute_q`
- Legal frames: `479/479`
- Cycle: `{'status': 'PASS', 'start': 402, 'end': 443, 'frames': 41, 'duration_s': 0.6833333333333333, 'pose_seam_rms_rad': 0.013432448729872704, 'velocity_seam_rms_rad_s': 0.3868210017681122, 'foot_seam_rms_m': 0.003334618639200926, 'mean_joint_amplitude_rad': 0.5343134999275208, 'score': -0.002212187591940168, 'candidate_count': 25559}`

The source motion is Kine2Go Go2-retargeted motion data, not Unitree official gait capture.
