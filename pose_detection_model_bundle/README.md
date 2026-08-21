# Pose Detection

Pose detection workspace for real-time elder-care monitoring. This bundle is
kept separate from the fall-detection workspace during V1 so we can add pose
capabilities without disturbing the existing production fall pipeline.

Current V1 strategy:

- Use a real-time pose front end to detect people and keypoints.
- Build lightweight posture labels from keypoint geometry and scene ROI hints.
- Output structured JSON files that the backend can tail and expose through APIs.
- Keep the existing fall detection service running in parallel.
