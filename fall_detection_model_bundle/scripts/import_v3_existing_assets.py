from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"


def copy_tree_or_file(source: Path, target: Path) -> str:
    if not source.exists():
        return "missing"
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)
    return "copied"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import existing fall-detection assets into the isolated V3 lab.")
    parser.add_argument("--source-root", default=r"D:\Program\model\fall_detection")
    args = parser.parse_args()

    source_root = Path(args.source_root)
    actions = {
        "fall_detect_dataset": copy_tree_or_file(
            source_root / "data_processed" / "fall_detect",
            LAB / "datasets" / "fall_detect_existing",
        ),
        "fall_detect_v2_recall_dataset": copy_tree_or_file(
            source_root / "data_processed" / "fall_detect_v2_recall",
            LAB / "datasets" / "fall_detect_v2_recall_existing",
        ),
        "dryrun_videos": copy_tree_or_file(
            source_root / "data_private" / "camera_scene" / "dryrun_videos",
            LAB / "datasets" / "private_dryrun_videos",
        ),
        "raw_private_videos": copy_tree_or_file(
            source_root / "data_private" / "camera_scene" / "raw_videos",
            LAB / "datasets" / "private_raw_videos",
        ),
        "pose_tcn_fall_v2": copy_tree_or_file(
            source_root / "weights" / "pose_tcn_fall_v2.pt",
            LAB / "weights" / "temporal" / "pose_tcn_fall_v2.pt",
        ),
        "pose_tcn_fall_v2_meta": copy_tree_or_file(
            source_root / "weights" / "pose_tcn_fall_v2.pt.json",
            LAB / "weights" / "temporal" / "pose_tcn_fall_v2.pt.json",
        ),
        "yolo_fall_detector_v1_external": copy_tree_or_file(
            source_root / "weights" / "yolo_fall_detector_v1.pt",
            LAB / "weights" / "yolo26" / "yolo26_fall_detector_v3_warmstart_source.pt",
        ),
    }

    dataset_yaml = LAB / "configs" / "fall_detect_v3_existing_dataset.yaml"
    dataset_yaml.write_text(
        "\n".join(
            [
                f"path: {str((LAB / 'datasets' / 'fall_detect_existing').resolve()).replace(chr(92), '/')}",
                "train: images/train",
                "val: images/val",
                "test: images/test",
                "",
                "names:",
                "  0: person",
                "  1: fall",
                "  2: fallen",
                "  3: sitting",
                "  4: lying",
                "  5: bending",
                "",
            ]
        ),
        encoding="utf-8",
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(source_root),
        "actions": actions,
        "dataset_yaml": str(dataset_yaml),
    }
    report_path = LAB / "reports" / "import_v3_existing_assets.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
