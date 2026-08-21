from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import cv2


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data_private" / "camera_scene" / "raw_videos"


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a local camera or stream into the private scene dataset folder.")
    parser.add_argument("--source", default="0", help="Camera index or stream/video source.")
    parser.add_argument("--output-dir", default=str(DEFAULT_DIR))
    parser.add_argument("--name", default=None, help="Optional output filename stem.")
    parser.add_argument("--fps", type=float, default=20.0)
    parser.add_argument("--duration", type=float, default=None, help="Optional maximum duration in seconds.")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--no-display", action="store_true")
    args = parser.parse_args()

    source = int(args.source) if args.source.isdigit() else args.source
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.name or datetime.now().strftime("scene_%Y%m%d_%H%M%S")
    out_path = out_dir / f"{stem}.mp4"

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open source: {args.source}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or args.width)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or args.height)
    fps = cap.get(cv2.CAP_PROP_FPS) or args.fps
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

    print(f"[recording] {out_path}")
    if args.duration is not None:
        print(f"Auto-stop after {args.duration:.1f}s")
    if not args.no_display:
        print("Press 'q' or ESC to stop.")
    max_frames = None if args.duration is None else int(max(1, round(args.duration * fps)))
    frame_count = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        writer.write(frame)
        frame_count += 1
        if max_frames is not None and frame_count >= max_frames:
            break
        if not args.no_display:
            cv2.imshow("Capture Scene Video", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord("q"):
                break

    cap.release()
    writer.release()
    if not args.no_display:
        cv2.destroyAllWindows()
    print(f"[saved] {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
