from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2


LABEL_KEYS = {
    ord("1"): "fall",
    ord("2"): "fallen",
    ord("3"): "lie_down",
    ord("4"): "sit_down",
    ord("5"): "bending",
    ord("6"): "walking",
    ord("7"): "other",
    ord("8"): "recovery",
}


def draw_overlay(frame, label: str, frame_idx: int, total: int, start_frame: int | None, segments: list[dict], playing: bool) -> None:
    lines = [
        f"label={label}",
        f"frame={frame_idx}/{total - 1}",
        f"segments={len(segments)}",
        f"mark_start={start_frame if start_frame is not None else '-'}",
        "SPACE play/pause | a/d +/-1 | j/l +/-15",
        "1-8 choose label | [ mark start | ] mark end/save",
        "u undo | s save | q/ESC quit",
        f"state={'playing' if playing else 'paused'}",
    ]
    y = 24
    for text in lines:
        cv2.putText(frame, text, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
        y += 24


def save_annotations(out_path: Path, video_path: Path, fps: float, total_frames: int, segments: list[dict]) -> None:
    payload = {
        "video_path": str(video_path),
        "fps": fps,
        "total_frames": total_frames,
        "segments": segments,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[saved] {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive event-level annotation for fall detection videos.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", default=None, help="Optional output JSON path. Defaults next to annotations dir.")
    args = parser.parse_args()

    video_path = Path(args.video)
    out_path = Path(args.output) if args.output else video_path.with_suffix(".events.json")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 20.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    playing = False
    label = "fall"
    start_frame = None
    frame_idx = 0
    segments: list[dict] = []

    def read_frame(idx: int):
        idx = max(0, min(total_frames - 1, idx))
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            return idx, None
        return idx, frame

    frame_idx, frame = read_frame(frame_idx)
    if frame is None:
        raise RuntimeError("Failed to read first frame.")

    while True:
        show = frame.copy()
        draw_overlay(show, label, frame_idx, total_frames, start_frame, segments, playing)
        cv2.imshow("Annotate Fall Events", show)

        delay = 30 if playing else 0
        key = cv2.waitKey(delay) & 0xFF
        if playing and key == 255:
            next_idx = min(total_frames - 1, frame_idx + 1)
            if next_idx == frame_idx:
                playing = False
            frame_idx, frame = read_frame(next_idx)
            continue

        if key in (27, ord("q")):
            break
        if key == ord(" "):
            playing = not playing
            continue
        if key == ord("a"):
            frame_idx, frame = read_frame(frame_idx - 1)
            continue
        if key == ord("d"):
            frame_idx, frame = read_frame(frame_idx + 1)
            continue
        if key == ord("j"):
            frame_idx, frame = read_frame(frame_idx - 15)
            continue
        if key == ord("l"):
            frame_idx, frame = read_frame(frame_idx + 15)
            continue
        if key == ord("["):
            start_frame = frame_idx
            print(f"[mark] start={start_frame}")
            continue
        if key == ord("]"):
            if start_frame is None:
                print("[warn] mark start first with [")
                continue
            end_frame = frame_idx
            if end_frame < start_frame:
                start_frame, end_frame = end_frame, start_frame
            segments.append(
                {
                    "label": label,
                    "start_frame": int(start_frame),
                    "end_frame": int(end_frame),
                    "start_s": round(start_frame / fps, 4),
                    "end_s": round(end_frame / fps, 4),
                }
            )
            print(f"[segment] {label}: {start_frame} -> {end_frame}")
            start_frame = None
            continue
        if key == ord("u"):
            if segments:
                removed = segments.pop()
                print(f"[undo] {removed}")
            continue
        if key == ord("s"):
            save_annotations(out_path, video_path, fps, total_frames, segments)
            continue
        if key in LABEL_KEYS:
            label = LABEL_KEYS[key]
            print(f"[label] {label}")

    save_annotations(out_path, video_path, fps, total_frames, segments)
    cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
