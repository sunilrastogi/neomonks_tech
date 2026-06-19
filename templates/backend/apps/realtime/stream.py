from __future__ import annotations

import json
from collections.abc import Iterator

from .services import RealtimeService


def stream_events(since_id: int = 0) -> Iterator[str]:
    """Yield SSE-formatted frames from WorkflowEvent rows.

    Runs until the client disconnects (Django will close the generator).
    `since_id` lets clients reconnect and resume from their last-seen event.
    """
    service = RealtimeService()
    yield "event: ready\ndata: {}\n\n"

    for event_type, data in service.stream(since_id=since_id):
        yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
