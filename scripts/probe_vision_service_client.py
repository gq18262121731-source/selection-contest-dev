#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.vision_service_client import VisionServiceClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe a Vision Service through the read-only VisionServiceClient."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8101",
        help="Vision Service base URL.",
    )
    parser.add_argument(
        "--camera-id",
        default="camera_01",
        help="Default camera_id to use for status, source, and latest result calls.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.5,
        help="HTTP timeout in seconds.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = VisionServiceClient(
        base_url=args.base_url,
        default_camera_id=args.camera_id,
        timeout=args.timeout,
    )
    try:
        result = client.probe()
    finally:
        client.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
