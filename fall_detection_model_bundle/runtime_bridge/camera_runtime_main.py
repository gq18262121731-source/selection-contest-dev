from __future__ import annotations

import argparse
import json
from pathlib import Path

from camera_runtime.config import load_runtime_config
from camera_runtime.logging_utils import setup_logging
from camera_runtime.service import CameraRuntime
from camera_runtime.web import create_http_server


def main() -> int:
    parser = argparse.ArgumentParser(description="Camera runtime main entry.")
    parser.add_argument("--config", default="camera_live_config.json")
    parser.add_argument("--stream", default="")
    parser.add_argument("--listen-port", type=int, default=0)
    parser.add_argument("--listen-host", default="")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    runtime_config = load_runtime_config(config_path)
    if args.stream:
        runtime_config.camera.stream = args.stream
    if args.listen_port:
        runtime_config.viewer.listen_port = args.listen_port
    if args.listen_host:
        runtime_config.viewer.listen_host = args.listen_host

    setup_logging(Path(runtime_config.viewer.log_dir))
    runtime = CameraRuntime(
        camera_config=runtime_config.camera,
        jpeg_quality=runtime_config.viewer.jpeg_quality,
        frame_interval_seconds=runtime_config.viewer.frame_interval_seconds,
        viewer_auth_enabled=runtime_config.viewer.auth_enabled,
        viewer_auth_username=runtime_config.viewer.auth_username,
        viewer_auth_password=runtime_config.viewer.auth_password,
    )
    runtime.start()

    server = create_http_server(
        runtime,
        listen_host=runtime_config.viewer.listen_host,
        listen_port=runtime_config.viewer.listen_port,
    )

    print(
        json.dumps(
            {
                "listen": f"http://{runtime_config.viewer.listen_host}:{runtime_config.viewer.listen_port}/viewer",
                "source": runtime.camera_config.masked_rtsp_url,
                "log_dir": runtime_config.viewer.log_dir,
            },
            ensure_ascii=False,
        )
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
