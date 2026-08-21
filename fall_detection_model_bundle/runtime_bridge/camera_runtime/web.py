from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlparse
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .service import CameraRuntime


def build_handler(runtime: CameraRuntime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CameraRuntime/2.0"

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorized():
                return
            if self.path in ("/", "/viewer"):
                self._send_html()
                return
            if self.path == "/health":
                self._send_health()
                return
            if self.path == "/snapshot.jpg":
                self._send_snapshot()
                return
            if self.path == "/stream.mjpg":
                self._send_mjpeg()
                return
            if self.path.startswith("/api/v1/camera/health"):
                self._send_health()
                return
            if self.path.startswith("/api/v1/camera/snapshot"):
                self._send_snapshot()
                return
            if self.path.startswith("/api/v1/camera/stream.mjpg"):
                self._send_mjpeg()
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized():
                return
            if self.path.startswith("/api/v1/camera/stream/switch"):
                self._switch_stream()
                return
            if self.path.startswith("/api/v1/camera/stop"):
                self._stop_runtime()
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def _authorized(self) -> bool:
            if not runtime.viewer_auth_enabled:
                return True
            header = self.headers.get("Authorization", "")
            if not header.startswith("Basic "):
                self._request_auth()
                return False
            try:
                encoded = header.split(" ", 1)[1].strip()
                decoded = base64.b64decode(encoded).decode("utf-8")
            except Exception:
                self._request_auth()
                return False
            username, _, password = decoded.partition(":")
            if username != runtime.viewer_auth_username or password != runtime.viewer_auth_password:
                self._request_auth()
                return False
            return True

        def _request_auth(self) -> None:
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("WWW-Authenticate", 'Basic realm="CameraRuntime"')
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _send_html(self) -> None:
            html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Camera Runtime Viewer</title>
</head>
<body style="margin:0;background:#0b1220;color:#f5f7fb;font-family:Arial,sans-serif;">
  <div style="max-width:1100px;margin:0 auto;padding:20px;">
    <h2>Camera Runtime Viewer</h2>
    <p>Source: <code>{runtime.camera_config.masked_rtsp_url}</code></p>
    <p><a href="/health" style="color:#8bd3ff">/health</a> |
       <a href="/snapshot.jpg" style="color:#8bd3ff">/snapshot.jpg</a> |
       <a href="/stream.mjpg" style="color:#8bd3ff">/stream.mjpg</a></p>
    <img src="/stream.mjpg" alt="camera stream" style="width:100%;max-width:100%;background:#000;">
  </div>
</body>
</html>"""
            payload = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_health(self) -> None:
            state = runtime.frame_store.snapshot()
            payload = {
                "running": state.running,
                "source": runtime.camera_config.masked_rtsp_url,
                "stream": runtime.camera_config.stream,
                "transport": runtime.camera_config.transport,
                "rtsp_port": runtime.camera_config.rtsp_port,
                "has_frame": state.latest_jpeg is not None,
                "latest_frame_at": state.latest_frame_at,
                "frame_count": state.frame_count,
                "last_error": state.last_error,
                "last_opened_at": state.last_opened_at,
                "reconnect_count": state.reconnect_count,
                "consecutive_failures": state.consecutive_failures,
                "current_stream": state.current_stream,
            }
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_snapshot(self) -> None:
            state = runtime.frame_store.snapshot()
            if state.latest_jpeg is None:
                body = json.dumps({"error": state.last_error or "No frame yet"}, ensure_ascii=False).encode("utf-8")
                self.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(state.latest_jpeg)))
            self.end_headers()
            self.wfile.write(state.latest_jpeg)

        def _send_mjpeg(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()

            last_seen = 0
            while True:
                state = runtime.frame_store.snapshot()
                if state.latest_jpeg is None or state.frame_count == last_seen:
                    time.sleep(0.05)
                    continue
                last_seen = state.frame_count
                try:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(state.latest_jpeg)}\r\n\r\n".encode("ascii"))
                    self.wfile.write(state.latest_jpeg)
                    self.wfile.write(b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    break

        def _switch_stream(self) -> None:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            stream = (params.get("stream", [""])[0] or "").strip()
            if stream not in {"av0_0", "av0_1"}:
                body = json.dumps({"error": "stream must be av0_0 or av0_1"}, ensure_ascii=False).encode("utf-8")
                self.send_response(HTTPStatus.BAD_REQUEST)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            runtime.switch_stream(stream)
            body = json.dumps({"ok": True, "stream": stream}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stop_runtime(self) -> None:
            runtime.stop()
            body = json.dumps({"ok": True, "stopped": True}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def create_http_server(runtime: CameraRuntime, listen_host: str, listen_port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((listen_host, listen_port), build_handler(runtime))
