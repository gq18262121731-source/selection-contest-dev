from __future__ import annotations

from pathlib import Path

import requests

from diag_common import build_parser, ensure_runtime_dir, exit_with_summary, join_url, log, ok, error


def fetch_snapshot(base_url: str, path: str, timeout: float, output_dir: Path) -> bool:
    url = join_url(base_url, path)
    try:
        response = requests.get(url, timeout=timeout, headers={"Accept": "image/*,*/*"})
    except requests.RequestException as exc:
        error(f"GET {path} failed: {type(exc).__name__}: {exc}")
        return False
    content_type = response.headers.get("content-type", "")
    if response.status_code != 200:
        error(f"GET {path} status={response.status_code} content-type={content_type} body={response.text[:300]}")
        return False
    data = response.content
    if len(data) < 1000:
        error(f"GET {path} returned too little data: bytes={len(data)} content-type={content_type}")
        return False
    suffix = ".jpg" if b"\xff\xd8" in data[:16] else ".bin"
    file_name = path.strip("/").replace("/", "_").replace(".", "_") + suffix
    target = output_dir / file_name
    target.write_bytes(data)
    ok(f"snapshot {path} bytes={len(data)} content-type={content_type} saved={target}")
    return True


def main() -> None:
    parser = build_parser("Fetch camera snapshots and save them to runtime_logs/diagnostics.")
    args = parser.parse_args()
    output_dir = ensure_runtime_dir()
    log(f"snapshot output dir: {output_dir}")
    paths = [
        "/api/v1/camera-sources/active/snapshot",
        "/api/v1/camera/snapshot",
        "/api/v1/camera/processed-snapshot",
    ]
    successes = 0
    failures = 0
    for path in paths:
        if fetch_snapshot(args.base_url, path, args.timeout, output_dir):
            successes += 1
        else:
            failures += 1
    exit_with_summary(successes, failures)


if __name__ == "__main__":
    main()
