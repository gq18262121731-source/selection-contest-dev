from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".mjpeg"}


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def infer_label_from_path(path: Path, taxonomy: dict[str, Any]) -> tuple[str, str]:
    text = " ".join(part.lower() for part in path.parts)
    for label in taxonomy.get("action_stages", {}).get("positive", []):
        if label.lower() in text:
            return label, "positive"
    aliases = {"fall": "fall_transition", "fallen": "fallen_immobile"}
    for needle, label in aliases.items():
        if needle in text:
            return label, "positive"
    for label in taxonomy.get("action_stages", {}).get("hard_negative", []):
        if label.lower() in text:
            return label, "hard_negative"
    for label in taxonomy.get("action_stages", {}).get("neutral", []):
        if label.lower() in text:
            return label, "neutral"
    return "unknown", "unknown"


def infer_scene_from_path(path: Path, taxonomy: dict[str, Any]) -> str:
    text = " ".join(part.lower() for part in path.parts)
    for scene in taxonomy.get("scene_types", {}):
        if scene.lower() in text:
            return scene
    mapping = {
        "bedroom": "bedroom_low_light",
        "bed": "bedroom_low_light",
        "living": "living_room_far_view",
        "sofa": "living_room_far_view",
        "corridor": "corridor_multi_person",
        "hall": "corridor_multi_person",
        "bath": "bathroom_or_doorway",
        "door": "bathroom_or_doorway",
        "demo": "demo_clean_room",
    }
    for needle, scene in mapping.items():
        if needle in text:
            return scene
    return "unknown"


def read_sidecar(path: Path) -> dict[str, Any]:
    for candidate in [path.with_suffix(path.suffix + ".json"), path.with_suffix(".json")]:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
    return {}


def build_rows(input_dirs: list[Path], taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for input_dir in input_dirs:
        if not input_dir.exists():
            continue
        for video_path in sorted(p for p in input_dir.rglob("*") if p.suffix.lower() in VIDEO_EXTS):
            sidecar = read_sidecar(video_path)
            label, kind = infer_label_from_path(video_path, taxonomy)
            scene = infer_scene_from_path(video_path, taxonomy)
            label = str(sidecar.get("label") or label)
            kind = str(sidecar.get("kind") or kind)
            scene = str(sidecar.get("scene_type") or scene)
            rows.append(
                {
                    "video_path": str(video_path.resolve()),
                    "video_key": video_path.stem,
                    "dataset": str(sidecar.get("dataset") or "v3_local"),
                    "split": str(sidecar.get("split") or "unassigned"),
                    "scene_type": scene,
                    "label_name": label,
                    "kind": kind,
                    "segment_start_s": float(sidecar.get("segment_start_s", 0.0)),
                    "segment_end_s": float(sidecar.get("segment_end_s", -1.0)),
                    "target_user_id": str(sidecar.get("target_user_id") or ""),
                    "camera_id": str(sidecar.get("camera_id") or ""),
                    "lighting": str(sidecar.get("lighting") or "unknown"),
                    "distance_level": str(sidecar.get("distance_level") or "unknown"),
                    "occlusion_level": str(sidecar.get("occlusion_level") or "unknown"),
                    "multi_person": bool(sidecar.get("multi_person", False)),
                    "target_visible": bool(sidecar.get("target_visible", True)),
                    "authorized_for_training": bool(sidecar.get("authorized_for_training", False)),
                    "notes": str(sidecar.get("notes") or ""),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a V3 scene-aware manifest from local authorized videos and sidecars.")
    parser.add_argument("--input-dir", action="append", default=[str(LAB / "datasets")])
    parser.add_argument("--taxonomy", default=str(LAB / "configs" / "scene_taxonomy.v3.yaml"))
    parser.add_argument("--output", default=str(LAB / "manifests" / "scene_manifest.v3.csv"))
    parser.add_argument("--report", default=str(LAB / "reports" / "scene_manifest.v3.summary.json"))
    args = parser.parse_args()

    taxonomy = load_yaml(Path(args.taxonomy))
    rows = build_rows([Path(p).expanduser().resolve() for p in args.input_dir], taxonomy)
    write_csv(Path(args.output), rows)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": len(rows),
        "by_kind": {},
        "by_scene": {},
        "authorized_rows": sum(1 for row in rows if row["authorized_for_training"]),
    }
    for row in rows:
        summary["by_kind"][row["kind"]] = summary["by_kind"].get(row["kind"], 0) + 1
        summary["by_scene"][row["scene_type"]] = summary["by_scene"].get(row["scene_type"], 0) + 1
    Path(args.report).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
