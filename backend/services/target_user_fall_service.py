from __future__ import annotations

import time
from pathlib import Path
from threading import RLock
from typing import Any

import cv2
import numpy as np

from backend.services.posture_event_service import PostureEventService
from backend.services.posture_knowledge_service import PostureKnowledgeService
from backend.services.target_pose_service import TargetPoseService
from backend.services.target_user_service import TargetUserService


class TargetUserFallService:
    """Phase-1 target-only fall detection bridge.

    This service does not yet solve full multi-person tracking. It provides a
    clean target-user gate in front of single-frame fall detection so the rest
    of the system can evolve toward the final multi-person target-only flow.
    """

    def __init__(
        self,
        *,
        data_root: Path,
        model_root: Path,
        target_user_service: TargetUserService,
        target_pose_service: TargetPoseService,
        posture_event_service: PostureEventService,
        posture_knowledge_service: PostureKnowledgeService,
    ) -> None:
        self._target_user_service = target_user_service
        self._target_pose_service = target_pose_service
        self._posture_event_service = posture_event_service
        self._posture_knowledge_service = posture_knowledge_service
        self._model_root = model_root
        self._data_root = data_root
        self._fall_frame_service = None
        self._lock = RLock()
        self._session_match_cache: dict[str, dict[str, Any]] = {}
        self._session_trackers: dict[str, Any] = {}
        self._session_fall_windows: dict[str, list[dict[str, Any]]] = {}
        self._match_cache_ttl_ms = 1800
        self._full_refresh_interval_ms = 900
        self._tracker_args = None
        self._tracker_available = False
        self._tracker_import_error: str | None = None
        self._roi_padding_ratio = 0.18
        self._init_tracker_backend()
        self._init_fall_frame_service()

    def _init_tracker_backend(self) -> None:
        try:
            from ultralytics.trackers.byte_tracker import BYTETracker  # type: ignore
            from ultralytics.utils import IterableSimpleNamespace  # type: ignore
        except Exception as exc:
            self._tracker_available = False
            self._tracker_import_error = f"{exc.__class__.__name__}: {exc}"
            self._byte_tracker_cls = None
            self._tracker_args = None
            return

        self._byte_tracker_cls = BYTETracker
        self._tracker_args = IterableSimpleNamespace(
            tracker_type="bytetrack",
            track_high_thresh=0.25,
            track_low_thresh=0.1,
            new_track_thresh=0.25,
            track_buffer=30,
            match_thresh=0.8,
            fuse_score=True,
        )
        self._tracker_available = True
        self._tracker_import_error = None

    def _init_fall_frame_service(self) -> None:
        try:
            from backend.services.fall_frame_test_service import FallFrameTestService
            from backend.config import get_settings

            self._fall_frame_service = FallFrameTestService(get_settings())
        except Exception:
            self._fall_frame_service = None

    def warmup(self, *, speed_mode: str = "low_latency") -> dict[str, Any]:
        """Load and warm the heavy realtime vision models before the first UI request."""
        started = time.perf_counter()
        speed = self._speed_profile(speed_mode)
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        result: dict[str, Any] = {
            "ok": True,
            "speed": speed,
            "person": None,
            "fall": None,
            "pose": None,
            "tracker_available": self._tracker_available,
            "tracker_import_error": self._tracker_import_error,
            "latency_ms": 0,
        }
        try:
            result["person"] = self._target_user_service.warmup_person_detector(imgsz=speed["person_imgsz"])
            if self._fall_frame_service is not None:
                result["fall"] = self._fall_frame_service.warmup(
                    imgsz=speed["fall_imgsz"],
                    posture_imgsz=speed["posture_imgsz"],
                )
            result["pose"] = self._target_pose_service.warmup(
                imgsz=speed["pose_imgsz"],
                conf=speed["pose_conf"],
            )
        except Exception as exc:
            result["ok"] = False
            result["error"] = f"{exc.__class__.__name__}: {exc}"
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return result

    def detect(
        self,
        image_bytes: bytes,
        *,
        include_annotated_image: bool = True,
        target_only: bool = True,
        session_id: str = "default",
        speed_mode: str = "balanced",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        speed = self._speed_profile(speed_mode)
        np_buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        frame = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
        if frame is None:
            return {
                "ok": False,
                "status": "model_unavailable",
                "error": "INVALID_IMAGE",
                "target_match": None,
                "fall_result": None,
                "latency_ms": 0,
            }

        now_ms = int(time.perf_counter() * 1000)
        cache_entry = self._get_cache_entry(session_id)
        force_full_match = True
        if cache_entry is not None and "last_full_match_ms" not in cache_entry:
            cache_entry["last_full_match_ms"] = int(cache_entry.get("ts_ms", now_ms))
        if cache_entry and (now_ms - int(cache_entry["last_full_match_ms"])) <= speed["full_refresh_interval_ms"]:
            force_full_match = False

        tracked_persons = self._resolve_tracked_persons(frame=frame, session_id=session_id, speed=speed)
        tracked_person = None
        target_features = None
        target_match = None
        tracking_payload = {
            "session_id": session_id,
            "track_id": None,
            "used_track": False,
            "full_match_refreshed": force_full_match,
            "candidate_count": len(tracked_persons),
            "tracker_available": self._tracker_available,
            "tracker_import_error": self._tracker_import_error,
        }

        if tracked_persons:
            tracked_person, target_match, target_features = self._pick_target_candidate(
                tracked_persons=tracked_persons,
                session_id=session_id,
                now_ms=now_ms,
                force_full_match=force_full_match,
                speed=speed,
            )
            if tracked_person is not None:
                tracking_payload["track_id"] = tracked_person["track_id"]
                tracking_payload["used_track"] = True
                tracking_payload["reused_locked_match"] = bool(target_features and target_features.get("reused_locked_match"))

        if target_match is None or target_features is None:
            target_features = self._target_user_service.extract_features_from_frame(
                frame,
                include_face=force_full_match,
                include_body=True,
                body_imgsz=speed["body_imgsz"],
            )
            target_match = self._resolve_target_match(
                face_embedding=target_features["face_embedding"],
                body_profile=target_features["body_profile"],
                body_embedding=target_features["body_embedding"],
                session_id=session_id,
                now_ms=now_ms,
                track_id=tracked_person["track_id"] if tracked_person is not None else None,
                match_cache_ttl_ms=speed["match_cache_ttl_ms"],
            )

        assert target_match is not None
        assert target_features is not None

        if target_only and not target_match.matched:
            return {
                "ok": True,
                "status": "filtered_non_target",
                "target_match": target_match.model_dump(mode="json"),
                "fall_result": None,
                "warnings": target_features["warnings"],
                "speed": speed,
                "tracking": tracking_payload,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }

        if target_only and target_match.matched and tracked_person is None:
            return {
                "ok": True,
                "status": "target_not_localized",
                "target_match": target_match.model_dump(mode="json"),
                "fall_result": None,
                "pose_result": None,
                "posture_event": None,
                "posture_guidance": None,
                "warnings": [*target_features["warnings"], "TARGET_MATCHED_BUT_NO_TRACK_ROI"],
                "speed": speed,
                "tracking": tracking_payload,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }

        if self._fall_frame_service is None:
            return {
                "ok": False,
                "status": "model_unavailable",
                "error": "FALL_MODEL_UNAVAILABLE",
                "target_match": target_match.model_dump(mode="json"),
                "fall_result": None,
                "speed": speed,
                "tracking": tracking_payload,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }

        roi_info = None
        pose_result = None
        posture_event = None
        posture_guidance = None
        if tracked_person is not None and target_match.matched:
            roi_frame, roi_bbox = self._crop_target_roi(frame, tracked_person["bbox"])
            if roi_frame is not None:
                fall_result = self._fall_frame_service.detect_frame(
                    roi_frame,
                    include_annotated_image=include_annotated_image,
                    imgsz=speed["fall_imgsz"],
                    posture_imgsz=speed["posture_imgsz"],
                )
                self._offset_detections(fall_result, roi_bbox)
                self._limit_fall_result_to_target(fall_result, roi_bbox, target_match=target_match)
                pose_result = self._target_pose_service.estimate_pose(
                    frame,
                    bbox=roi_bbox,
                    imgsz=speed["pose_imgsz"],
                    conf=speed["pose_conf"],
                    session_id=session_id,
                    track_id=tracked_person["track_id"],
                )
                posture_event = self._posture_event_service.analyze(
                    session_id=session_id,
                    pose_result=pose_result,
                    target_matched=True,
                )
                posture_guidance = self._posture_knowledge_service.get((posture_event or {}).get("type", "normal"))
                self._stabilize_target_fall_result(
                    session_id=session_id,
                    fall_result=fall_result,
                    pose_result=pose_result,
                    posture_event=posture_event,
                )
                roi_info = {
                    "bbox": roi_bbox,
                    "used_roi": True,
                }
            else:
                fall_result = self._fall_frame_service.detect_frame(
                    frame,
                    include_annotated_image=include_annotated_image,
                    imgsz=speed["fall_imgsz"],
                    posture_imgsz=speed["posture_imgsz"],
                )
                self._limit_fall_result_to_target(fall_result, tracked_person["bbox"], target_match=target_match)
                pose_result = self._target_pose_service.estimate_pose(
                    frame,
                    bbox=tracked_person["bbox"],
                    imgsz=speed["pose_imgsz"],
                    conf=speed["pose_conf"],
                    session_id=session_id,
                    track_id=tracked_person["track_id"],
                )
                posture_event = self._posture_event_service.analyze(
                    session_id=session_id,
                    pose_result=pose_result,
                    target_matched=True,
                )
                posture_guidance = self._posture_knowledge_service.get((posture_event or {}).get("type", "normal"))
                self._stabilize_target_fall_result(
                    session_id=session_id,
                    fall_result=fall_result,
                    pose_result=pose_result,
                    posture_event=posture_event,
                )
        else:
            fall_result = self._fall_frame_service.detect_frame(
                frame,
                include_annotated_image=include_annotated_image,
                imgsz=speed["fall_imgsz"],
                posture_imgsz=speed["posture_imgsz"],
            )
            if target_only:
                fall_result["detections"] = []

        if fall_result.get("frame"):
            fall_result["frame"] = {"width": frame.shape[1], "height": frame.shape[0]}
        return {
            "ok": bool(fall_result.get("ok", False)),
            "status": fall_result.get("status"),
            "target_match": target_match.model_dump(mode="json"),
            "fall_result": fall_result,
            "pose_result": pose_result,
            "posture_event": posture_event,
            "posture_guidance": posture_guidance,
            "warnings": target_features["warnings"],
            "speed": speed,
            "tracking": {
                **tracking_payload,
                "roi": roi_info,
            },
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }

    def _resolve_target_match(
        self,
        *,
        face_embedding: list[float] | None,
        body_profile: dict[str, float] | None,
        body_embedding: list[float] | None,
        session_id: str,
        now_ms: int,
        track_id: int | None,
        match_cache_ttl_ms: int | None = None,
    ):
        cached = self._get_cache_entry(session_id)
        cache_ttl_ms = match_cache_ttl_ms or self._match_cache_ttl_ms

        if cached and (now_ms - int(cached["ts_ms"])) <= cache_ttl_ms:
            if track_id is not None and cached.get("track_id") is not None and int(cached["track_id"]) != int(track_id):
                cached = None
        else:
            cached = None

        if cached:
            if face_embedding is None and body_profile is not None and cached.get("body_profile") is not None:
                if (
                    track_id is None
                    or cached.get("track_id") is None
                    or int(cached["track_id"]) != int(track_id)
                    or not cached.get("face_confirmed")
                    or (now_ms - int(cached.get("last_full_match_ms", 0))) > 2500
                ):
                    return self._target_user_service.match_target(
                        face_embedding=face_embedding,
                        body_profile=body_profile,
                        body_embedding=body_embedding,
                    )
                body_score = self._target_user_service._best_body_similarity(  # type: ignore[attr-defined]
                    body_profile,
                    [cached["body_profile"]],
                )
                if body_score >= 0.90:
                    match = cached["match"].model_copy(update={
                        "body_score": round(body_score, 4),
                        "fused_score": round(max(float(cached["match"].fused_score), body_score), 4),
                    })
                    updated = {
                        **cached,
                        "ts_ms": now_ms,
                        "last_feature_match_ms": now_ms,
                        "match": match,
                        "body_profile": body_profile,
                        "body_embedding": body_embedding,
                        "track_id": track_id if track_id is not None else cached.get("track_id"),
                    }
                    self._set_cache_entry(session_id, updated)
                    return match

        target_match = self._target_user_service.match_target(
            face_embedding=face_embedding,
            body_profile=body_profile,
            body_embedding=body_embedding,
        )
        if target_match.matched:
            last_full_match_ms = now_ms
            if face_embedding is None and cached is not None:
                last_full_match_ms = int(cached.get("last_full_match_ms", now_ms))
            self._set_cache_entry(
                session_id,
                {
                    "ts_ms": now_ms,
                    "last_full_match_ms": last_full_match_ms,
                    "last_feature_match_ms": now_ms,
                    "match": target_match,
                    "body_profile": body_profile,
                    "body_embedding": body_embedding,
                    "track_id": track_id,
                    "face_confirmed": face_embedding is not None and float(target_match.face_score or 0.0) >= 0.70,
                },
            )
        else:
            if cached and (now_ms - int(cached["ts_ms"])) > cache_ttl_ms:
                self._clear_cache_entry(session_id)
        return target_match

    def _resolve_tracked_persons(self, *, frame: np.ndarray, session_id: str, speed: dict[str, Any]) -> list[dict[str, Any]]:
        person_boxes = self._target_user_service._collect_person_boxes(  # type: ignore[attr-defined]
            frame,
            self._target_user_service.person_model,  # type: ignore[attr-defined]
            allowed_labels={"person"},
            conf=0.2,
            imgsz=speed["person_imgsz"],
        )
        if not person_boxes:
            person_boxes = self._target_user_service._collect_person_boxes(  # type: ignore[attr-defined]
                frame,
                self._target_user_service.fallback_person_model,  # type: ignore[attr-defined]
                allowed_labels={"person", "fall", "fallen", "sitting", "lying", "bending"},
                conf=0.2,
                imgsz=speed["person_imgsz"],
            )
        if not person_boxes:
            face_candidate = self._build_face_first_candidate(frame)
            return [face_candidate] if face_candidate is not None else []

        if not self._tracker_available:
            people: list[dict[str, Any]] = []
            h, w = frame.shape[:2]
            for index, (box, _score, _label) in enumerate(person_boxes, start=1):
                x1, y1, x2, y2 = [float(v) for v in box]
                x1i = max(0, min(w - 1, int(round(x1))))
                y1i = max(0, min(h - 1, int(round(y1))))
                x2i = max(0, min(w, int(round(x2))))
                y2i = max(0, min(h, int(round(y2))))
                if x2i <= x1i or y2i <= y1i:
                    continue
                crop = frame[y1i:y2i, x1i:x2i]
                if crop.size == 0:
                    continue
                people.append(
                    {
                        "track_id": index,
                        "bbox": [x1i, y1i, x2i, y2i],
                        "crop": crop,
                    }
                )
            return people

        tracker = self._get_or_create_tracker(session_id)
        if tracker is None:
            return []

        class _TrackResults:
            def __init__(self, boxes):
                xywh = []
                conf = []
                cls = []
                for box, score, label in boxes:
                    x1, y1, x2, y2 = [float(v) for v in box]
                    xywh.append([(x1 + x2) * 0.5, (y1 + y2) * 0.5, max(1.0, x2 - x1), max(1.0, y2 - y1)])
                    conf.append(float(score))
                    cls.append(0.0 if label == "person" else 1.0)
                self.xywh = np.asarray(xywh, dtype=np.float32)
                self.conf = np.asarray(conf, dtype=np.float32)
                self.cls = np.asarray(cls, dtype=np.float32)

            def __len__(self):
                return int(len(self.conf))

            def __getitem__(self, item):
                sliced = object.__new__(_TrackResults)
                sliced.xywh = np.asarray(self.xywh[item], dtype=np.float32).reshape(-1, 4)
                sliced.conf = np.asarray(self.conf[item], dtype=np.float32).reshape(-1)
                sliced.cls = np.asarray(self.cls[item], dtype=np.float32).reshape(-1)
                return sliced

        tracks = tracker.update(_TrackResults(person_boxes), frame)
        if tracks is None or len(tracks) == 0:
            return []

        cache_entry = self._get_cache_entry(session_id)
        preferred_track_id = cache_entry.get("track_id") if cache_entry else None
        ordered_tracks = list(tracks)
        if preferred_track_id is not None:
            ordered_tracks.sort(key=lambda item: 0 if int(item[4]) == int(preferred_track_id) else 1)

        people: list[dict[str, Any]] = []
        h, w = frame.shape[:2]
        for selected in ordered_tracks:
            x1, y1, x2, y2, track_id, *_rest = [float(v) for v in selected]
            x1i = max(0, min(w - 1, int(round(x1))))
            y1i = max(0, min(h - 1, int(round(y1))))
            x2i = max(0, min(w, int(round(x2))))
            y2i = max(0, min(h, int(round(y2))))
            if x2i <= x1i or y2i <= y1i:
                continue
            crop = frame[y1i:y2i, x1i:x2i]
            if crop.size == 0:
                continue
            people.append(
                {
                    "track_id": int(track_id),
                    "bbox": [x1i, y1i, x2i, y2i],
                    "crop": crop,
                }
            )
        return people

    def _build_face_first_candidate(self, frame: np.ndarray) -> dict[str, Any] | None:
        face_bbox = self._target_user_service.detect_face_bbox(frame)
        if face_bbox is None:
            return None
        x1, y1, x2, y2 = face_bbox
        h, w = frame.shape[:2]
        face_w = max(1, x2 - x1)
        face_h = max(1, y2 - y1)
        body_w = int(round(face_w * 3.4))
        body_h = int(round(face_h * 6.2))
        cx = int(round((x1 + x2) * 0.5))
        top = max(0, y1 - int(round(face_h * 0.6)))
        rx1 = max(0, cx - body_w // 2)
        rx2 = min(w, cx + body_w // 2)
        ry1 = top
        ry2 = min(h, ry1 + body_h)
        if rx2 <= rx1 or ry2 <= ry1:
            return None
        crop = frame[ry1:ry2, rx1:rx2]
        if crop.size == 0:
            return None
        return {
            "track_id": -1,
            "bbox": [rx1, ry1, rx2, ry2],
            "crop": crop,
        }

    def _pick_target_candidate(
        self,
        *,
        tracked_persons: list[dict[str, Any]],
        session_id: str,
        now_ms: int,
        force_full_match: bool,
        speed: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, Any | None, dict[str, Any] | None]:
        cached = self._get_cache_entry(session_id)
        if cached and cached.get("track_id") is not None:
            preferred = next((item for item in tracked_persons if int(item["track_id"]) == int(cached["track_id"])), None)
            if preferred is not None:
                reuse_ms = int(speed.get("track_lock_reuse_ms") or 0)
                revalidate_ms = int(speed.get("track_lock_revalidate_ms") or 0)
                last_seen_ms = int(cached.get("ts_ms", 0))
                last_feature_match_ms = int(cached.get("last_feature_match_ms", last_seen_ms))
                can_reuse_track_lock = (
                    cached.get("match") is not None
                    and reuse_ms > 0
                    and revalidate_ms > 0
                    and (now_ms - last_seen_ms) <= reuse_ms
                    and (now_ms - last_feature_match_ms) <= revalidate_ms
                )
                if can_reuse_track_lock:
                    self._set_cache_entry(session_id, {**cached, "ts_ms": now_ms})
                    return preferred, cached["match"], {
                        "warnings": [],
                        "face_embedding": None,
                        "body_profile": cached.get("body_profile"),
                        "body_embedding": cached.get("body_embedding"),
                        "reused_locked_match": True,
                    }
                preferred_features = self._target_user_service.extract_features_from_frame(
                    preferred["crop"],
                    include_face=force_full_match,
                    include_body=True,
                    body_imgsz=speed["body_imgsz"],
                )
                preferred_match = self._resolve_target_match(
                    face_embedding=preferred_features["face_embedding"],
                    body_profile=preferred_features["body_profile"],
                    body_embedding=preferred_features["body_embedding"],
                    session_id=session_id,
                    now_ms=now_ms,
                    track_id=preferred["track_id"],
                    match_cache_ttl_ms=speed["match_cache_ttl_ms"],
                )
                if preferred_match.matched:
                    return preferred, preferred_match, preferred_features

        best_person = None
        best_features = None
        best_match = None
        best_score = -1.0
        for person in tracked_persons:
            features = self._target_user_service.extract_features_from_frame(
                person["crop"],
                include_face=force_full_match,
                include_body=True,
                body_imgsz=speed["body_imgsz"],
            )
            candidate = self._target_user_service.match_target(
                face_embedding=features["face_embedding"],
                body_profile=features["body_profile"],
                body_embedding=features["body_embedding"],
            )
            score = float(candidate.fused_score)
            if score > best_score:
                best_score = score
                best_person = person
                best_features = features
                best_match = candidate

        if best_person is None or best_features is None:
            return None, None, None

        final_match = self._resolve_target_match(
            face_embedding=best_features["face_embedding"],
            body_profile=best_features["body_profile"],
            body_embedding=best_features["body_embedding"],
            session_id=session_id,
            now_ms=now_ms,
            track_id=best_person["track_id"],
            match_cache_ttl_ms=speed["match_cache_ttl_ms"],
        )
        return best_person, final_match, best_features

    @staticmethod
    def _speed_profile(speed_mode: str) -> dict[str, Any]:
        normalized = str(speed_mode or "balanced").strip().lower().replace("-", "_")
        if normalized in {"low_latency", "fast", "turbo"}:
            return {
                "mode": "low_latency",
                "person_imgsz": 416,
                "fall_imgsz": 416,
                "posture_imgsz": 256,
                "pose_imgsz": 384,
                "pose_conf": 0.25,
                "body_imgsz": 416,
                "match_cache_ttl_ms": 3200,
                "full_refresh_interval_ms": 1800,
                "track_lock_reuse_ms": 650,
                "track_lock_revalidate_ms": 1500,
            }
        return {
            "mode": "balanced",
            "person_imgsz": 640,
            "fall_imgsz": 640,
            "posture_imgsz": 384,
            "pose_imgsz": 640,
            "pose_conf": 0.2,
            "body_imgsz": 640,
            "match_cache_ttl_ms": 1800,
            "full_refresh_interval_ms": 900,
            "track_lock_reuse_ms": 0,
            "track_lock_revalidate_ms": 0,
        }

    def _get_or_create_tracker(self, session_id: str):
        with self._lock:
            if not self._tracker_available or self._byte_tracker_cls is None or self._tracker_args is None:
                return None
            tracker = self._session_trackers.get(session_id)
            if tracker is None:
                tracker = self._byte_tracker_cls(self._tracker_args, frame_rate=30)
                self._session_trackers[session_id] = tracker
            return tracker

    def _get_cache_entry(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._session_match_cache.get(session_id)

    def _set_cache_entry(self, session_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._session_match_cache[session_id] = payload

    def _clear_cache_entry(self, session_id: str) -> None:
        with self._lock:
            self._session_match_cache.pop(session_id, None)

    def _stabilize_target_fall_result(
        self,
        *,
        session_id: str,
        fall_result: dict[str, Any],
        pose_result: dict[str, Any] | None,
        posture_event: dict[str, Any] | None,
    ) -> None:
        if not fall_result.get("ok"):
            return

        now_ms = int(time.perf_counter() * 1000)
        scores = fall_result.get("scores") if isinstance(fall_result.get("scores"), dict) else {}
        fall_score = float(scores.get("fall") or fall_result.get("fall_score") or 0.0)
        detector_score = float(scores.get("detector") or 0.0)
        posture_score = float(scores.get("posture") or 0.0)
        pose = (pose_result or {}).get("pose") or {}
        pose_posture = pose.get("posture") or {}
        pose_quality = pose.get("quality") or {}
        pose_label = str(pose_posture.get("label") or "unknown")
        pose_conf = float(pose_posture.get("confidence") or 0.0)
        visible_points = int(pose_quality.get("visible_points") or 0)
        event_type = str((posture_event or {}).get("type") or "normal")
        event_level = str((posture_event or {}).get("level") or "normal")

        entry = {
            "ts_ms": now_ms,
            "status": str(fall_result.get("status") or "normal"),
            "fall_score": fall_score,
            "detector_score": detector_score,
            "posture_score": posture_score,
            "pose_label": pose_label,
            "pose_conf": pose_conf,
            "visible_points": visible_points,
            "event_type": event_type,
            "event_level": event_level,
        }
        with self._lock:
            window = self._session_fall_windows.setdefault(session_id, [])
            window.append(entry)
            cutoff = now_ms - 2200
            window[:] = [item for item in window[-16:] if int(item["ts_ms"]) >= cutoff]
            recent = list(window)

        risky_pose = (
            pose_label in {"fall_like", "slumped"}
            and pose_conf >= 0.58
            and visible_points >= 8
        )
        risky_event = event_type in {"fall_fast", "fall_slow", "collapse_or_slump"} or event_level in {"danger", "critical"}
        risky_frames = sum(
            1
            for item in recent
            if float(item["fall_score"]) >= 0.42
            or str(item["pose_label"]) in {"fall_like", "slumped"}
            or str(item["event_level"]) in {"danger", "critical"}
        )

        confirmed = (
            detector_score >= 0.58
            or fall_score >= 0.82
            or (fall_score >= 0.62 and (risky_pose or risky_event))
            or (fall_score >= 0.48 and risky_frames >= 3 and (risky_pose or risky_event))
        )
        suspected = fall_score >= 0.36 or risky_pose or risky_event or risky_frames >= 2

        original_status = str(fall_result.get("status") or "normal")
        if confirmed:
            fall_result["status"] = "fall"
            fall_result["fall_detected"] = True
        elif suspected:
            fall_result["status"] = "suspected"
            fall_result["fall_detected"] = False
        else:
            fall_result["status"] = "normal"
            fall_result["fall_detected"] = False

        fall_result["temporal_verification"] = {
            "enabled": True,
            "original_status": original_status,
            "confirmed": confirmed,
            "risky_frames": risky_frames,
            "window_frames": len(recent),
            "pose_label": pose_label,
            "pose_confidence": round(pose_conf, 4),
            "visible_points": visible_points,
            "event_type": event_type,
            "event_level": event_level,
        }

    def _crop_target_roi(self, frame: np.ndarray, bbox: list[int]) -> tuple[np.ndarray | None, list[int] | None]:
        if frame is None or frame.size == 0:
            return None, None
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = frame.shape[:2]
        box_w = max(1, x2 - x1)
        box_h = max(1, y2 - y1)
        pad_x = int(round(box_w * self._roi_padding_ratio))
        pad_y = int(round(box_h * self._roi_padding_ratio))
        rx1 = max(0, x1 - pad_x)
        ry1 = max(0, y1 - pad_y)
        rx2 = min(w, x2 + pad_x)
        ry2 = min(h, y2 + pad_y)
        if rx2 <= rx1 or ry2 <= ry1:
            return None, None
        crop = frame[ry1:ry2, rx1:rx2]
        if crop.size == 0:
            return None, None
        return crop, [rx1, ry1, rx2, ry2]

    @staticmethod
    def _offset_detections(fall_result: dict[str, Any], roi_bbox: list[int] | None) -> None:
        if roi_bbox is None:
            return
        detections = fall_result.get("detections") or []
        ox, oy = roi_bbox[0], roi_bbox[1]
        for item in detections:
            box = item.get("bbox")
            if not box or len(box) < 4:
                continue
            item["bbox"] = [
                round(float(box[0]) + ox, 1),
                round(float(box[1]) + oy, 1),
                round(float(box[2]) + ox, 1),
                round(float(box[3]) + oy, 1),
            ]

    @staticmethod
    def _limit_fall_result_to_target(
        fall_result: dict[str, Any],
        target_bbox: list[int] | list[float] | None,
        *,
        target_match: Any,
    ) -> None:
        if target_bbox is None or len(target_bbox) < 4:
            fall_result["detections"] = []
            return

        tx1, ty1, tx2, ty2 = [float(v) for v in target_bbox[:4]]
        if tx2 <= tx1 or ty2 <= ty1:
            fall_result["detections"] = []
            return

        target_area = max(1.0, (tx2 - tx1) * (ty2 - ty1))
        kept: list[dict[str, Any]] = []
        for item in fall_result.get("detections") or []:
            box = item.get("bbox")
            if not box or len(box) < 4:
                continue
            x1, y1, x2, y2 = [float(v) for v in box[:4]]
            ix1 = max(tx1, x1)
            iy1 = max(ty1, y1)
            ix2 = min(tx2, x2)
            iy2 = min(ty2, y2)
            inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
            box_area = max(1.0, (x2 - x1) * (y2 - y1))
            center_inside = tx1 <= (x1 + x2) * 0.5 <= tx2 and ty1 <= (y1 + y2) * 0.5 <= ty2
            if center_inside or inter / target_area >= 0.12 or inter / box_area >= 0.35:
                kept.append({**item, "target_only": True})

        label = "target"
        if kept:
            risky = max(float(item.get("confidence") or 0.0) for item in kept)
            risky_labels = {"fall", "fallen", "lying"}
            label = "target_" + ("risk" if any(str(item.get("label", "")).lower() in risky_labels for item in kept) else "tracked")
            confidence = max(risky, float(getattr(target_match, "fused_score", 0.0) or 0.0))
        else:
            confidence = float(getattr(target_match, "fused_score", 0.0) or 0.0)

        target_detection = {
            "bbox": [round(tx1, 1), round(ty1, 1), round(tx2, 1), round(ty2, 1)],
            "label": label,
            "confidence": round(max(0.0, min(1.0, confidence)), 4),
            "target_only": True,
            "source": "target_track_roi",
        }
        fall_result["detections"] = [target_detection, *kept[:3]]
