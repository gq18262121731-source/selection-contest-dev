from __future__ import annotations

from diag_common import build_parser, error, join_url, log, read_stream_frames


def main() -> None:
    parser = build_parser("Watch MJPEG camera streams and print every received JPEG frame.")
    parser.add_argument("--path", default="", help="Specific stream path or full URL. If omitted, tries known camera streams.")
    parser.add_argument("--duration", type=float, default=0.0, help="Run seconds. 0 means forever.")
    args = parser.parse_args()

    default_paths = [
        "/api/v1/camera-sources/active/stream.mjpg",
        "/api/v1/camera/stream.mjpg",
        "/api/v1/camera/stream.processed.mjpg",
        "/api/v1/camera/stream.detect.mjpg",
        "/api/v1/camera/stream.pose.mjpg",
    ]
    paths = [args.path] if args.path else default_paths
    last_error = ""
    for path in paths:
        url = path if path.startswith("http://") or path.startswith("https://") else join_url(args.base_url, path)
        log(f"connecting {url}")
        try:
            summary = read_stream_frames(url, timeout=args.timeout, duration=args.duration)
            log(f"summary {summary}")
            if summary["frames"] > 0:
                return
            last_error = "stream ended without complete JPEG frames"
            error(last_error)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            error(last_error)
    raise SystemExit(f"No usable stream found. Last error: {last_error}")


if __name__ == "__main__":
    main()
