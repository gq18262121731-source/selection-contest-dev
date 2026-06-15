from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


REQUIRED_SHOUHUAN_CONSTANTS = {
    "TARGET_COM": str,
    "BAUD_RATE": int,
    "HANDWARE_MAC": str,
}
DEFAULT_SERIAL_DETECTION_KEYWORDS = (
    "cp210",
    "usb serial",
    "nrf",
    "silicon labs",
    "ch9102",
    "wch",
    "usb-enhanced-serial",
)


@dataclass(frozen=True)
class ShouhuanConfig:
    port: str
    baudrate: int
    mac_address: str
    packet_type: int = 5
    script_path: str = ""


@dataclass(frozen=True)
class RuntimeBootstrap:
    mode: str
    bootstrap_source: str
    bootstrap_status: str
    bootstrap_reason: str
    port: str = ""
    baudrate: int = 115200
    mac_address: str = ""
    packet_type: int = 5


def parse_shouhuan_config(script_path: str | Path) -> ShouhuanConfig:
    path = Path(script_path)
    source = _read_script_source(path)
    syntax_tree = ast.parse(source, filename=str(path))
    values: dict[str, object] = {}

    for node in syntax_tree.body:
        if not isinstance(node, ast.Assign):
            continue
        constant_value = _extract_constant(node.value)
        if constant_value is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in REQUIRED_SHOUHUAN_CONSTANTS:
                values[target.id] = constant_value

    missing = [name for name in REQUIRED_SHOUHUAN_CONSTANTS if name not in values]
    if missing:
        missing_constants = ", ".join(missing)
        raise ValueError(f"Missing shouhuan.py constants: {missing_constants}")

    port = str(values["TARGET_COM"]).strip()
    baudrate = int(values["BAUD_RATE"])
    mac_address = _normalize_mac(str(values["HANDWARE_MAC"]))
    if not port:
        raise ValueError("TARGET_COM is empty")

    return ShouhuanConfig(
        port=port,
        baudrate=baudrate,
        mac_address=mac_address,
        script_path=str(path),
    )


def resolve_runtime_bootstrap(script_path: str | Path) -> RuntimeBootstrap:
    path = Path(script_path)
    if not path.exists():
        return RuntimeBootstrap(
            mode="mock",
            bootstrap_source="fallback_mock",
            bootstrap_status="fallback",
            bootstrap_reason="shouhuan_missing",
        )

    try:
        config = parse_shouhuan_config(path)
    except Exception as exc:
        return RuntimeBootstrap(
            mode="mock",
            bootstrap_source="fallback_mock",
            bootstrap_status="fallback",
            bootstrap_reason=f"shouhuan_parse_failed:{type(exc).__name__}",
        )

    detected_port, reason = auto_detect_serial_port(config.port, config.baudrate)
    if detected_port:
        return RuntimeBootstrap(
            mode="serial",
            bootstrap_source="shouhuan.py",
            bootstrap_status="ready",
            bootstrap_reason=reason,
            port=detected_port,
            baudrate=config.baudrate,
            mac_address=config.mac_address,
            packet_type=config.packet_type,
        )

    if reason == "pyserial_missing":
        return RuntimeBootstrap(
            mode="mock",
            bootstrap_source="fallback_mock",
            bootstrap_status="fallback",
            bootstrap_reason=reason,
            port=config.port,
            baudrate=config.baudrate,
            mac_address=config.mac_address,
            packet_type=config.packet_type,
        )

    return RuntimeBootstrap(
        mode="serial",
        bootstrap_source="shouhuan.py",
        bootstrap_status="waiting",
        bootstrap_reason=reason,
        port=config.port,
        baudrate=config.baudrate,
        mac_address=config.mac_address,
        packet_type=config.packet_type,
    )


def probe_serial_port(port: str, baudrate: int) -> tuple[bool, str]:
    try:
        import serial  # type: ignore
    except ImportError:
        return False, "pyserial_missing"

    try:
        with serial.Serial(port=port, baudrate=baudrate, timeout=1):
            return True, "serial_port_available"
    except Exception as exc:
        return False, f"serial_open_failed:{type(exc).__name__}"


def auto_detect_serial_port(preferred_port: str, baudrate: int) -> tuple[str | None, str]:
    try:
        from serial.tools import list_ports  # type: ignore
    except ImportError:
        return None, "pyserial_missing"

    ports = list(list_ports.comports())
    normalized_preferred = preferred_port.strip().upper()
    preferred_failure_reason: str | None = None

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
            preferred_device = str(getattr(preferred_match, "device", "")).strip()
            preferred_ready, preferred_reason = probe_serial_port(preferred_device, baudrate)
            if preferred_ready:
                return preferred_device, "serial_port_available"
            preferred_failure_reason = preferred_reason
        else:
            preferred_failure_reason = "serial_port_not_present"

    candidate_ports = [
        port
        for port in ports
        if _port_matches_keywords(port, DEFAULT_SERIAL_DETECTION_KEYWORDS)
    ] or ports

    last_failure_reason: str | None = preferred_failure_reason
    for port in candidate_ports:
        device = str(getattr(port, "device", "")).strip()
        if not device or device.upper() == normalized_preferred:
            continue
        port_ready, reason = probe_serial_port(device, baudrate)
        if port_ready:
            return device, f"serial_port_auto_detected:{device}"
        last_failure_reason = reason

    if last_failure_reason:
        return None, last_failure_reason
    if not ports:
        return None, "serial_port_not_detected"
    return None, "serial_port_unavailable"


def _extract_constant(node: ast.AST) -> object | None:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        if isinstance(node.operand.value, (int, float)):
            return -node.operand.value
    return None


def _normalize_mac(value: str) -> str:
    compact = "".join(character for character in value if character.isalnum()).upper()
    if len(compact) != 12 or any(character not in "0123456789ABCDEF" for character in compact):
        raise ValueError("HANDWARE_MAC must be a 12-digit hexadecimal MAC address")
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


def _read_script_source(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _port_matches_keywords(port: object, keywords: tuple[str, ...]) -> bool:
    haystack = " ".join(
        [
            str(getattr(port, "device", "")),
            str(getattr(port, "description", "")),
            str(getattr(port, "manufacturer", "")),
            str(getattr(port, "hwid", "")),
        ]
    ).lower()
    return any(keyword in haystack for keyword in keywords)
