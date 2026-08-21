from __future__ import annotations

from collections.abc import Awaitable, Callable

from backend.models.health_model import HealthSample, IngestionSource
from iot.parser import T10PacketParser

try:
    from bleak import BleakScanner
except ImportError:
    BleakScanner = None


class BleScannerService:
    """BLE development adapter using bleak. Intended for direct debugging and demos."""

    def __init__(self, parser: T10PacketParser, allowed_prefixes: list[str]) -> None:
        self._parser = parser
        self._allowed_prefixes = [prefix.upper() for prefix in allowed_prefixes]

    async def scan_forever(self, on_sample: Callable[[HealthSample], Awaitable[None]]) -> None:
        if BleakScanner is None:
            raise RuntimeError("bleak 未安装，无法启用直接 BLE 调试模式。")

        async def handle_detection(device, advertisement_data):
            address = device.address.upper()
            if not any(address.startswith(prefix) for prefix in self._allowed_prefixes):
                return
            for payload in advertisement_data.manufacturer_data.values():
                sample = self._parser.feed(address, payload, source=IngestionSource.BLE)
                if sample:
                    await on_sample(sample)

        scanner = BleakScanner(detection_callback=handle_detection)
        await scanner.start()
