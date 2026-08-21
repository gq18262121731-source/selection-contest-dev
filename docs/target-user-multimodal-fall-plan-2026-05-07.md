# Target User Multimodal Fall Detection Plan

## Goal

Upgrade the current fall-detection workflow from "detect every person in view" to
"detect falls only for registered target users" by combining:

- face identity
- body / posture identity
- track-level association
- target-only event filtering

## What We Checked

### Current environment

- `OpenCV 4.13` is available
- `ultralytics`, `torch`, `numpy` are available
- `cv2.FaceDetectorYN` and `cv2.FaceRecognizerSF` are available
- `insightface`, `facenet_pytorch`, `torchreid`, and `face_recognition` are not installed

### Existing model assets

- `D:\Program\model\fall_detection\yolo11n-pose.pt`
- `D:\Program\model\fall_detection\weights\yolo_fall_detector_v1.pt`
- `D:\Program\model\fall_detection\runs\yolo_posture_person_binary_cls_v1\weights\best.pt`

### Main implication

The fastest path to a working MVP is:

1. use OpenCV YuNet / SFace for face detection + face embedding
2. reuse the current YOLO person / pose / posture stack for body cues
3. add a target-user feature store and a target-only gating step before fall alerts

This is more realistic than trying to introduce heavy new dependencies first.

## Recommended Architecture

### Phase 0: Source Alignment

Before implementation, confirm the current source of truth for:

- fall camera test page
- lightweight frame inference path
- backend camera / fall API wiring

Do not build the new target-user path on top of stale copies.

### Phase 1: MVP (recommended immediate implementation)

#### 1. Target user registry

Add a new backend module for target-user registration and lifecycle management.

Recommended storage layout:

- `data/target_users/<user_id>/meta.json`
- `data/target_users/<user_id>/photos/*.jpg`
- `data/target_users/<user_id>/embeddings.json`

Minimal metadata:

- user id
- display name
- group
- note
- active / suspended state
- created / updated timestamps

#### 2. Face feature extraction

Use OpenCV Zoo style APIs:

- `FaceDetectorYN`
- `FaceRecognizerSF`

For each uploaded photo:

1. detect faces
2. reject low-quality faces
3. align face
4. compute normalized face embedding
5. store one or more embeddings per target user

#### 3. Body / posture feature extraction

For the same uploaded photos:

1. detect person box
2. extract body crop
3. compute lightweight body cues:
   - box aspect ratio
   - area ratio
   - shoulder / torso / leg geometry from pose
   - current posture-risk model score
4. store these as the first-stage body profile

This is not yet full ReID, but it is enough for a practical first release.

#### 4. Real-time association

For each frame:

1. detect people
2. detect faces
3. associate face boxes to person boxes by containment / center distance / keypoint proximity
4. keep a short-lived track state per visible person

#### 5. Target user matching

For each associated track:

- face similarity: cosine(face_live, face_gallery)
- body similarity: cosine / weighted distance(body_live, body_gallery)

Use confidence-gated fusion:

- reliable face: `0.75 * face + 0.25 * body`
- no reliable face: `1.00 * body`

Only tracks whose fused score passes the threshold continue into fall detection.
All others are ignored by business logic.

#### 6. Target-only fall alerts

Only create fall events when:

- track belongs to a registered target user
- target match score passes threshold
- fall detector / fall scorer passes threshold

Non-target people should not generate business alerts.

#### 7. Test page upgrade

Upgrade the dedicated model test page to support:

- upload target user photos
- list registered target users
- toggle "target-only detection"
- show current matched target name
- show face score / body score / fused score
- mark non-target people as filtered

### Phase 2: Robust Multi-Person Version

After the MVP works, upgrade the identity stack with stronger building blocks.

#### Recommended upgrades

- Face:
  - ArcFace / InsightFace
  - AdaFace for lower-quality or occluded face inputs
- Tracking:
  - ByteTrack
- Body ReID:
  - OSNet via `deep-person-reid`
- Pose:
  - RTMPose or ViTPose if current pose stability is not enough

#### Why these are the right next upgrades

- ArcFace is still a strong baseline for discriminative face embeddings
- AdaFace adds quality-aware behavior that helps in practical camera conditions
- ByteTrack is strong for maintaining consistent IDs across frames
- OSNet is a strong and efficient person ReID baseline
- RTMPose is more deployment-oriented than many heavier pose stacks

### Phase 3: Long-Range Identity / Back-View Version

If the use case still suffers from side view / back view / face loss:

- add gait features as an optional third modality
- recommended base:
  - OpenGait

Do not start here.
It is useful only after the face + body + tracking pipeline is already stable.

## Data Flow

### Registration flow

1. user uploads 2-10 photos and optional short clips
2. backend extracts face embeddings
3. backend extracts body / posture descriptors
4. data is stored under one target user ID
5. the gallery is reloaded for online matching

### Online flow

1. frame arrives
2. person detection + pose + face detection
3. face-person association
4. live face/body descriptors computed
5. gallery match
6. target-only gating
7. fall detection only for target tracks
8. save evidence and emit alert if needed

## Recommended Modules

- `backend/api/target_user_api.py`
- `backend/services/target_user_service.py`
- `backend/services/target_user_embedding_service.py`
- `backend/services/target_user_match_service.py`
- `backend/services/target_user_track_service.py`

For the test page:

- `tools/fall-camera-lite/index.html`

## Storage Recommendation

Short term:

- JSON + local files for gallery

Medium term:

- SQLite for metadata
- Chroma / vector collections for embeddings

The current environment already includes Chroma, so it is a viable next step.

## First-Stage Acceptance Criteria

The MVP is good enough to move forward when:

1. a registered user is matched from uploaded photos in a single-person test
2. a non-registered person in frame does not trigger target-user fall events
3. in a two-person scene, only the matched target user can produce a fall business event
4. the test page shows target match scores clearly
5. the registry supports add / update / disable / delete

## Test Matrix

### Identity tests

- target user, clear frontal face
- target user, partial side face
- target user, lower face quality
- non-target user, similar hairstyle / clothes
- two people in frame, both visible
- target user occluded by non-target user

### Fall logic tests

- target user falls
- non-target user falls
- both people present, only target user crouches / sits / bends
- target user normal ADL

### Stability tests

- multiple target photos with clothing changes
- repeated sessions across days
- camera moved closer / farther

## Research References

- ArcFace paper:
  - https://arxiv.org/abs/1801.07698
- AdaFace:
  - https://arxiv.org/abs/2204.00964
  - https://github.com/mk-minchul/AdaFace
- ByteTrack:
  - https://github.com/FoundationVision/ByteTrack
- OpenMMLab pose toolbox / RTMPose entrypoint:
  - https://github.com/open-mmlab/mmpose
- OpenGait:
  - https://github.com/ShiqiYu/OpenGait
- OpenCV Zoo (YuNet / SFace):
  - https://github.com/opencv/opencv_zoo
- OpenCV face detection / face recognition docs:
  - https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html
  - https://docs.opencv.org/4.x/df/d20/classcv_1_1FaceDetectorYN.html
  - https://docs.opencv.org/4.x/da/d09/classcv_1_1FaceRecognizerSF.html
- Browser-side frame scheduling:
  - https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/requestVideoFrameCallback

## Immediate Recommendation

Do not begin with gait, full ReID, and advanced multi-branch fusion all at once.

Build in this order:

1. OpenCV face gallery + current YOLO body cues
2. target-only gating in real-time fall inference
3. test page upload / inspection support
4. stronger tracker and ReID
5. gait as optional third modality

## Updated Next-Step Recommendation

After validating the first lightweight registry / API scaffold, the next most important upgrade is:

1. replace the temporary Haar face path with OpenCV Zoo YuNet + SFace
2. keep the current body cues as a lightweight first-stage body branch
3. rerun registration / match smoke tests before integrating target-only gating into fall inference

### Why this is the correct next step

- the current MVP plumbing is enough to prove the registry / API / storage path
- the current temporary face embedding path is too weak for practical matching
- YuNet + SFace improves practical face detection and embedding quality without introducing a heavy new dependency stack
- this keeps the implementation aligned with the current environment, which already ships OpenCV 4.13 APIs for:
  - `FaceDetectorYN`
  - `FaceRecognizerSF`

### Immediate implementation order

1. add model file management for YuNet / SFace ONNX assets
2. upgrade `TargetUserService` face extraction to YuNet / SFace
3. rerun:
   - target user registration
   - target user single-image match
   - mixed target / non-target smoke tests
4. only then wire the matcher into target-only fall event filtering
