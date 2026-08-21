from __future__ import annotations

import argparse
import json
import socket
import time
from pathlib import Path


STREAM_MAP = {
    "main": "av0_0",
    "mainstream": "av0_0",
    "av0_0": "av0_0",
    "sub": "av0_1",
    "substream": "av0_1",
    "av0_1": "av0_1",
}


def normalize_stream(value: str) -> str:
    return STREAM_MAP.get((value or "").strip().lower(), "av0_1")


def normalize_transport(value: str) -> str:
    value = (value or "").strip().lower()
    return value if value in {"tcp", "udp"} else "tcp"


def build_rtsp_url(args: argparse.Namespace) -> str:
    if args.source:
        return args.source
    if not args.host:
        raise ValueError("需要提供 --host 摄像头IP，或者直接提供 --source RTSP地址")
    stream = normalize_stream(args.stream)
    transport = normalize_transport(args.transport)
    return f"rtsp://{args.username}:{args.password}@{args.host}:{args.rtsp_port}/{transport}/{stream}"


def check_tcp_port(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def mask_secret(text: str, password: str) -> str:
    return text.replace(password, "***") if password else text


def probe_video(source: str, duration_seconds: float, output: Path) -> dict[str, object]:
    try:
        import cv2
    except ImportError:
        return {
            "opened": False,
            "frames_read": 0,
            "effective_fps": 0,
            "sample_frame_path": None,
            "error": "OPENCV_NOT_INSTALLED: 请先执行 pip install opencv-python",
        }

    cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        return {
            "opened": False,
            "frames_read": 0,
            "effective_fps": 0,
            "sample_frame_path": None,
        }

    started = time.perf_counter()
    frames = 0
    first_frame_saved = False
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    reported_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        while time.perf_counter() - started < duration_seconds:
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            frames += 1
            if width <= 0 or height <= 0:
                height, width = frame.shape[:2]
            if not first_frame_saved:
                cv2.imwrite(str(output), frame)
                first_frame_saved = True
    finally:
        cap.release()

    elapsed = max(time.perf_counter() - started, 0.001)
    return {
        "opened": True,
        "frames_read": frames,
        "elapsed_seconds": round(elapsed, 3),
        "effective_fps": round(frames / elapsed, 3),
        "reported_width": width,
        "reported_height": height,
        "reported_fps": round(reported_fps, 3),
        "sample_frame_path": str(output.resolve()) if first_frame_saved else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe xstrive/XSWCAM RTSP camera stream.")
    parser.add_argument("--source", default="", help="完整 RTSP 地址；提供后会忽略 host/password 等参数")
    parser.add_argument("--host", default="", help="摄像头局域网 IP，例如 192.168.1.126")
    parser.add_argument("--username", default="admin", help="摄像头账号，通常是 admin")
    parser.add_argument("--password", default="", help="摄像头明文密码")
    parser.add_argument("--rtsp-port", type=int, default=10554, help="RTSP 端口，迅思维常见为 10554")
    parser.add_argument("--onvif-port", type=int, default=10080, help="ONVIF 端口，迅思维常见为 10080")
    parser.add_argument("--transport", default="tcp", choices=["tcp", "udp"], help="RTSP 传输方式")
    parser.add_argument("--stream", default="sub", help="main/sub/av0_0/av0_1")
    parser.add_argument("--duration-seconds", type=float, default=8.0, help="拉流测试时长")
    parser.add_argument("--output", default="artifacts/camera_probe_frame.jpg", help="首帧截图保存位置")
    args = parser.parse_args()

    source = build_rtsp_url(args)
    output = Path(args.output)
    tcp_checks: dict[str, bool] = {}
    if args.host:
        tcp_checks = {
            f"rtsp_port_{args.rtsp_port}": check_tcp_port(args.host, args.rtsp_port),
            f"onvif_port_{args.onvif_port}": check_tcp_port(args.host, args.onvif_port),
            "http_port_80": check_tcp_port(args.host, 80),
        }

    video_result = probe_video(source, max(1.0, args.duration_seconds), output)
    result = {
        "rtsp_url": mask_secret(source, args.password),
        "tcp_checks": tcp_checks,
        "video": video_result,
        "success": bool(video_result.get("opened") and video_result.get("frames_read", 0) > 0),
        "next_hint": (
            "成功：已经能读取摄像头画面，可以进入二次开发。"
            if video_result.get("opened") and video_result.get("frames_read", 0) > 0
            else "失败：请先检查供电、网线、IP、明文密码、RTSP 路径。"
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
