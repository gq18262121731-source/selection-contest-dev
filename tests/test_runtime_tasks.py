from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import backend.main as backend_main


def test_lifespan_in_serial_mode_starts_serial_and_demo_overlay_without_mock_stream(monkeypatch, tmp_path: Path) -> None:
    started: list[str] = []

    async def fake_mock_stream_loop() -> None:
        started.append("mock")
        await asyncio.Event().wait()

    async def fake_demo_overlay_stream_loop() -> None:
        started.append("demo_overlay")
        await asyncio.Event().wait()

    async def fake_serial_stream_loop() -> None:
        started.append("serial")
        await asyncio.Event().wait()

    monkeypatch.setattr(
        backend_main,
        "settings",
        SimpleNamespace(
            data_dir=tmp_path,
            mock_runtime_enabled=False,
            enable_mock_overlay=True,
            serial_runtime_enabled=True,
            data_mode="serial",
            mqtt_enabled=False,
        ),
    )
    monkeypatch.setattr(backend_main, "_mock_stream_loop", fake_mock_stream_loop)
    monkeypatch.setattr(backend_main, "_demo_overlay_stream_loop", fake_demo_overlay_stream_loop)
    monkeypatch.setattr(backend_main, "_serial_stream_loop", fake_serial_stream_loop)

    async def exercise_lifespan() -> None:
        async with backend_main.lifespan(backend_main.app):
            await asyncio.sleep(0)

    asyncio.run(exercise_lifespan())

    assert "mock" not in started
    assert set(started) == {"demo_overlay", "serial"}
