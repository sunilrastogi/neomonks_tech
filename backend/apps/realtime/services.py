from __future__ import annotations

import time
from typing import Any, Iterator


class RealtimeService:
    """Database-backed realtime service.

    Polls WorkflowEvent in chronological order starting from `since_id`.
    Returns only new rows each call so the SSE stream can checkpoint.
    """

    POLL_INTERVAL = 2.0  # seconds between DB polls
    HEARTBEAT_INTERVAL = 15.0  # seconds between SSE keep-alive pings

    def poll_new_events(self, since_id: int = 0) -> tuple[list[dict[str, Any]], int]:
        """Return events with id > since_id and the new high-water mark."""
        from django.db import OperationalError
        from apps.workflow.models import WorkflowEvent

        try:
            qs = (
                WorkflowEvent.objects.filter(id__gt=since_id)
                .order_by("id")
                .values("id", "event_type", "entity_type", "entity_id", "payload_json", "created_at")
            )
            events = list(qs)
        except OperationalError:
            # Table not yet created — migrations haven't been run yet.
            return [], since_id
        if not events:
            return [], since_id
        new_cursor = events[-1]["id"]
        serialized = [
            {
                "id": e["id"],
                "event_type": e["event_type"],
                "entity_type": e["entity_type"],
                "entity_id": e["entity_id"],
                "payload": e["payload_json"],
                "ts": e["created_at"].isoformat(),
            }
            for e in events
        ]
        return serialized, new_cursor

    def stream(self, since_id: int = 0) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield (event_type, data) tuples indefinitely."""
        cursor = since_id
        last_heartbeat = time.monotonic()

        while True:
            events, cursor = self.poll_new_events(cursor)
            for ev in events:
                yield ev["event_type"], ev

            now = time.monotonic()
            if now - last_heartbeat >= self.HEARTBEAT_INTERVAL:
                yield "heartbeat", {"ts": time.time()}
                last_heartbeat = now

            if not events:
                time.sleep(self.POLL_INTERVAL)
