from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable

from backend.models.health_model import HealthSample, IngestionSource
from iot.parser import T10PacketParser

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None


MAC_PATTERN = re.compile(r"(?i)\b((?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}|53(?:57|:57)(?:08|:08)[0-9a-f:-]{6,})\b")
BROADCAST_MARKER = "0201061AFF4C000215"
RESPONSE_A_MARKER = "161803"
RESPONSE_B_MARKER = "160318"
logger = logging.getLogger(__name__)


class SerialGatewayReader:
    """Serial adapter for the nRF52832 collector used by the T10 wristband."""

    def __init__(self, parser: T10PacketParser) -> None:
        self._parser = parser

    def list_candidate_ports(self, keywords: list[str] | None = None) -> list[object]:
        if list_ports is None:
            raise RuntimeError("pyserial is not installed; serial collection is unavailable.")
        normalized_keywords = [keyword.lower() for keyword in (keywords or [])]
        ports = list(list_ports.comports())
        if not normalized_keywords:
            return ports
        return [
            port
            for port in ports
            if self._port_matches_keywords(port, normalized_keywords)
        ]

    def detect_port(self, preferred_port: str | None = None, keywords: list[str] | None = None) -> str:
        normalized_preferred = (preferred_port or "").strip().upper()
        ports = self.list_candidate_ports(None)
        if normalized_preferred:
            preferred_match = next(
                (
                    port
                    for port in ports
                    if str(getattr(port, "device", "")).strip().upper() == normalized_preferred
                ),
                None,
            )
            if preferred_match is not None:
                return str(preferred_match.device)
            logger.warning(
                "Preferred serial collector port %s is unavailable; falling back to auto-detection.",
                preferred_port,
            )

        candidates = self.list_candidate_ports(keywords)
        if not candidates:
            raise RuntimeError("No compatible collector serial port was detected.")
        return str(candidates[0].device)

    def initialize_collector(
        self,
        connection,
        *,
        mac_filter: str,
        packet_type: int,
        disable_uuid_output: bool = True,
        apply_mac_filter: bool = False,
        apply_packet_type: bool = False,
        command_delay_seconds: float = 0.02,
    ) -> None:
        commands = ["AT+SCANSTOP"]
        if disable_uuid_output:
            commands.append("AT+UUID=NO")
        if apply_mac_filter:
            commands.append(f"AT+MAC={mac_filter}")
        if apply_packet_type:
            commands.append(f"AT+TYPE={packet_type}")
        commands.append("AT+SCANSTART")
        self._run_commands(connection, commands, command_delay_seconds=command_delay_seconds)

    def configure_single_target(
        self,
        connection,
        *,
        target_mac: str,
        packet_type: int = 5,
        command_delay_seconds: float = 0.02,
    ) -> None:
        compact_mac = self._compact_mac(target_mac)
        commands = [
            "AT+SCANSTOP",
            f"AT+MAC={compact_mac}",
            f"AT+TYPE={packet_type}",
            "AT+SCANSTART",
        ]
        self._run_commands(connection, commands, command_delay_seconds=command_delay_seconds)

    def stop_scan(
        self,
        connection,
        *,
        command_delay_seconds: float = 0.02,
    ) -> None:
        self._run_commands(connection, ["AT+SCANSTOP"], command_delay_seconds=command_delay_seconds)

    def switch_packet_type(
        self,
        connection,
        *,
        packet_type: int,
        command_delay_seconds: float = 0.02,
    ) -> None:
        commands = ["AT+SCANSTOP", f"AT+TYPE={packet_type}", "AT+SCANSTART"]
        self._run_commands(connection, commands, command_delay_seconds=command_delay_seconds)

    def run(
        self,
        *,
        port: str | None = None,
        baudrate: int = 115200,
        collection_strategy: str = "single_target",
        packet_type: int = 5,
        mac_filter: str = "535708000000",
        detection_keywords: list[str] | None = None,
        fallback_device_mac: str | None = None,
        auto_configure: bool = True,
        disable_uuid_output: bool = True,
        apply_mac_filter: bool = False,
        apply_packet_type: bool = False,
        enable_broadcast_sos_overlay: bool = False,
        response_cycle_seconds: float = 2.0,
        broadcast_cycle_seconds: float = 0.5,
        command_delay_seconds: float = 0.12,
        reconnect_delay_seconds: float = 1.0,
        target_mac_provider: Callable[[], str | None] | None = None,
        on_sample: Callable[[HealthSample], None] | None = None,
    ) -> None:
        if serial is None:
            raise RuntimeError("pyserial is not installed; serial collection is unavailable.")

        current_port: str | None = None
        while True:
            selected_port: str | None = None
            try:
                selected_port = self.detect_port(current_port or port, detection_keywords)
                if selected_port != current_port:
                    logger.info("Serial collector connected on %s", selected_port)
                current_port = selected_port
                with serial.Serial(port=selected_port, baudrate=baudrate, timeout=1) as connection:
                    self._stream_connection(
                        connection,
                        collection_strategy=collection_strategy,
                        packet_type=packet_type,
                        mac_filter=mac_filter,
                        fallback_device_mac=fallback_device_mac,
                        auto_configure=auto_configure,
                        disable_uuid_output=disable_uuid_output,
                        apply_mac_filter=apply_mac_filter,
                        apply_packet_type=apply_packet_type,
                        enable_broadcast_sos_overlay=enable_broadcast_sos_overlay,
                        response_cycle_seconds=response_cycle_seconds,
                        broadcast_cycle_seconds=broadcast_cycle_seconds,
                        command_delay_seconds=command_delay_seconds,
                        target_mac_provider=target_mac_provider,
                        on_sample=on_sample,
                    )
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                retry_target = selected_port or current_port or port or "auto-detect"
                logger.warning(
                    "Serial collector unavailable on %s, retrying detection in %.1fs: %s",
                    retry_target,
                    reconnect_delay_seconds,
                    exc,
                )
                current_port = None
                time.sleep(reconnect_delay_seconds)

    def _stream_connection(
        self,
        connection,
        *,
        collection_strategy: str,
        packet_type: int,
        mac_filter: str,
        fallback_device_mac: str | None,
        auto_configure: bool,
        disable_uuid_output: bool,
        apply_mac_filter: bool,
        apply_packet_type: bool,
        enable_broadcast_sos_overlay: bool,
        response_cycle_seconds: float,
        broadcast_cycle_seconds: float,
        command_delay_seconds: float,
        target_mac_provider: Callable[[], str | None] | None,
        on_sample: Callable[[HealthSample], None] | None,
    ) -> None:
        active_packet_type = packet_type
        active_target_mac: str | None = None
        cycle_started_at = time.monotonic()

        if collection_strategy != "single_target" and auto_configure:
            self.initialize_collector(
                connection,
                mac_filter=mac_filter,
                packet_type=packet_type,
                disable_uuid_output=disable_uuid_output,
                apply_mac_filter=apply_mac_filter,
                apply_packet_type=apply_packet_type,
                command_delay_seconds=command_delay_seconds,
            )

        while True:
            if collection_strategy == "single_target":
                desired_target_mac = self._normalize_mac(target_mac_provider() if target_mac_provider else mac_filter)
                desired_packet_type = packet_type
                if enable_broadcast_sos_overlay:
                    elapsed = time.monotonic() - cycle_started_at
                    if active_packet_type == 5 and elapsed >= response_cycle_seconds:
                        desired_packet_type = 4
                    elif active_packet_type == 4 and elapsed >= broadcast_cycle_seconds:
                        desired_packet_type = 5
                    else:
                        desired_packet_type = active_packet_type

                if desired_target_mac != active_target_mac or desired_packet_type != active_packet_type:
                    if desired_target_mac:
                        self.configure_single_target(
                            connection,
                            target_mac=desired_target_mac,
                            packet_type=desired_packet_type,
                            command_delay_seconds=command_delay_seconds,
                        )
                        active_target_mac = desired_target_mac
                        active_packet_type = desired_packet_type
                        cycle_started_at = time.monotonic()
                    else:
                        if active_target_mac:
                            self.stop_scan(connection, command_delay_seconds=command_delay_seconds)
                        active_target_mac = None
                        active_packet_type = packet_type

                if not active_target_mac:
                    time.sleep(0.2)
                    continue

            if collection_strategy != "single_target" and enable_broadcast_sos_overlay:
                elapsed = time.monotonic() - cycle_started_at
                target_packet_type = 5
                if active_packet_type == 5 and elapsed >= response_cycle_seconds:
                    target_packet_type = 4
                elif active_packet_type == 4 and elapsed >= broadcast_cycle_seconds:
                    target_packet_type = 5

                if target_packet_type != active_packet_type:
                    self.switch_packet_type(
                        connection,
                        packet_type=target_packet_type,
                        command_delay_seconds=command_delay_seconds,
                    )
                    active_packet_type = target_packet_type
                    cycle_started_at = time.monotonic()

            line = connection.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            payload, line_mac = self._extract_payload_and_mac(line)
            if not payload:
                continue
            normalized_line_mac = self._normalize_mac(line_mac)
            if (
                collection_strategy == "single_target"
                and active_target_mac
                and normalized_line_mac
                and normalized_line_mac != active_target_mac
            ):
                logger.debug(
                    "Dropping serial payload for off-target MAC %s while tracking %s",
                    normalized_line_mac,
                    active_target_mac,
                )
                continue

            sample = self._parser.feed(
                normalized_line_mac or fallback_device_mac or active_target_mac,
                payload,
                source=IngestionSource.SERIAL,
            )
            if sample and on_sample:
                on_sample(sample)

    def _run_commands(
        self,
        connection,
        commands: list[str],
        *,
        command_delay_seconds: float,
    ) -> None:
        for command in commands:
            connection.write(f"{command}\r\n".encode("utf-8"))
            connection.flush()
            time.sleep(command_delay_seconds)
            self._drain_feedback(connection)

    @staticmethod
    def _drain_feedback(connection) -> None:
        started = time.time()
        while time.time() - started < 0.05:
            waiting = getattr(connection, "in_waiting", 0)
            if not waiting:
                break
            connection.readline()

    @staticmethod
    def _extract_payload_and_mac(line: str) -> tuple[str | None, str | None]:
        upper_line = line.upper()
        if upper_line.startswith("AT+") or upper_line in {"OK", "ERROR"}:
            return None, None

        compact = re.sub(r"[^0-9A-Fa-f]", "", line).upper()
        if len(compact) < 12:
            return None, None

        mac = None
        mac_match = MAC_PATTERN.search(line)
        if mac_match:
            compact_mac = re.sub(r"[^0-9A-Fa-f]", "", mac_match.group(1)).upper()
            if len(compact_mac) == 12:
                mac = SerialGatewayReader._format_mac(compact_mac)

        collector_payload, collector_mac = SerialGatewayReader._extract_prefixed_payload(compact)
        payload = collector_payload or SerialGatewayReader._extract_embedded_payload(compact)
        if not payload or len(payload) % 2 != 0:
            return None, mac
        return payload, (mac or collector_mac)

    @staticmethod
    def _extract_prefixed_payload(compact: str) -> tuple[str | None, str | None]:
        # Try finding known packet markers first.
        # Only infer MAC from the leading 12 hex chars when the marker starts
        # exactly at offset 12 (strict "<MAC><PAYLOAD>" shape).
        for marker in [BROADCAST_MARKER, RESPONSE_A_MARKER, RESPONSE_B_MARKER]:
            idx = compact.find(marker)
            if idx == 12:
                mac_candidate = compact[:12]
                payload_candidate = compact[idx:]
                return payload_candidate, SerialGatewayReader._format_mac(mac_candidate)
            if idx >= 0:
                return compact[idx:], None

        # Fallback to fixed offsets if no marker but long enough (e.g. raw dump)
        if len(compact) >= 12:
            return compact, None

        return None, None

    @staticmethod
    def _extract_embedded_payload(compact: str) -> str | None:
        broadcast_index = compact.find(BROADCAST_MARKER)
        if broadcast_index != -1:
            return compact[broadcast_index:]

        response_a_index = compact.find(RESPONSE_A_MARKER)
        if response_a_index != -1:
            return compact[response_a_index:]

        response_b_index = compact.find(RESPONSE_B_MARKER)
        if response_b_index != -1:
            return compact[response_b_index:]

        if re.fullmatch(r"[0-9A-F]+", compact):
            return compact
        return None

    @staticmethod
    def _format_mac(compact_mac: str) -> str:
        return ":".join(compact_mac[index : index + 2] for index in range(0, 12, 2))

    @staticmethod
    def _compact_mac(mac_address: str) -> str:
        return re.sub(r"[^0-9A-Fa-f]", "", mac_address).upper()

    @staticmethod
    def _normalize_mac(mac_address: str | None) -> str | None:
        if not mac_address:
            return None
        compact = SerialGatewayReader._compact_mac(mac_address)
        if len(compact) != 12:
            return None
        return SerialGatewayReader._format_mac(compact)

    @staticmethod
    def _port_matches_keywords(port: object, keywords: list[str]) -> bool:
        haystack = " ".join(
            [
                str(getattr(port, "device", "")),
                str(getattr(port, "description", "")),
                str(getattr(port, "manufacturer", "")),
                str(getattr(port, "hwid", "")),
            ]
        ).lower()
        return any(keyword in haystack for keyword in keywords)
