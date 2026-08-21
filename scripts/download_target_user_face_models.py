from __future__ import annotations

from pathlib import Path
import sys

import requests


ASSET_DIR = Path(__file__).resolve().parents[1] / "data" / "target_user_assets"
FILES = {
    "face_detection_yunet.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    with dest.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)


def main() -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        dest = ASSET_DIR / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"[skip] {dest}")
            continue
        print(f"[download] {url}")
        download(url, dest)
        print(f"[saved] {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
