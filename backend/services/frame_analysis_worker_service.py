from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


class FrameAnalysisWorkerService:
    """Keeps heavyweight single-frame model inference outside FastAPI."""

    def __init__(
        self,
        *,
        project_root: Path,
        timeout_seconds: float = 20.0,
        task: str = "full",
        log_name: str = "frame_analysis_worker_stderr.log",
    ) -> None:
        self._project_root = project_root
        self._timeout_seconds = timeout_seconds
        self._task = task
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._last_error: str | None = None
        self._last_ok_at: float | None = None
        self._started_at: float | None = None
        self._restart_count = 0
        self._log_path = project_root / "runtime_logs" / log_name

    def status(self) -> dict[str, Any]:
        process = self._process
        running = process is not None and process.returncode is None
        return {
            "enabled": True,
            "running": running,
            "pid": process.pid if running and process is not None else None,
            "last_error": self._last_error,
            "last_ok_at": self._last_ok_at,
            "started_at": self._started_at,
            "restart_count": self._restart_count,
            "timeout_seconds": self._timeout_seconds,
            "task": self._task,
        }

    async def analyze_frame(
        self,
        image_bytes: bytes,
        *,
        session_id: str,
        run_pose: bool = True,
        run_fall: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "task": self._task,
            "session_id": session_id,
            "run_pose": run_pose,
            "run_fall": run_fall,
            "image_b64": base64.b64encode(image_bytes).decode("ascii"),
        }
        request = {"id": uuid.uuid4().hex, "task": self._task, "payload": payload}
        async with self._request_lock:
            process = await self._ensure_process()
            assert process.stdin is not None
            assert process.stdout is not None
            try:
                process.stdin.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
                await process.stdin.drain()
                response = await self._read_response(process, request_id=request["id"])
            except Exception as exc:
                await self._restart_process(reason=f"{exc.__class__.__name__}: {exc}")
                raise RuntimeError("FRAME_ANALYSIS_WORKER_TIMEOUT") from exc

        if not response.get("ok"):
            self._last_error = str(response.get("error") or "FRAME_ANALYSIS_FAILED")
            return {
                "ok": False,
                "error": self._last_error,
                "traceback": response.get("traceback"),
            }

        self._last_error = None
        self._last_ok_at = time.time()
        result = response.get("result")
        return result if isinstance(result, dict) else {"ok": False, "error": "FRAME_ANALYSIS_EMPTY_RESULT"}

    async def analyze_pose(self, image_bytes: bytes, *, session_id: str) -> dict[str, Any]:
        payload = {
            "task": "pose",
            "session_id": session_id,
            "image_b64": base64.b64encode(image_bytes).decode("ascii"),
        }
        return await self._send(payload, task="pose")

    async def analyze_fall(self, image_bytes: bytes, *, session_id: str) -> dict[str, Any]:
        payload = {
            "task": "fall",
            "session_id": session_id,
            "image_b64": base64.b64encode(image_bytes).decode("ascii"),
        }
        return await self._send(payload, task="fall")

    async def _send(self, payload: dict[str, Any], *, task: str) -> dict[str, Any]:
        request = {"id": uuid.uuid4().hex, "task": task, "payload": payload}
        async with self._request_lock:
            process = await self._ensure_process()
            assert process.stdin is not None
            assert process.stdout is not None
            try:
                process.stdin.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
                await process.stdin.drain()
                response = await self._read_response(process, request_id=request["id"])
            except Exception as exc:
                await self._restart_process(reason=f"{exc.__class__.__name__}: {exc}")
                raise RuntimeError("FRAME_ANALYSIS_WORKER_TIMEOUT") from exc

        if not response.get("ok"):
            self._last_error = str(response.get("error") or "FRAME_ANALYSIS_FAILED")
            return {"ok": False, "error": self._last_error, "traceback": response.get("traceback")}

        self._last_error = None
        self._last_ok_at = time.time()
        result = response.get("result")
        return result if isinstance(result, dict) else {"ok": False, "error": "FRAME_ANALYSIS_EMPTY_RESULT"}

    async def _read_response(self, process: asyncio.subprocess.Process, *, request_id: str) -> dict[str, Any]:
        assert process.stdout is not None
        deadline = time.monotonic() + self._timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("worker response timeout")
            line = await asyncio.wait_for(process.stdout.readline(), timeout=remaining)
            if not line:
                raise RuntimeError("worker exited without response")
            try:
                response = json.loads(line.decode("utf-8"))
            except Exception:
                self._last_error = f"worker noisy stdout skipped: {line[:160]!r}"
                continue
            if response.get("id") == request_id:
                return response
            self._last_error = f"worker response id mismatch skipped: {response.get('id')}"

    async def _ensure_process(self) -> asyncio.subprocess.Process:
        async with self._lock:
            if self._process is not None and self._process.returncode is None:
                return self._process

            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            stderr = self._log_path.open("ab")
            try:
                self._process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "backend.workers.frame_analysis_worker",
                    cwd=str(self._project_root),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=stderr,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
            finally:
                stderr.close()
            self._started_at = time.time()
            return self._process

    async def _restart_process(self, *, reason: str) -> None:
        self._last_error = reason
        self._restart_count += 1
        process = self._process
        self._process = None
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
