# OpenMMLab Candidate Plan

The production path remains Ultralytics-compatible. OpenMMLab candidates are
used to establish a stronger pose/action-recognition upper bound before any
runtime migration is considered.

## Pose Candidates

- RTMPose: real-time pose front end for single/multi-person keypoints.
- RTMO: real-time multi-person pose estimation candidate for crowded scenes.
- RTMW / whole-body: optional higher-detail skeleton for hands/feet/head cues.

## Action Candidates

- ST-GCN: baseline graph convolution skeleton action classifier.
- 2s-AGCN: stronger two-stream skeleton action classifier.
- PoseC3D: converts keypoints to heatmap sequences for robust temporal action
  recognition.
- STGCN++ / CTRGCN: later candidates if ST-GCN/2s-AGCN improve recall without
  increasing hard-negative alarms.

## Integration Rule

OpenMMLab models first export pose/action scores into V3 replay reports. They
do not replace `realtime_fall_monitor.py` until they beat the YOLO26 path on
latency, recall, and hard-negative false positives.
