from __future__ import annotations

import json
import re
import os
import socket
import subprocess
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import cv2
import requests

from backend.services.target_user_fall_service import TargetUserFallService


@dataclass(slots=True)
class ExternalCameraEndpoints:
    viewer_url: str = "http://127.0.0.1:8090/viewer"
    health_url: str = "http://127.0.0.1:8090/api/v1/camera/health"
    snapshot_url: str = "http://127.0.0.1:8090/api/v1/camera/snapshot"
    mjpeg_url: str = "http://127.0.0.1:8090/api/v1/camera/stream.mjpg"
    switch_url: str = "http://127.0.0.1:8090/api/v1/camera/stream/switch"


class ExternalCameraBridgeService:
    """Bridge the local camera runtime into the target-only fall detection pipeline."""

    def __init__(self, *, data_root: Path, target_user_fall_service: TargetUserFallService) -> None:
        self._data_root = data_root
        self._target_user_fall_service = target_user_fall_service
        self._endpoints = ExternalCameraEndpoints()
        self._session = requests.Session()
        self._session.headers.update({"Cache-Control": "no-store"})
        self._debug_root = self._data_root / "external_camera_debug"
        self._debug_root.mkdir(parents=True, exist_ok=True)
        self._max_debug_frames = 20
        self._max_snapshot_age_seconds = 6.0
        self._project_root = Path(__file__).resolve().parents[2]
        self._runtime_root = self._resolve_runtime_root()
        self._runtime_config_path = self._runtime_root / "camera_live_config.json"
        self._runtime_config_runtime_path = self._runtime_root / "camera_live_config.runtime.json"
        self._camera_truth_path = self._data_root / "camera_source_of_truth.json"

    def startup_recover(self) -> dict[str, Any]:
        """Attempt to recover the external runtime into the best available source."""
        started = time.perf_counter()
        truth = self.get_camera_source_of_truth()
        health_before = self.health()
        if self._has_fresh_frame(health_before):
            result = {
                "ok": True,
                "status": "already_ready",
                "camera_health": health_before,
                "truth": truth,
            }
            result["bridge_latency_ms"] = int((time.perf_counter() - started) * 1000)
            return result

        probe = self.probe_runtime_candidates(
            host=truth.get("preferred_host") or truth.get("host"),
            username=truth.get("username"),
            password=truth.get("password"),
            rtsp_port=truth.get("rtsp_port"),
            transport=truth.get("transport"),
            stream=truth.get("stream"),
            apply_success=True,
        )
        applied_result = probe.get("applied_result")
        if not isinstance(applied_result, dict):
            applied_result = {}
        health_after = applied_result.get("camera_health") or self.health()
        result = {
            "ok": bool(probe.get("applied")),
            "status": "probe_applied" if probe.get("applied") else "probe_failed",
            "camera_health": health_after,
            "probe": probe,
            "truth": self.get_camera_source_of_truth(),
        }
        result["bridge_latency_ms"] = int((time.perf_counter() - started) * 1000)
        return result

    def health(self) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            response = self._session.get(self._endpoints.health_url, timeout=3)
            response.raise_for_status()
            payload = response.json()
            payload["bridge_status"] = self._classify_bridge_status(payload)
        except (requests.RequestException, ValueError) as exc:
            payload = {
                "running": False,
                "has_frame": False,
                "fresh_frame": False,
                "stale_frame": True,
                "frame_age_seconds": None,
                "last_error": str(exc),
                "bridge_status": "camera_unavailable",
            }
        payload["fresh_frame"] = self._has_fresh_frame(payload)
        payload["candidate_runtime"] = self.get_runtime_config()
        payload["truth"] = self.get_camera_source_of_truth()
        payload["bridge_latency_ms"] = int((time.perf_counter() - started) * 1000)
        payload.update(self._camera_source())
        return payload

    def get_camera_source_of_truth(self) -> dict[str, Any]:
        runtime = self.get_runtime_config(include_secret=True)
        truth = self._read_truth()
        truth.setdefault("camera_id", "camera2")
        truth.setdefault("preferred_host", runtime.get("host"))
        truth.setdefault("host", runtime.get("host"))
        truth.setdefault("username", runtime.get("username"))
        truth.setdefault("password", runtime.get("password"))
        truth.setdefault("rtsp_port", runtime.get("rtsp_port"))
        truth.setdefault("transport", runtime.get("transport"))
        truth.setdefault("stream", runtime.get("stream"))
        truth.setdefault("source_of_truth", "camera_runtime_external")
        truth.setdefault("verified_at", None)
        truth.setdefault("verified_status", "unknown")
        truth.setdefault("fallback_order", [
            {"host": truth.get("host"), "rtsp_port": truth.get("rtsp_port"), "transport": "tcp", "stream": "av0_1"},
            {"host": truth.get("host"), "rtsp_port": truth.get("rtsp_port"), "transport": "tcp", "stream": "av0_0"},
            {"host": truth.get("host"), "rtsp_port": 10554, "transport": "tcp", "stream": "av0_1"},
            {"host": truth.get("host"), "rtsp_port": 10554, "transport": "tcp", "stream": "av0_0"},
        ])
        return truth

    def persist_camera_source_of_truth(
        self,
        *,
        host: str,
        username: str,
        password: str,
        rtsp_port: int,
        transport: str,
        stream: str,
        verified_status: str,
        verification_reason: str | None = None,
    ) -> dict[str, Any]:
        truth = self.get_camera_source_of_truth()
        truth.update(
            {
                "camera_id": "camera2",
                "preferred_host": host,
                "host": host,
                "username": username,
                "password": password,
                "rtsp_port": rtsp_port,
                "transport": transport,
                "stream": stream,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "verified_status": verified_status,
                "verification_reason": verification_reason,
                "source_of_truth": "camera_runtime_external",
            }
        )
        self._write_truth(truth)
        return truth

    def get_runtime_config(self, *, include_secret: bool = False) -> dict[str, Any]:
        raw = self._read_runtime_config()
        camera = raw.get("camera", {}) if isinstance(raw.get("camera"), dict) else {}
        password = str(camera.get("password") or "")
        config = {
            "host": str(camera.get("host") or "192.168.8.248"),
            "username": str(camera.get("username") or "admin"),
            "rtsp_port": int(camera.get("rtsp_port") or 554),
            "transport": str(camera.get("transport") or "tcp"),
            "stream": str(camera.get("stream") or "av0_1"),
            "password_set": bool(password),
            "password_length": len(password),
        }
        if include_secret:
            config["password"] = password
        config["source"] = self._public_probe_config({**config, "password": password})["source"]
        return config

    def configure_runtime(
        self,
        *,
        host: str | None = None,
        username: str | None = None,
        password: str | None = None,
        rtsp_port: int | None = None,
        transport: str | None = None,
        stream: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        raw = self._read_runtime_config()
        camera = raw.setdefault("camera", {})
        if not isinstance(camera, dict):
            camera = {}
            raw["camera"] = camera

        if host is not None:
            camera["host"] = self._clean_host(host)
        if username is not None:
            camera["username"] = self._clean_required_text(username, "username")
        if password is not None and password != "":
            camera["password"] = str(password)
        if rtsp_port is not None:
            camera["rtsp_port"] = self._clean_port(rtsp_port)
        if transport is not None:
            camera["transport"] = self._clean_choice(transport, {"tcp", "udp"}, "transport")
        if stream is not None:
            camera["stream"] = self._clean_choice(stream, {"av0_0", "av0_1"}, "stream")

        raw.setdefault("viewer", {})
        self._normalize_viewer_config(raw)
        self._write_runtime_config(raw)

        config = self.get_runtime_config()
        restart = self._restart_runtime(
            host=config["host"],
            username=config["username"],
            password=str(camera.get("password") or ""),
            rtsp_port=int(config["rtsp_port"]),
            transport=config["transport"],
            stream=config["stream"],
        )
        camera_health = self._wait_for_fresh_camera_frame(timeout_seconds=1.5)
        camera_available = self._has_fresh_frame(camera_health)
        verified_status = "reachable" if camera_available else "unreachable"
        verified_reason = None if camera_available else str(camera_health.get("last_error") or "NO_FRESH_FRAME")
        truth = self.persist_camera_source_of_truth(
            host=config["host"],
            username=config["username"],
            password=str(camera.get("password") or ""),
            rtsp_port=int(config["rtsp_port"]),
            transport=config["transport"],
            stream=config["stream"],
            verified_status=verified_status,
            verification_reason=verified_reason,
        )
        return {
            "ok": restart["ok"] and camera_available,
            "camera_available": camera_available,
            "config": config,
            "restart": restart,
            "camera_health": camera_health,
            "truth": truth,
            "bridge_latency_ms": int((time.perf_counter() - started) * 1000),
            **self._camera_source(),
        }

    def detect_latest(
        self,
        *,
        session_id: str,
        target_only: bool = True,
        include_annotated_image: bool = False,
        speed_mode: str = "balanced",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        camera_health = self.health()
        if camera_health.get("bridge_status") == "camera_unavailable" or not camera_health.get("has_frame"):
            return self._camera_failure_response(
                status="camera_unavailable",
                reason="CAMERA_UNAVAILABLE",
                message="External camera runtime is not reachable or has no frame yet.",
                started=started,
                camera_health=camera_health,
                session_id=session_id,
            )

        health_age = camera_health.get("frame_age_seconds")
        if isinstance(health_age, (int, float)) and health_age > self._max_snapshot_age_seconds:
            return self._camera_failure_response(
                status="camera_frame_stale",
                reason="CAMERA_FRAME_STALE",
                message=f"External camera frame is stale ({health_age:.1f}s old).",
                started=started,
                camera_health=camera_health,
                session_id=session_id,
            )

        try:
            response = self._session.get(self._endpoints.snapshot_url, timeout=5)
            response.raise_for_status()
        except requests.RequestException as exc:
            return self._camera_failure_response(
                status="camera_snapshot_failed",
                reason="CAMERA_SNAPSHOT_FAILED",
                message=str(exc),
                started=started,
                camera_health=camera_health,
                session_id=session_id,
            )

        snapshot_meta = self._snapshot_meta_from_headers(response.headers)
        if snapshot_meta.get("stale"):
            return self._camera_failure_response(
                status="camera_frame_stale",
                reason="CAMERA_FRAME_STALE",
                message="External camera snapshot header reports a stale frame.",
                started=started,
                camera_health=camera_health,
                snapshot_meta=snapshot_meta,
                session_id=session_id,
            )

        image_bytes = response.content
        result = self._target_user_fall_service.detect(
            image_bytes,
            include_annotated_image=include_annotated_image,
            target_only=target_only,
            session_id=session_id,
            speed_mode=speed_mode,
        )
        diagnostics = self._build_diagnostics(result, camera_health=camera_health, snapshot_meta=snapshot_meta)
        result["diagnostics"] = diagnostics
        result["camera_source"] = self._camera_source()
        result["camera_health"] = camera_health
        result["camera_frame"] = {**snapshot_meta, "snapshot_bytes": len(image_bytes)}
        result["bridge_latency_ms"] = int((time.perf_counter() - started) * 1000)
        result["snapshot_bytes"] = len(image_bytes)
        if diagnostics["is_failure"]:
            self._store_failure_frame(image_bytes=image_bytes, session_id=session_id, diagnostics=diagnostics)
        return result

    def refresh_stream(self, *, prefer_stream: str | None = None) -> dict[str, Any]:
        """Ask the camera runtime to reopen/switch the RTSP stream without reloading the web page."""
        started = time.perf_counter()
        before = self.health()
        current = str(before.get("current_stream") or before.get("stream") or "av0_0")
        if prefer_stream in {"av0_0", "av0_1"}:
            next_stream = prefer_stream
        else:
            next_stream = "av0_1" if current == "av0_0" else "av0_0"

        try:
            response = self._session.post(
                self._endpoints.switch_url,
                params={"stream": next_stream},
                timeout=6,
            )
            response.raise_for_status()
            switch_payload = response.json()
            switch_ok = True
            error = None
        except (requests.RequestException, ValueError) as exc:
            switch_payload = {}
            switch_ok = False
            error = str(exc)

        wait_seconds = 2.0 if before.get("has_frame") else 0.8
        after = self._wait_for_fresh_camera_frame(timeout_seconds=wait_seconds)
        camera_available = self._has_fresh_frame(after)
        return {
            "ok": switch_ok and camera_available,
            "switch_ok": switch_ok,
            "camera_available": camera_available,
            "requested_stream": next_stream,
            "before": before,
            "after": after,
            "switch": switch_payload,
            "error": error,
            "bridge_latency_ms": int((time.perf_counter() - started) * 1000),
            **self._camera_source(),
        }

    def probe_runtime_candidates(
        self,
        *,
        host: str | None = None,
        username: str | None = None,
        password: str | None = None,
        rtsp_port: int | None = None,
        transport: str | None = None,
        stream: str | None = None,
        apply_success: bool = True,
    ) -> dict[str, Any]:
        """Probe likely RTSP source variants, then optionally apply the first working one."""
        started = time.perf_counter()
        raw = self._read_runtime_config()
        camera = raw.get("camera", {}) if isinstance(raw.get("camera"), dict) else {}
        current = self.get_runtime_config()

        candidate_password = str(password) if password not in {None, ""} else str(camera.get("password") or "")
        candidate_username = self._clean_required_text(username or current["username"], "username")
        requested = {
            "host": self._clean_host(host or current["host"]),
            "username": candidate_username,
            "password": candidate_password,
            "rtsp_port": self._clean_port(rtsp_port or int(current["rtsp_port"])),
            "transport": self._clean_choice(transport or current["transport"], {"tcp", "udp"}, "transport"),
            "stream": self._clean_choice(stream or current["stream"], {"av0_0", "av0_1"}, "stream"),
        }

        results: list[dict[str, Any]] = []
        winner: dict[str, Any] | None = None
        probe_deadline = time.perf_counter() + 32.0
        candidates = self._build_probe_candidates(requested=requested, current=current, password=candidate_password)
        for candidate in candidates:
            if time.perf_counter() > probe_deadline:
                results.append(
                    {
                        "ok": False,
                        "error": "PROBE_TIMEOUT",
                        "config": candidate,
                        "latency_ms": int((time.perf_counter() - started) * 1000),
                    }
                )
                break
            probe = self._probe_rtsp_candidate(candidate)
            results.append(probe)
            if probe.get("ok"):
                winner = probe
                break

        applied: dict[str, Any] | None = None
        if winner and apply_success:
            cfg = winner["config"]
            applied = self.configure_runtime(
                host=str(cfg["host"]),
                username=str(cfg["username"]),
                password=str(cfg.get("password") or ""),
                rtsp_port=int(cfg["rtsp_port"]),
                transport=str(cfg["transport"]),
                stream=str(cfg["stream"]),
            )

        return {
            "ok": bool(winner),
            "applied": bool(applied and applied.get("camera_available")),
            "winner": self._public_probe_config(winner["config"]) if winner else None,
            "results": [
                {
                    **item,
                    "config": self._public_probe_config(item["config"]),
                }
                for item in results
            ],
            "applied_result": applied,
            "bridge_latency_ms": int((time.perf_counter() - started) * 1000),
            **self._camera_source(),
        }

    def discover_camera_candidates(self, *, subnet: str | None = None, limit: int = 256) -> dict[str, Any]:
        """Find likely camera devices on local IPv4 subnets using bounded port probes."""
        started = time.perf_counter()
        ips = self._build_discovery_ips(subnet=subnet, limit=limit)
        for known_ip in ("192.168.8.254", "192.168.8.248"):
            if known_ip not in ips:
                ips.insert(0, known_ip)
        preferred = str(self.get_camera_source_of_truth().get("preferred_host") or "").strip()
        if preferred and preferred not in ips:
            ips.insert(0, preferred)
        ports = (80, 554, 10554, 10080, 8080)
        port_map: dict[str, list[int]] = {}
        with ThreadPoolExecutor(max_workers=64) as executor:
            futures = {
                executor.submit(self._tcp_open, ip, port, timeout=0.35): (ip, port)
                for ip in ips
                for port in ports
            }
            done, _ = wait(futures.keys(), timeout=20)
            for future in done:
                ip, port = futures[future]
                try:
                    is_open = bool(future.result())
                except Exception:
                    is_open = False
                if is_open:
                    port_map.setdefault(ip, []).append(port)
        devices: list[dict[str, Any]] = []
        for ip, open_ports in port_map.items():
            open_ports = sorted(open_ports)
            if not open_ports:
                continue
            rtsp_describe: list[dict[str, Any]] = []
            if 10554 in open_ports or 554 in open_ports:
                for port in [item for item in (10554, 554) if item in open_ports]:
                    for transport in ("tcp", "udp"):
                        for stream in ("av0_1", "av0_0"):
                            cfg = {
                                "host": ip,
                                "username": "admin",
                                "password": "",
                                "rtsp_port": port,
                                "transport": transport,
                                "stream": stream,
                            }
                            options = self._probe_rtsp_options(cfg)
                            describe = self._probe_rtsp_describe(cfg) if options.get("reachable") else {}
                            rtsp_describe.append(
                                {
                                    "source": self._public_probe_config(cfg)["source"],
                                    "options_status": options.get("status"),
                                    "describe_status": describe.get("status"),
                                    "sdp": describe.get("sdp"),
                                    "auth_scheme": describe.get("auth_scheme"),
                                    "codecs": describe.get("codecs") or [],
                                }
                            )
                            if describe.get("sdp") or describe.get("status") in {401, 403, 404}:
                                break
                        if any(item.get("sdp") for item in rtsp_describe):
                            break
                    if any(item.get("sdp") for item in rtsp_describe):
                        break
            score = 0
            if 10554 in open_ports or 554 in open_ports:
                score += 5
            if 10080 in open_ports:
                score += 4
            if 80 in open_ports or 8080 in open_ports:
                score += 1
            if any(item.get("sdp") for item in rtsp_describe):
                score += 10
            if any(item.get("describe_status") in {401, 403} for item in rtsp_describe):
                score += 4
            devices.append(
                {
                    "host": ip,
                    "open_ports": open_ports,
                    "score": score,
                    "rtsp": rtsp_describe[:4],
                    "suggested": {
                        "host": ip,
                        "rtsp_port": 10554 if 10554 in open_ports else (554 if 554 in open_ports else None),
                        "transport": "tcp",
                        "stream": "av0_1",
                        "username": "admin",
                    },
                }
            )
        devices.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("host") or "")))
        return {
            "ok": True,
            "devices": devices[:20],
            "scanned": len(ips),
            "subnet": subnet or "auto",
            "bridge_latency_ms": int((time.perf_counter() - started) * 1000),
        }

    def _wait_for_fresh_camera_frame(self, *, timeout_seconds: float) -> dict[str, Any]:
        deadline = time.perf_counter() + timeout_seconds
        last_health = self.health()
        while time.perf_counter() < deadline:
            if self._has_fresh_frame(last_health):
                return last_health
            time.sleep(0.5)
            last_health = self.health()
        return last_health

    def _has_fresh_frame(self, health: dict[str, Any]) -> bool:
        age = health.get("frame_age_seconds")
        if not isinstance(age, (int, float)):
            latest_frame_at = health.get("latest_frame_at")
            if isinstance(latest_frame_at, (int, float)):
                age = max(0.0, time.time() - latest_frame_at)
        return bool(
            health.get("has_frame")
            and isinstance(age, (int, float))
            and age <= self._max_snapshot_age_seconds
            and not health.get("stale_frame")
        )

    def _build_discovery_ips(self, *, subnet: str | None, limit: int) -> list[str]:
        if subnet:
            prefix = str(subnet).strip().rsplit(".", 1)[0]
            if prefix.count(".") == 2:
                return [f"{prefix}.{i}" for i in range(1, min(254, max(1, limit)) + 1)]
        prefixes: list[str] = []
        try:
            host_name = socket.gethostname()
            for _, _, _, _, sockaddr in socket.getaddrinfo(host_name, None, family=socket.AF_INET):
                ip = sockaddr[0]
                if ip.startswith("127."):
                    continue
                prefix = ip.rsplit(".", 1)[0]
                if prefix not in prefixes:
                    prefixes.append(prefix)
        except OSError:
            pass
        for fallback in ("192.168.8", "192.168.1", "192.168.0"):
            if fallback not in prefixes:
                prefixes.append(fallback)
        ips: list[str] = []
        for prefix in prefixes[:3]:
            for i in range(1, 255):
                ips.append(f"{prefix}.{i}")
                if len(ips) >= limit:
                    return ips
        return ips

    def _tcp_open(self, host: str, port: int, *, timeout: float) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def _read_runtime_config(self) -> dict[str, Any]:
        for path in (self._runtime_config_runtime_path, self._runtime_config_path):
            if not path.exists():
                continue
            return json.loads(path.read_text(encoding="utf-8-sig"))
        return {"camera": {}, "viewer": {}}

    def _write_runtime_config(self, raw: dict[str, Any]) -> None:
        self._runtime_root.mkdir(parents=True, exist_ok=True)
        self._normalize_viewer_config(raw)
        body = json.dumps(raw, ensure_ascii=False, indent=2)
        self._runtime_config_path.write_text(body + "\n", encoding="utf-8-sig")
        self._runtime_config_runtime_path.write_text(body + "\n", encoding="utf-8-sig")

    def _resolve_runtime_root(self) -> Path:
        local_runtime = self._project_root / "camera_runtime_external"
        if (local_runtime / "camera_runtime_main.py").exists():
            return local_runtime
        external_runtime = Path(r"D:\Program\camear_new")
        if (external_runtime / "camera_runtime_main.py").exists():
            return external_runtime
        return local_runtime

    def _normalize_viewer_config(self, raw: dict[str, Any]) -> None:
        viewer = raw.setdefault("viewer", {})
        if not isinstance(viewer, dict):
            viewer = {}
            raw["viewer"] = viewer
        viewer["listen_host"] = "127.0.0.1"
        viewer["listen_port"] = 8090
        viewer["log_dir"] = str(self._runtime_root / "runtime_logs")
        viewer.setdefault("jpeg_quality", 68)
        viewer.setdefault("frame_interval_seconds", 0.05)
        viewer.setdefault("auth_enabled", False)
        viewer.setdefault("auth_username", "camera")
        viewer.setdefault("auth_password", "camera")

    def _restart_runtime(
        self,
        *,
        host: str,
        username: str,
        password: str,
        rtsp_port: int,
        transport: str,
        stream: str,
    ) -> dict[str, Any]:
        script = self._runtime_root / "camera_runtime_main.py"
        if not script.exists():
            return {"ok": False, "error": f"Runtime entry not found: {script}"}
        log_dir = self._runtime_root / "runtime_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout = log_dir / "camera_runtime_restart.stdout.log"
        stderr = log_dir / "camera_runtime_restart.stderr.log"
        stop_command = (
            "Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty OwningProcess -Unique | "
            "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -eq 'python.exe' -and "
            "$_.CommandLine -match 'camera_runtime_main\\.py|camera_live_server\\.py' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", stop_command],
                check=False,
                timeout=10,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass
        runtime_config = self._runtime_root / "camera_live_config.runtime.json"
        command = [
            self._resolve_python_executable(),
            str(script),
            "--config",
            str(runtime_config),
            "--stream",
            stream,
            "--listen-port",
            "8090",
        ]
        try:
            with stdout.open("w", encoding="utf-8") as out_handle, stderr.open("w", encoding="utf-8") as err_handle:
                process = subprocess.Popen(
                    command,
                    cwd=str(self._runtime_root),
                    stdout=out_handle,
                    stderr=err_handle,
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "pid": process.pid,
            "mode": "background",
            "stdout_log": str(stdout),
            "stderr_log": str(stderr),
        }

    def _resolve_python_executable(self) -> str:
        for candidate in (
            Path(r"C:\Users\YANG\.conda\envs\health\python.exe"),
        ):
            if candidate.exists():
                return str(candidate)
        return "python"

    def _clean_host(self, value: str) -> str:
        host = str(value or "").strip()
        if not host or any(char.isspace() for char in host) or "/" in host or "@" in host:
            raise ValueError("INVALID_CAMERA_HOST")
        return host

    def _clean_required_text(self, value: str, field_name: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"INVALID_CAMERA_{field_name.upper()}")
        return text

    def _clean_port(self, value: int) -> int:
        port = int(value)
        if port < 1 or port > 65535:
            raise ValueError("INVALID_CAMERA_RTSP_PORT")
        return port

    def _clean_choice(self, value: str, choices: set[str], field_name: str) -> str:
        text = str(value or "").strip().lower()
        if text not in choices:
            raise ValueError(f"INVALID_CAMERA_{field_name.upper()}")
        return text

    def _camera_source(self) -> dict[str, str]:
        config = self.get_runtime_config() if self._runtime_config_path.exists() else {}
        return {
            "viewer_url": self._endpoints.viewer_url,
            "snapshot_url": self._endpoints.snapshot_url,
            "mjpeg_url": self._endpoints.mjpeg_url,
            "runtime_root": str(self._runtime_root),
            "rtsp_source": str(config.get("source") or ""),
            "rtsp_host": str(config.get("host") or ""),
            "rtsp_stream": str(config.get("stream") or ""),
        }

    def _read_truth(self) -> dict[str, Any]:
        if not self._camera_truth_path.exists():
            return {}
        try:
            payload = json.loads(self._camera_truth_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_truth(self, payload: dict[str, Any]) -> None:
        self._camera_truth_path.parent.mkdir(parents=True, exist_ok=True)
        self._camera_truth_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _classify_bridge_status(self, payload: dict[str, Any]) -> str:
        if not payload.get("running"):
            return "runtime_not_running"
        if payload.get("has_frame") and self._has_fresh_frame(payload):
            return "ok"
        error_text = str(payload.get("last_error") or "").lower()
        if "timed out" in error_text or "not reachable" in error_text or "connection" in error_text:
            return "rtsp_unreachable"
        if payload.get("has_frame") and not self._has_fresh_frame(payload):
            return "frame_stale"
        return "runtime_no_frame"

    def _build_probe_candidates(
        self,
        *,
        requested: dict[str, Any],
        current: dict[str, Any],
        password: str,
    ) -> list[dict[str, Any]]:
        def unique(values: list[str]) -> list[str]:
            result: list[str] = []
            for value in values:
                text = str(value or "")
                if text in result:
                    continue
                result.append(text)
            return result

        password_candidates = unique([password, "8888888", "888888", "123456", "admin", ""])

        def add_candidate(
            bucket: list[dict[str, Any]],
            *,
            host: str,
            rtsp_port: int,
            transport: str,
            stream: str,
            reason: str,
            candidate_password: str | None = None,
        ) -> None:
            try:
                candidate = {
                    "host": self._clean_host(host),
                    "username": requested["username"],
                    "password": password if candidate_password is None else candidate_password,
                    "rtsp_port": self._clean_port(rtsp_port),
                    "transport": self._clean_choice(transport, {"tcp", "udp"}, "transport"),
                    "stream": self._clean_choice(stream, {"av0_0", "av0_1"}, "stream"),
                    "reason": reason,
                }
            except ValueError:
                return
            key = (
                candidate["host"],
                candidate["rtsp_port"],
                candidate["transport"],
                candidate["stream"],
                candidate["username"],
                candidate.get("password") or "",
            )
            if any(
                (
                    item["host"],
                    item["rtsp_port"],
                    item["transport"],
                    item["stream"],
                    item["username"],
                    item.get("password") or "",
                )
                == key
                for item in bucket
            ):
                return
            bucket.append(candidate)

        candidates: list[dict[str, Any]] = []
        for stream_name in unique([str(requested["stream"]), "av0_1", "av0_0"]):
            for candidate_password in password_candidates:
                add_candidate(
                    candidates,
                    host=str(requested["host"]),
                    rtsp_port=int(requested["rtsp_port"]),
                    transport=str(requested["transport"]),
                    stream=stream_name,
                    reason="requested",
                    candidate_password=candidate_password,
                )

        learned_hosts = unique([
            str(requested["host"]),
            str(current.get("host") or ""),
            "192.168.8.253",
            "192.168.8.254",
            "192.168.8.248",
        ])
        port_order = [int(item) for item in unique([str(requested["rtsp_port"]), "554", "10554"])]
        transport_order = unique([str(requested["transport"]), "tcp", "udp"])
        for host in learned_hosts:
            if not host:
                continue
            for port in port_order:
                for transport in transport_order:
                    for stream_name in ("av0_1", "av0_0"):
                        for candidate_password in password_candidates:
                            add_candidate(
                                candidates,
                                host=host,
                                rtsp_port=port,
                                transport=transport,
                                stream=stream_name,
                                reason="known_camera_variant",
                                candidate_password=candidate_password,
                            )
        return candidates[:48]

    def _probe_rtsp_candidate(self, config: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        url = self._rtsp_url(config)
        options = self._probe_rtsp_options(config)
        if not options.get("reachable"):
            return {
                "ok": False,
                "error": options.get("error") or "RTSP_PORT_UNREACHABLE",
                "rtsp_status": options.get("status"),
                "config": config,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        status = int(options.get("status") or 0)
        if status and status not in {200, 401}:
            return {
                "ok": False,
                "error": f"RTSP_STATUS_{status}",
                "rtsp_status": status,
                "config": config,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        describe = self._probe_rtsp_describe(config)
        describe_status = describe.get("status")
        if describe_status in {401, 403}:
            return {
                "ok": False,
                "error": "RTSP_AUTH_FAILED",
                "rtsp_status": status,
                "describe": describe,
                "config": config,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        if describe_status == 404:
            return {
                "ok": False,
                "error": "RTSP_PATH_NOT_FOUND",
                "rtsp_status": status,
                "describe": describe,
                "config": config,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        if describe_status and describe_status >= 400:
            return {
                "ok": False,
                "error": f"DESCRIBE_STATUS_{describe_status}",
                "rtsp_status": status,
                "describe": describe,
                "config": config,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        cap = cv2.VideoCapture()
        previous_ffmpeg_options = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS")
        rtsp_transport = "udp" if str(config.get("transport") or "").lower() == "udp" else "tcp"
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            f"rtsp_transport;{rtsp_transport}|stimeout;2000000|max_delay;500000|fflags;nobuffer"
        )
        try:
            if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1500)
            if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 1500)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.open(url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                return {
                    "ok": False,
                    "error": "OPEN_FAILED",
                    "rtsp_status": status,
                    "describe": describe,
                    "config": config,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                }
            frame = None
            deadline = time.perf_counter() + 2.0
            while time.perf_counter() < deadline:
                ok, frame = cap.read()
                if ok and frame is not None:
                    height, width = frame.shape[:2]
                    return {
                        "ok": True,
                        "error": None,
                        "rtsp_status": status,
                        "describe": describe,
                        "config": config,
                        "frame": {"width": int(width), "height": int(height)},
                        "latency_ms": int((time.perf_counter() - started) * 1000),
                    }
                time.sleep(0.05)
            return {
                "ok": False,
                "error": "NO_FRAME",
                "rtsp_status": status,
                "describe": describe,
                "config": config,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "rtsp_status": status,
                "describe": describe,
                "config": config,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        finally:
            cap.release()
            if previous_ffmpeg_options is None:
                os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
            else:
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = previous_ffmpeg_options

    def _probe_rtsp_options(self, config: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        host = str(config["host"])
        port = int(config["rtsp_port"])
        path = f"/{config['transport']}/{config['stream']}"
        request = (
            f"OPTIONS rtsp://{host}:{port}{path} RTSP/1.0\r\n"
            "CSeq: 1\r\n"
            "User-Agent: 410health-camera-probe\r\n"
            "\r\n"
        ).encode("ascii", "ignore")
        try:
            with socket.create_connection((host, port), timeout=0.8) as sock:
                sock.settimeout(0.8)
                sock.sendall(request)
                data = sock.recv(1024)
        except OSError as exc:
            return {
                "reachable": False,
                "error": type(exc).__name__,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        text = data.decode("iso-8859-1", "ignore")
        status = None
        first = text.splitlines()[0] if text else ""
        parts = first.split()
        if len(parts) >= 2 and parts[0].startswith("RTSP/"):
            try:
                status = int(parts[1])
            except ValueError:
                status = None
        return {
            "reachable": bool(status),
            "status": status,
            "error": None if status else "INVALID_RTSP_RESPONSE",
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }

    def _probe_rtsp_describe(self, config: dict[str, Any]) -> dict[str, Any]:
        first = self._send_rtsp_request(config, method="DESCRIBE", accept_sdp=True)
        if first.get("status") != 401:
            return self._public_describe_result(first)
        authorization = self._build_rtsp_authorization(
            config,
            str(first.get("www_authenticate") or ""),
            method="DESCRIBE",
        )
        if not authorization:
            return self._public_describe_result(first)
        second = self._send_rtsp_request(
            config,
            method="DESCRIBE",
            accept_sdp=True,
            authorization=authorization,
        )
        return self._public_describe_result(second)

    def _send_rtsp_request(
        self,
        config: dict[str, Any],
        *,
        method: str,
        accept_sdp: bool = False,
        authorization: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        host = str(config["host"])
        port = int(config["rtsp_port"])
        path = f"/{config['transport']}/{config['stream']}"
        uri = f"rtsp://{host}:{port}{path}"
        lines = [
            f"{method} {uri} RTSP/1.0",
            "CSeq: 2",
            "User-Agent: 410health-camera-probe",
        ]
        if accept_sdp:
            lines.append("Accept: application/sdp")
        if authorization:
            lines.append(f"Authorization: {authorization}")
        request = ("\r\n".join(lines) + "\r\n\r\n").encode("ascii", "ignore")
        try:
            with socket.create_connection((host, port), timeout=0.9) as sock:
                sock.settimeout(0.9)
                sock.sendall(request)
                chunks: list[bytes] = []
                while True:
                    try:
                        chunk = sock.recv(4096)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if sum(len(item) for item in chunks) > 16384:
                        break
        except OSError as exc:
            return {
                "status": None,
                "error": type(exc).__name__,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        raw = b"".join(chunks).decode("iso-8859-1", "ignore")
        header_text, _, body = raw.partition("\r\n\r\n")
        headers = self._parse_rtsp_headers(header_text)
        status = None
        first_line = header_text.splitlines()[0] if header_text else ""
        parts = first_line.split()
        if len(parts) >= 2 and parts[0].startswith("RTSP/"):
            try:
                status = int(parts[1])
            except ValueError:
                status = None
        return {
            "status": status,
            "headers": headers,
            "www_authenticate": headers.get("www-authenticate"),
            "body": body,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }

    def _parse_rtsp_headers(self, header_text: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        for line in header_text.splitlines()[1:]:
            name, sep, value = line.partition(":")
            if sep:
                headers[name.strip().lower()] = value.strip()
        return headers

    def _build_rtsp_authorization(self, config: dict[str, Any], challenge: str, *, method: str) -> str | None:
        username = str(config.get("username") or "")
        password = str(config.get("password") or "")
        host = str(config["host"])
        port = int(config["rtsp_port"])
        uri = f"rtsp://{host}:{port}/{config['transport']}/{config['stream']}"
        if not username:
            return None
        if challenge.lower().startswith("basic"):
            import base64

            token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            return f"Basic {token}"
        if not challenge.lower().startswith("digest"):
            return None
        realm = self._auth_param(challenge, "realm")
        nonce = self._auth_param(challenge, "nonce")
        qop = self._auth_param(challenge, "qop")
        if not realm or not nonce:
            return None
        nc = "00000001"
        cnonce = "410health"
        ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode("utf-8")).hexdigest()
        ha2 = hashlib.md5(f"{method}:{uri}".encode("utf-8")).hexdigest()
        if qop and "auth" in qop:
            response = hashlib.md5(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}".encode("utf-8")).hexdigest()
            return (
                f'Digest username="{username}", realm="{realm}", nonce="{nonce}", uri="{uri}", '
                f'response="{response}", qop=auth, nc={nc}, cnonce="{cnonce}"'
            )
        response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode("utf-8")).hexdigest()
        return (
            f'Digest username="{username}", realm="{realm}", nonce="{nonce}", uri="{uri}", '
            f'response="{response}"'
        )

    def _auth_param(self, challenge: str, name: str) -> str | None:
        match = re.search(rf'{re.escape(name)}="?([^",]+)"?', challenge, flags=re.IGNORECASE)
        return match.group(1) if match else None

    def _public_describe_result(self, raw: dict[str, Any]) -> dict[str, Any]:
        body = str(raw.get("body") or "")
        headers = raw.get("headers") if isinstance(raw.get("headers"), dict) else {}
        auth = str(raw.get("www_authenticate") or "")
        auth_scheme = auth.split(" ", 1)[0] if auth else None
        codecs = []
        for line in body.splitlines():
            if line.startswith("a=rtpmap:"):
                codecs.append(line.split(None, 1)[-1])
        return {
            "status": raw.get("status"),
            "auth_scheme": auth_scheme,
            "content_type": headers.get("content-type"),
            "content_base": headers.get("content-base"),
            "sdp": bool(body.strip()),
            "codecs": codecs[:4],
            "latency_ms": raw.get("latency_ms"),
            "error": raw.get("error"),
        }

    def _rtsp_url(self, config: dict[str, Any]) -> str:
        username = quote(str(config["username"]), safe="")
        password = quote(str(config.get("password") or ""), safe="")
        return (
            f"rtsp://{username}:{password}"
            f"@{config['host']}:{config['rtsp_port']}/{config['transport']}/{config['stream']}"
        )

    def _public_probe_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "host": config.get("host"),
            "username": config.get("username"),
            "rtsp_port": config.get("rtsp_port"),
            "transport": config.get("transport"),
            "stream": config.get("stream"),
            "password_set": bool(config.get("password")),
            "reason": config.get("reason"),
            "source": (
                f"rtsp://{config.get('username') or 'admin'}:***"
                f"@{config.get('host')}:{config.get('rtsp_port')}"
                f"/{config.get('transport')}/{config.get('stream')}"
            ),
        }

    def _snapshot_meta_from_headers(self, headers: requests.structures.CaseInsensitiveDict[str]) -> dict[str, Any]:
        age_ms = self._parse_int(headers.get("X-Camera-Frame-Age-Ms"))
        frame_count = self._parse_int(headers.get("X-Camera-Frame-Count"))
        stale_header = str(headers.get("X-Camera-Frame-Stale") or "0").strip().lower()
        age_seconds = None if age_ms is None else age_ms / 1000.0
        return {
            "frame_age_ms": age_ms,
            "frame_age_seconds": age_seconds,
            "frame_count": frame_count,
            "stale": stale_header in {"1", "true", "yes"} or (
                age_seconds is not None and age_seconds > self._max_snapshot_age_seconds
            ),
        }

    def _parse_int(self, value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return None

    def _camera_failure_response(
        self,
        *,
        status: str,
        reason: str,
        message: str,
        started: float,
        camera_health: dict[str, Any],
        session_id: str,
        snapshot_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        diagnostics = {
            "is_failure": True,
            "reasons": [reason],
            "warnings": [message],
            "candidate_count": 0,
            "track_id": None,
            "used_track": False,
            "used_roi": False,
            "match_decision": "camera_unavailable",
            "face_score": 0.0,
            "body_score": 0.0,
            "fused_score": 0.0,
            "fall_status": None,
            "camera_health": camera_health,
            "camera_frame": snapshot_meta or {},
        }
        return {
            "ok": False,
            "status": status,
            "error": message,
            "target_match": None,
            "fall_result": None,
            "pose_result": None,
            "posture_event": None,
            "posture_guidance": None,
            "warnings": [message],
            "tracking": {
                "session_id": session_id,
                "track_id": None,
                "used_track": False,
                "candidate_count": 0,
                "roi": {"used_roi": False},
            },
            "diagnostics": diagnostics,
            "camera_source": self._camera_source(),
            "camera_health": camera_health,
            "camera_frame": snapshot_meta or {},
            "bridge_latency_ms": int((time.perf_counter() - started) * 1000),
            "snapshot_bytes": 0,
        }

    def _build_diagnostics(
        self,
        result: dict[str, Any],
        *,
        camera_health: dict[str, Any] | None = None,
        snapshot_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        warnings = [str(item) for item in (result.get("warnings") or [])]
        tracking = result.get("tracking") or {}
        target_match = result.get("target_match") or {}
        fall_result = result.get("fall_result") or {}
        reasons: list[str] = []
        if "FACE_NOT_FOUND" in warnings:
            reasons.append("FACE_NOT_FOUND")
        if "BODY_NOT_FOUND" in warnings:
            reasons.append("BODY_NOT_FOUND")
        if not tracking.get("used_track"):
            reasons.append("NO_TRACK_CANDIDATE")
        if target_match.get("decision") in {"unknown", "non_target"}:
            reasons.append("LOW_MATCH_CONFIDENCE")
        if not reasons and result.get("status") == "filtered_non_target":
            reasons.append("FILTERED_NON_TARGET")
        return {
            "is_failure": result.get("status") == "filtered_non_target" or bool(warnings),
            "reasons": reasons,
            "warnings": warnings,
            "candidate_count": int(tracking.get("candidate_count") or 0),
            "track_id": tracking.get("track_id"),
            "used_track": bool(tracking.get("used_track")),
            "used_roi": bool((tracking.get("roi") or {}).get("used_roi")),
            "match_decision": target_match.get("decision", "unknown"),
            "face_score": float(target_match.get("face_score") or 0.0),
            "body_score": float(target_match.get("body_score") or 0.0),
            "fused_score": float(target_match.get("fused_score") or 0.0),
            "fall_status": fall_result.get("status"),
            "camera_health": camera_health or {},
            "camera_frame": snapshot_meta or {},
        }

    def _store_failure_frame(self, *, image_bytes: bytes, session_id: str, diagnostics: dict[str, Any]) -> None:
        session_dir = self._debug_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time() * 1000)
        image_path = session_dir / f"{stamp}.jpg"
        meta_path = session_dir / f"{stamp}.json"
        image_path.write_bytes(image_bytes)
        meta_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")

        images = sorted(session_dir.glob("*.jpg"))
        metas = sorted(session_dir.glob("*.json"))
        while len(images) > self._max_debug_frames:
            oldest = images.pop(0)
            oldest.unlink(missing_ok=True)
        while len(metas) > self._max_debug_frames:
            oldest = metas.pop(0)
            oldest.unlink(missing_ok=True)
