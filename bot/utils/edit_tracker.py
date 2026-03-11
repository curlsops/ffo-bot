import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

EDIT_TRACK_TTL_SECONDS = 3600


@dataclass
class TrackedResponse:
    response_msg_id: int
    channel_id: int
    invoked_at: datetime


class EditTracker:
    def __init__(self, ttl_seconds: float = EDIT_TRACK_TTL_SECONDS):
        self._map: dict[int, dict[int, TrackedResponse]] = defaultdict(dict)
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    def track(self, user_msg_id: int, channel_id: int, response_msg_id: int) -> None:
        self._map[channel_id][user_msg_id] = TrackedResponse(
            response_msg_id=response_msg_id,
            channel_id=channel_id,
            invoked_at=datetime.now(UTC),
        )

    def get(self, user_msg_id: int, channel_id: int) -> TrackedResponse | None:
        channel_map = self._map.get(channel_id, {})
        entry = channel_map.get(user_msg_id)
        if not entry:
            return None
        if (datetime.now(UTC) - entry.invoked_at).total_seconds() > self._ttl:
            del channel_map[user_msg_id]
            return None
        return entry

    def untrack(self, user_msg_id: int, channel_id: int) -> None:
        if channel_id in self._map and user_msg_id in self._map[channel_id]:
            del self._map[channel_id][user_msg_id]
