from __future__ import annotations

import json
import shutil
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
FALL_ROOT = ROOT / "fall_detection_model_bundle"
POSE_ROOT = ROOT / "pose_detection_model_bundle"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def download_ultralytics_weight(model_name: str, target_path: Path) -> dict[str, object]:
    ensure_dir(target_path.parent)
    if target_path.exists() and target_path.stat().st_size > 0:
        return {"status": "exists", "path": str(target_path)}

    model = YOLO(model_name)
    source_path = Path(getattr(model, "ckpt_path", "") or model_name)
    if not source_path.exists():
        source_path = Path(model_name)
    if source_path.exists() and source_path.resolve() != target_path.resolve():
        shutil.copy2(source_path, target_path)
    if target_path.exists():
        return {"status": "downloaded", "path": str(target_path)}
    return {"status": "missing_after_download", "path": str(target_path)}


def main() -> int:
    required_assets = {
        "public_weights": {
            "fall_detection_model_bundle/yolo11n.pt": "yolo11n.pt",
            "fall_detection_model_bundle/yolo11n-pose.pt": "yolo11n-pose.pt",
        },
        "manual_weights": {
            "fall_detection_model_bundle/weights/yolo_fall_detector_v1.pt": "Required by fall_frame_test_service; private/local trained weight not present in repo.",
            "fall_detection_model_bundle/runs/yolo_posture_person_binary_cls_v1/weights/best.pt": "Required by posture_risk branch; private/local trained weight not present in repo.",
            "fall_detection_model_bundle/weights/gru_pose_fall_v1.pt": "Temporal GRU branch weight referenced by model registry.",
            "fall_detection_model_bundle/weights/hybrid_tcn_transformer_private_real_v1.pt": "Hybrid temporal branch weight referenced by model registry.",
            "fall_detection_model_bundle/weights/hybrid_tcn_transformer_v2_matchgru.pt": "Hybrid fallback temporal branch weight referenced by model registry.",
            "fall_detection_model_bundle/weights/semantic_mix_falldb_private_real_v1.pt": "Semantic temporal branch weight referenced by model registry.",
            "fall_detection_model_bundle/weights/semantic_mix_falldb_v1.pt": "Semantic fallback temporal branch weight referenced by model registry.",
        },
    }

    results: dict[str, object] = {"public_weights": {}, "manual_weights": {}, "paths": {}}

    public_targets = {
        FALL_ROOT / "yolo11n.pt": "yolo11n.pt",
        FALL_ROOT / "yolo11n-pose.pt": "yolo11n-pose.pt",
    }
    for target_path, model_name in public_targets.items():
        results["public_weights"][str(target_path.relative_to(ROOT)).replace("\\", "/")] = download_ultralytics_weight(
            model_name,
            target_path,
        )

    for relative_path, note in required_assets["manual_weights"].items():
        target = ROOT / relative_path
        ensure_dir(target.parent)
        results["manual_weights"][relative_path] = {
            "exists": target.exists() and target.stat().st_size > 0 if target.exists() else False,
            "path": str(target),
            "note": note,
        }

    results["paths"] = {
        "fall_detection_model_bundle": str(FALL_ROOT),
        "pose_detection_model_bundle": str(POSE_ROOT),
        "target_user_assets": str(ROOT / "data" / "target_user_assets"),
    }

    report_path = ROOT / "data" / "fall_detection_assets_status.json"
    ensure_dir(report_path.parent)
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
