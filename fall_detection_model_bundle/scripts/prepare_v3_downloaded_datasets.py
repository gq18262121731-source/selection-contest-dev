from __future__ import annotations

import argparse
import csv
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"
DATASETS = LAB / "datasets"
REPORTS = LAB / "reports"
MANIFESTS = LAB / "manifests"


def extract_zip_once(zip_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    marker = output_dir / ".extracted_ok"
    if marker.exists():
        return output_dir
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(output_dir)
    marker.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    return output_dir


def write_video_sidecar(video_path: Path, *, dataset: str, split: str, label: str, kind: str, scene_type: str, license_name: str, notes: str) -> None:
    sidecar = video_path.with_suffix(video_path.suffix + ".json")
    if sidecar.exists():
        return
    sidecar.write_text(
        json.dumps(
            {
                "dataset": dataset,
                "split": split,
                "label": label,
                "kind": kind,
                "scene_type": scene_type,
                "segment_start_s": 0.0,
                "segment_end_s": -1.0,
                "target_user_id": "",
                "camera_id": dataset,
                "lighting": "unknown",
                "distance_level": "unknown",
                "occlusion_level": "unknown",
                "multi_person": False,
                "target_visible": True,
                "authorized_for_training": True,
                "license": license_name,
                "notes": notes,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def prepare_gmdcsa24() -> list[dict[str, str]]:
    zip_path = DATASETS / "external_authorized" / "gmdcsa24" / "raw" / "GMDCSA24-A-Dataset-for-Human-Fall-Detection-in-Videos-v2.0.zip"
    rows: list[dict[str, str]] = []
    if not zip_path.exists():
        return rows
    extracted_root = DATASETS / "external_authorized" / "gmdcsa24" / "extracted"
    extract_zip_once(zip_path, extracted_root)
    videos = sorted(extracted_root.rglob("*.mp4"))
    for video_path in videos:
        lower_parts = [part.lower() for part in video_path.parts]
        if "fall" in lower_parts:
            kind = "positive"
            label = "fall_transition"
            split = "external_train_positive"
        elif "adl" in lower_parts:
            kind = "hard_negative"
            label = "normal"
            split = "external_train_hard_negative"
        else:
            kind = "unknown"
            label = "unknown"
            split = "external_unassigned"
        write_video_sidecar(
            video_path,
            dataset="gmdcsa24",
            split=split,
            label=label,
            kind=kind,
            scene_type="living_room_far_view",
            license_name="CC BY 4.0",
            notes="Auto-sidecar from GMDCSA-24 directory structure. Use for temporal/replay training after sampling and QA.",
        )
        rows.append(
            {
                "dataset": "gmdcsa24",
                "video_path": str(video_path.resolve()),
                "kind": kind,
                "label": label,
                "split": split,
                "license": "CC BY 4.0",
            }
        )
    return rows


def write_manifest(rows: list[dict[str, str]]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    csv_path = MANIFESTS / "prepared_external_videos.v3.csv"
    json_path = REPORTS / "prepared_external_videos.v3.json"
    md_path = REPORTS / "prepared_external_videos.v3.md"
    if rows:
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        csv_path.write_text("", encoding="utf-8")
    json_path.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    lines = [
        "# Prepared External Videos V3",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Prepared videos: {len(rows)}",
        "",
        "## Counts",
        "",
    ]
    for key, value in sorted(counts.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Notes", "", "- GMDCSA-24 videos are expanded and sidecars are generated automatically from `Fall` and `ADL` directories."])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract downloaded public datasets and create sidecars for V3 scene manifest.")
    parser.add_argument("--dataset", action="append", choices=["gmdcsa24"], default=[])
    args = parser.parse_args()
    datasets = args.dataset or ["gmdcsa24"]
    rows: list[dict[str, str]] = []
    if "gmdcsa24" in datasets:
        rows.extend(prepare_gmdcsa24())
    write_manifest(rows)
    print(json.dumps({"prepared_videos": len(rows), "manifest": str((MANIFESTS / "prepared_external_videos.v3.csv").resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
