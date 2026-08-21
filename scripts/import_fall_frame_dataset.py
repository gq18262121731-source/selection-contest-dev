from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert fall/nofall frame folders into labeled evaluation videos.")
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "data" / "fall_eval" / "downloads" / "personal-dataset-raw-train" / "personal-dataset-raw-train",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "data" / "fall_eval" / "videos",
    )
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def frame_number(path: Path) -> int:
    match = re.search(r"_frame_(\d+)$", path.stem)
    return int(match.group(1)) if match else 0


def group_frames(folder: Path) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for image in folder.glob("*.jpg"):
        prefix = image.stem.rsplit("_frame_", 1)[0]
        groups.setdefault(prefix, []).append(image)
    for frames in groups.values():
        frames.sort(key=frame_number)
    return groups


def write_video(frames: list[Path], output: Path, *, fps: float, overwrite: bool) -> dict[str, object]:
    if output.exists() and not overwrite:
        return {"output": str(output), "frames": len(frames), "skipped": True}
    first = cv2.imread(str(frames[0]))
    if first is None:
        raise RuntimeError(f"Could not read first frame: {frames[0]}")
    height, width = first.shape[:2]
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Could not write video: {output}")
    for frame_path in frames:
        frame = cv2.imread(str(frame_path))
        if frame is None:
            continue
        if frame.shape[1] != width or frame.shape[0] != height:
            frame = cv2.resize(frame, (width, height))
        writer.write(frame)
    writer.release()
    return {"output": str(output), "frames": len(frames), "skipped": False}


def main() -> int:
    args = parse_args()
    mapping = {"fall": "fall", "nofall": "normal"}
    imported: list[dict[str, object]] = []
    for source_label, target_label in mapping.items():
        folder = args.source / source_label
        if not folder.exists():
            continue
        for group, frames in sorted(group_frames(folder).items()):
            if not frames:
                continue
            output = args.output_root / target_label / f"public_personal_{group}.mp4"
            item = write_video(frames, output, fps=args.fps, overwrite=args.overwrite)
            duration = len(frames) / max(1e-6, args.fps)
            sidecar = output.with_suffix(output.suffix + ".json")
            if target_label == "fall":
                sidecar.write_text(
                    json.dumps({"events": [{"label": "fall", "start_s": 0.0, "end_s": round(duration, 3)}]}, indent=2),
                    encoding="utf-8",
                )
            elif sidecar.exists() and args.overwrite:
                sidecar.unlink()
            imported.append({"label": target_label, "source_group": group, "duration_s": round(duration, 3), **item})
    index = args.output_root.parent / "imported_public_personal_dataset.json"
    index.write_text(
        json.dumps(
            {
                "source": "sumitkumarjethani/fall-detection release v0.1 personal-dataset-raw-train.zip",
                "source_url": "https://github.com/sumitkumarjethani/fall-detection/releases/tag/v0.1",
                "license_note": "Check upstream repository before redistribution or commercial use.",
                "items": imported,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"imported": len(imported), "index": str(index)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
