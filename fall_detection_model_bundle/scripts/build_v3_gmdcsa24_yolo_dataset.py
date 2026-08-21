from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import cv2
import yaml
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"
DATASETS = LAB / "datasets"
REPORTS = LAB / "reports"
CONFIGS = LAB / "configs"

NAMES = {
    0: "person",
    1: "fall",
    2: "fallen",
    3: "lying",
    4: "sitting",
    5: "bending",
    6: "kneeling",
    7: "standing",
}


@dataclass
class VideoItem:
    video_path: Path
    subject: str
    kind: str
    file_name: str
    length_text: str
    description: str


def read_subject_csv(path: Path, kind: str) -> dict[str, tuple[str, str]]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    rows = csv.DictReader(text.splitlines())
    out: dict[str, tuple[str, str]] = {}
    for row in rows:
        file_name = str(row.get("File Name") or row.get("File Name ") or "").strip()
        length = str(row.get("Length") or row.get(" Length") or "").strip()
        desc = str(row.get("Description") or row.get("Description ") or "").strip()
        if file_name:
            out[file_name] = (length, desc)
    return out


def discover_items(extracted_root: Path) -> list[VideoItem]:
    items: list[VideoItem] = []
    for subject_dir in sorted(p for p in extracted_root.rglob("Subject *") if p.is_dir()):
        subject = subject_dir.name.replace(" ", "_").lower()
        fall_meta = read_subject_csv(subject_dir / "Fall.csv", "Fall")
        adl_meta = read_subject_csv(subject_dir / "ADL.csv", "ADL")
        for kind, meta in [("Fall", fall_meta), ("ADL", adl_meta)]:
            video_dir = subject_dir / kind
            if not video_dir.exists():
                continue
            for video_path in sorted(video_dir.glob("*.mp4")):
                length, desc = meta.get(video_path.name, ("", ""))
                items.append(VideoItem(video_path, subject, kind, video_path.name, length, desc))
    return items


def class_from_item(item: VideoItem) -> int:
    if item.kind.lower() == "fall":
        desc = item.description.lower()
        if "ground" in desc or "falling" in desc or "fall" in desc:
            return 1
        return 2
    desc = item.description.lower()
    if "sleep" in desc or "bed" in desc:
        return 3
    if "pick" in desc or "ground" in desc or "bend" in desc:
        return 5
    if "sitting" in desc or "sitting on" in desc or "sit" in desc or "chair" in desc:
        return 4
    if "standing" in desc or "stand" in desc:
        return 7
    return 0


def split_from_subject(subject: str) -> str:
    digits = "".join(ch for ch in subject if ch.isdigit())
    number = int(digits or "0")
    if number == 4:
        return "test"
    if number == 3:
        return "val"
    return "train"


def yolo_line_from_box(box: list[float], cls_id: int, width: int, height: int) -> str:
    x1, y1, x2, y2 = box
    x1 = max(0.0, min(float(width - 1), x1))
    y1 = max(0.0, min(float(height - 1), y1))
    x2 = max(0.0, min(float(width - 1), x2))
    y2 = max(0.0, min(float(height - 1), y2))
    bw = max(1.0, x2 - x1)
    bh = max(1.0, y2 - y1)
    cx = x1 + bw * 0.5
    cy = y1 + bh * 0.5
    return f"{cls_id} {cx / width:.6f} {cy / height:.6f} {bw / width:.6f} {bh / height:.6f}"


def largest_person_box(model: YOLO, frame, *, imgsz: int, conf: float, device: str) -> list[float] | None:
    result = model.predict(frame, verbose=False, imgsz=imgsz, conf=conf, device=device)[0]
    if result.boxes is None or len(result.boxes) == 0:
        return None
    boxes = result.boxes.xyxy.detach().cpu().numpy()
    scores = result.boxes.conf.detach().cpu().numpy()
    best = None
    best_score = -1.0
    for box, score in zip(boxes, scores):
        x1, y1, x2, y2 = [float(v) for v in box]
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        rank = area * float(score)
        if rank > best_score:
            best_score = rank
            best = [x1, y1, x2, y2]
    return best


def sample_indices(frame_count: int, max_frames: int) -> list[int]:
    if frame_count <= 0:
        return []
    if frame_count <= max_frames:
        return list(range(frame_count))
    return sorted({round(i * (frame_count - 1) / max(1, max_frames - 1)) for i in range(max_frames)})


def build_dataset(args: argparse.Namespace) -> dict[str, object]:
    extracted_root = Path(args.extracted_root)
    output_root = Path(args.output)
    if output_root.exists() and args.overwrite:
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    model = YOLO(args.pose_model)
    items = discover_items(extracted_root)
    rows: list[dict[str, object]] = []
    counts: dict[str, int] = {"images": 0, "labels": 0, "skipped_no_box": 0}

    for item in items:
        split = split_from_subject(item.subject)
        cls_id = class_from_item(item)
        cap = cv2.VideoCapture(str(item.video_path))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        indices = set(sample_indices(frame_count, args.max_frames_per_video))
        frame_idx = -1
        written = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1
            if frame_idx not in indices:
                continue
            box = largest_person_box(model, frame, imgsz=args.imgsz, conf=args.conf, device=args.device)
            if box is None:
                counts["skipped_no_box"] += 1
                continue
            height, width = frame.shape[:2]
            stem = f"{item.subject}_{item.kind.lower()}_{Path(item.file_name).stem}_f{frame_idx:05d}"
            image_dir = output_root / "images" / split
            label_dir = output_root / "labels" / split
            image_dir.mkdir(parents=True, exist_ok=True)
            label_dir.mkdir(parents=True, exist_ok=True)
            image_path = image_dir / f"{stem}.jpg"
            label_path = label_dir / f"{stem}.txt"
            cv2.imwrite(str(image_path), frame)
            label_path.write_text(yolo_line_from_box(box, cls_id, width, height) + "\n", encoding="utf-8")
            counts["images"] += 1
            counts["labels"] += 1
            written += 1
            rows.append(
                {
                    "image": str(image_path.resolve()),
                    "label": str(label_path.resolve()),
                    "source_video": str(item.video_path.resolve()),
                    "split": split,
                    "class_id": cls_id,
                    "class_name": NAMES[cls_id],
                    "kind": item.kind,
                    "description": item.description,
                    "frame_idx": frame_idx,
                }
            )
        cap.release()
        print(f"[gmdcsa24] {item.subject} {item.kind}/{item.file_name}: {written} frames -> {NAMES[cls_id]}")

    yaml_path = CONFIGS / "fall_detect_v3_gmdcsa24_autolabel_dataset.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "path": str(output_root.resolve()).replace("\\", "/"),
                "train": "images/train",
                "val": "images/val",
                "test": "images/test",
                "names": NAMES,
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    REPORTS.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output": str(output_root.resolve()),
        "dataset_yaml": str(yaml_path.resolve()),
        "counts": counts,
        "rows": len(rows),
        "autolabel_note": "Boxes are auto-generated with a pose model and must be QA'd before promotion-grade detector training.",
    }
    (REPORTS / "gmdcsa24_yolo_autolabel_dataset.v3.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = LAB / "manifests" / "gmdcsa24_yolo_autolabel_dataset.v3.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a YOLO autolabeled dataset from GMDCSA-24 videos.")
    parser.add_argument(
        "--extracted-root",
        default=str(DATASETS / "external_authorized" / "gmdcsa24" / "extracted"),
    )
    parser.add_argument(
        "--output",
        default=str(DATASETS / "fall_detect_v3_gmdcsa24_autolabel"),
    )
    parser.add_argument("--pose-model", default=str(ROOT / "yolo11n-pose.pt"))
    parser.add_argument("--max-frames-per-video", type=int, default=8)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.18)
    parser.add_argument("--device", default="0")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    report = build_dataset(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
