# Target User Unified Frontend And Real-Time Gate Plan

## Goal

Turn the existing backend-only target-user bridge into a truly usable operator workflow by adding:

1. one unified frontend page
2. one real-time camera mode
3. one clear target-only gate in front of fall detection

## What Already Exists

- target user local gallery
- target user API
- target user matching service
- target-user-directed fall detection bridge service

## What Is Still Missing

- a single operator page that shows the full chain
- a live camera mode that runs:
  - target match
  - target-only gate
  - fall detection
- strong enough validation UX so the operator knows exactly where the chain failed

## Why This Needs A Unified Frontend

Right now, the system is split across multiple concepts:

- upload target user
- match target user
- test fall detection

This makes it too easy to misread the system state. A unified page should let the operator complete the entire chain in one place:

1. register a target
2. verify the target match
3. verify whether the gate allows fall detection
4. observe the final fall result

## Proposed Frontend Structure

### Section A: Target user registration

Functions:

- upload 3 to 5 target photos
- input display name, group, note
- see feature extraction warnings immediately
- list current target users
- delete invalid users

Validation:

- do not show success when both face and body features are zero
- block duplicate `display_name + group`

### Section B: Single-image chain validation

Upload one test image and display:

- target match decision
- face score
- body score
- fused score
- gate decision
- final fall result
- alert level

This removes ambiguity because the operator no longer has to infer whether the target match and fall result are aligned.

### Section C: Real-time camera mode

Functions:

- live camera preview
- target-only toggle
- real-time target match result
- filtered non-target result
- final fall result
- target name display
- score diagnostics

Suggested diagnostics:

- srcObject present / missing
- video size
- latest HTTP status
- target-only enabled / disabled
- latest inference latency

## Real-Time Logic

Per camera frame:

1. detect and associate face / body cues
2. compute target match result
3. if `target_only == true` and no target match:
   - return `filtered_non_target`
   - stop before fall inference
4. if target match passes:
   - continue into fall inference
   - show alert level and fall result

## Technical Recommendations

### Face identity

Use OpenCV YuNet + SFace first because it fits the current environment well.

Upgrade path:

- InsightFace / ArcFace
- AdaFace for low-quality faces

### Body identity

First stage:

- bounding box geometry
- current posture-risk branch
- lightweight body profile

Upgrade path:

- OSNet via deep-person-reid

### Multi-person stability

First stage:

- per-frame association

Upgrade path:

- ByteTrack / BoT-SORT with stable track ids

### Browser-side real-time scheduling

Recommended:

- `getUserMedia()` with explicit `frameRate`
- `requestVideoFrameCallback()`
- local canvas overlay
- metadata-only backend mode

This is better than returning a full annotated image every frame.

## Testing Plan

### Registration tests

1. valid target photo pack
   - expect nonzero face or body feature counts
2. invalid blurry photo
   - expect rejection
3. duplicate target registration
   - expect rejection

### Single-image chain tests

1. target image
   - expect `target`
2. non-target image
   - expect `non_target` or `unknown`
3. target image with fall-like posture
   - expect gate pass + fall result

### Real-time camera tests

1. only target user in frame
   - target match should pass
   - fall model should run
2. only non-target user in frame
   - gate should filter
   - fall model should not run
3. target and non-target together
   - only target track continues into fall detection

## Acceptance Criteria

The system is "truly usable" only when:

1. one page can register target users
2. one page can test target matching
3. one page can show gate pass / gate filtered
4. live camera mode can distinguish:
   - target
   - non-target
   - unknown
5. only target users continue into fall detection

## Immediate Build Order

1. harden target user registration and deletion
2. build unified operator page
3. add single-image target + fall validation block
4. add live camera mode
5. wire target-only gate into the live fall test loop
