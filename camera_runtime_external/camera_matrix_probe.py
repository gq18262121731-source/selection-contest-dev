from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

import cv2


@dataclass
class ProbeResult:
    url: str
    opened: bool
    frames: int


def try_url(url: str, read_attempts: int = 30) -> ProbeResult:
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    opened = cap.isOpened()
    frames = 0
    if opened:
        for _ in range(read_attempts):
            ok, frame = cap.read()
            if ok and frame is not None:
                frames += 1
                break
    cap.release()
    return ProbeResult(url=url, opened=opened, frames=frames)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe a matrix of RTSP URLs.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--usernames", nargs="+", default=["admin"])
    parser.add_argument("--passwords", nargs="+", required=True)
    parser.add_argument("--ports", nargs="+", type=int, default=[10554, 554])
    parser.add_argument("--transports", nargs="+", default=["tcp", "udp"])
    parser.add_argument("--streams", nargs="+", default=["av0_1", "av0_0"])
    args = parser.parse_args()

    results: list[ProbeResult] = []
    for username in args.usernames:
        for password in args.passwords:
            for port in args.ports:
                for transport in args.transports:
                    for stream in args.streams:
                        url = f"rtsp://{username}:{password}@{args.host}:{port}/{transport}/{stream}"
                        results.append(try_url(url))

    print(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

