from __future__ import annotations

import os
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class SerialRuntimeLockError(RuntimeError):
    """Raised when another process already owns the serial runtime lock."""


class SerialRuntimeLock:
    """Cross-process lock that keeps only one serial runtime active per machine."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._handle = None

    def _lock_file(self, handle) -> None:
        if os.name == "nt":
            handle.seek(0)
            handle.write(" ")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_file(self, handle) -> None:
        if os.name == "nt":
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def acquire(self) -> "SerialRuntimeLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+", encoding="utf-8")
        try:
            self._lock_file(handle)
        except OSError as exc:
            handle.close()
            raise SerialRuntimeLockError(
                f"serial runtime lock is already held: {self._path}"
            ) from exc

        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        self._handle = handle
        return self

    def release(self) -> None:
        if self._handle is None:
            return
        handle = self._handle
        self._handle = None
        try:
            self._unlock_file(handle)
        finally:
            handle.close()

    def __enter__(self) -> "SerialRuntimeLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.release()
        return False
