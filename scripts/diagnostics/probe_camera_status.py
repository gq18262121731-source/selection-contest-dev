from __future__ import annotations

from diag_common import build_parser, exit_with_summary, probe_get


def main() -> None:
    parser = build_parser("Probe camera registration, source, runtime, and detection status.")
    args = parser.parse_args()

    paths = [
        "/api/v1/camera-sources",
        "/api/v1/camera-sources/active",
        "/api/v1/camera-sources/active/status",
        "/api/v1/camera-sources/active/stream-status",
        "/api/v1/camera/status",
        "/api/v1/camera/stream-status",
        "/api/v1/camera/audio/status",
        "/api/v1/camera/fall-detection/status",
        "/api/v1/camera/pose-detection/status",
        "/api/v1/target-users/external-camera/health",
    ]
    successes = 0
    failures = 0
    for path in paths:
        if probe_get(args.base_url, path, timeout=args.timeout):
            successes += 1
        else:
            failures += 1
    exit_with_summary(successes, failures)


if __name__ == "__main__":
    main()
