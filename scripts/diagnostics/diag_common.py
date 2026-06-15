from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse, urlunparse

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DEVICE_MAC = "53:57:08:00:00:01"
RUNTIME_DIR = PROJECT_ROOT / "runtime_logs" / "diagnostics"


class DiagnosticError(RuntimeError):
    pass


def now_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(message: str) -> None:
    print(f"[{now_text()}] {message}", flush=True)


def warn(message: str) -> None:
    log(f"WARN {message}")


def error(message: str) -> None:
    log(f"ERROR {message}")


def ok(message: str) -> None:
    log(f"OK {message}")


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)


def build_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Backend base URL. Default: {DEFAULT_BASE_URL}")
    parser.add_argument("--timeout", type=float, default=8.0, help="HTTP timeout seconds. Default: 8")
    return parser


def join_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/") + "/"
    return urljoin(base, path.lstrip("/"))


def to_ws_url(base_url: str, path: str) -> str:
    parsed = urlparse(join_url(base_url, path))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def request_json(
    method: str,
    base_url: str,
    path: str,
    *,
    timeout: float = 8.0,
    token: str | None = None,
    json_body: Any | None = None,
    expected_statuses: Iterable[int] = (200,),
) -> tuple[bool, Any, float, int | None]:
    url = join_url(base_url, path)
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    start = time.perf_counter()
    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            json=json_body,
            timeout=timeout,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
    except requests.RequestException as exc:
        return False, f"{type(exc).__name__}: {exc}", (time.perf_counter() - start) * 1000, None

    status_ok = response.status_code in set(expected_statuses)
    try:
        payload: Any = response.json()
    except ValueError:
        payload = response.text[:1000]
    return status_ok, payload, elapsed_ms, response.status_code


def probe_get(base_url: str, path: str, *, timeout: float = 8.0, token: str | None = None) -> bool:
    ok_flag, payload, elapsed_ms, status = request_json("GET", base_url, path, timeout=timeout, token=token)
    label = f"GET {path} status={status} elapsed={elapsed_ms:.0f}ms"
    if ok_flag:
        ok(label)
        if isinstance(payload, dict):
            compact = summarize_dict(payload)
            if compact:
                log(f"  {compact}")
        elif isinstance(payload, list):
            log(f"  list items={len(payload)}")
        return True
    error(f"{label} payload={payload}")
    return False


def summarize_dict(payload: dict[str, Any], *, max_items: int = 8) -> str:
    parts: list[str] = []
    for index, (key, value) in enumerate(payload.items()):
        if index >= max_items:
            parts.append("...")
            break
        if isinstance(value, (str, int, float, bool)) or value is None:
            parts.append(f"{key}={value}")
        elif isinstance(value, list):
            parts.append(f"{key}=list[{len(value)}]")
        elif isinstance(value, dict):
            parts.append(f"{key}=dict[{len(value)}]")
    return " ".join(parts)


def ensure_runtime_dir() -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return RUNTIME_DIR


def default_score_payload(device_id: str = DEFAULT_DEVICE_MAC) -> dict[str, Any]:
    return {
        "elderly_id": "diagnostic-elder",
        "device_id": device_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "heart_rate": 82,
        "spo2": 97,
        "sbp": 122,
        "dbp": 78,
        "body_temp": 36.6,
        "fall_detection": False,
        "data_accuracy": 98,
    }


def default_warning_payload() -> dict[str, Any]:
    return {
        "current_data": {
            "heart_rate": 82,
            "spo2": 97,
            "sbp": 122,
            "dbp": 78,
            "body_temp": 36.6,
            "fall_detection": False,
            "data_accuracy": 98,
        }
    }


def read_stream_frames(
    url: str,
    *,
    timeout: float,
    duration: float,
    chunk_size: int = 4096,
) -> dict[str, Any]:
    start = time.perf_counter()
    frames = 0
    total_bytes = 0
    last_frame_at = start
    buffer = bytearray()
    last_log = start

    with requests.get(url, stream=True, timeout=timeout, headers={"Accept": "*/*"}) as response:
        content_type = response.headers.get("content-type", "")
        log(f"stream opened: status={response.status_code} content-type={content_type}")
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=chunk_size):
            now = time.perf_counter()
            if duration > 0 and now - start >= duration:
                break
            if not chunk:
                continue
            total_bytes += len(chunk)
            buffer.extend(chunk)

            while True:
                soi = buffer.find(b"\xff\xd8")
                eoi = buffer.find(b"\xff\xd9", soi + 2 if soi >= 0 else 0)
                if soi < 0 or eoi < 0:
                    if len(buffer) > 2_000_000:
                        del buffer[:-128]
                    break
                frame = bytes(buffer[soi : eoi + 2])
                del buffer[: eoi + 2]
                frames += 1
                last_frame_at = now
                elapsed = max(now - start, 0.001)
                fps = frames / elapsed
                log(f"frame={frames} frame_bytes={len(frame)} total_bytes={total_bytes} fps={fps:.2f}")

            if now - last_log >= 2.0 and frames == 0:
                log(f"waiting for JPEG frames... received_bytes={total_bytes}")
                last_log = now
            if now - last_frame_at > timeout and total_bytes > 0:
                warn(f"stream receiving bytes but no complete JPEG frame for {timeout:.0f}s")
                last_frame_at = now

    elapsed = time.perf_counter() - start
    return {
        "frames": frames,
        "total_bytes": total_bytes,
        "elapsed_seconds": elapsed,
        "fps": frames / elapsed if elapsed > 0 else 0,
    }


async def watch_ws(
    url: str,
    *,
    duration: float,
    max_message_preview: int = 180,
) -> dict[str, Any]:
    import websockets

    start = time.perf_counter()
    count = 0
    total_bytes = 0
    log(f"connecting {url}")
    async with websockets.connect(url, max_size=None) as websocket:
        ok("websocket opened")
        while True:
            if duration > 0 and time.perf_counter() - start >= duration:
                break
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5)
            except asyncio.TimeoutError:
                log("waiting for websocket message...")
                continue
            count += 1
            if isinstance(message, bytes):
                size = len(message)
                preview = message[:24].hex()
                kind = "bytes"
            else:
                encoded = message.encode("utf-8", errors="replace")
                size = len(encoded)
                preview = message.replace("\n", "\\n")[:max_message_preview]
                kind = "text"
            total_bytes += size
            elapsed = max(time.perf_counter() - start, 0.001)
            log(f"message={count} kind={kind} bytes={size} total_bytes={total_bytes} rate={count / elapsed:.2f}/s preview={preview}")
    elapsed = time.perf_counter() - start
    return {"messages": count, "total_bytes": total_bytes, "elapsed_seconds": elapsed}


def exit_with_summary(successes: int, failures: int) -> None:
    log(f"summary success={successes} failure={failures}")
    raise SystemExit(0 if failures == 0 else 1)


def run_async(coro: Any) -> Any:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(coro)
