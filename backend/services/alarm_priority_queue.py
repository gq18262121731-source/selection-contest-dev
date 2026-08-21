from __future__ import annotations

from datetime import timezone

from backend.models.alarm_model import AlarmQueueItem, AlarmRecord

try:
    from redis import Redis
except ImportError:
    Redis = None


class AlarmPriorityQueue:
    """Redis Sorted Set semantics with an in-memory fallback."""

    def __init__(self, redis_url: str, queue_key: str = "alarm:priority") -> None:
        self._queue_key = queue_key
        self._memory: dict[str, tuple[float, AlarmRecord]] = {}
        self._redis = (
            Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
            if Redis
            else None
        )

    def enqueue(self, alarm: AlarmRecord) -> None:
        score = self._score_for(alarm)
        self._memory[alarm.id] = (score, alarm)
        if self._redis:
            try:
                self._redis.zadd(self._queue_key, {alarm.model_dump_json(): score})
            except Exception:
                # Fall back to the in-memory queue after the first Redis failure
                # so alarm ingestion never stalls on repeated reconnect attempts.
                self._redis = None

    def remove(self, alarm_id: str) -> None:
        cached = self._memory.pop(alarm_id, None)
        if self._redis and cached:
            _, alarm = cached
            try:
                self._redis.zrem(self._queue_key, alarm.model_dump_json())
            except Exception:
                self._redis = None

    def items(self, active_only: bool = True) -> list[AlarmQueueItem]:
        alarms = [item for item in self._memory.values() if not active_only or not item[1].acknowledged]
        alarms.sort(key=lambda item: (item[0], item[1].created_at))
        return [AlarmQueueItem(score=score, alarm=alarm) for score, alarm in alarms]

    def snapshot(self) -> dict[str, object]:
        backend = "redis" if self._redis else "memory"
        return {
            "queue_key": self._queue_key,
            "backend": backend,
            "length": len(self.items(active_only=False)),
            "head": [item.alarm.id for item in self.items(active_only=True)[:5]],
        }

    @staticmethod
    def _score_for(alarm: AlarmRecord) -> float:
        created_ts = alarm.created_at.astimezone(timezone.utc).timestamp()
        return float(alarm.alarm_level.value) * 1_000_000_000 + created_ts
