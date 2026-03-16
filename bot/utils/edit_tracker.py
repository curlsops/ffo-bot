import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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
        self._prune_interval_seconds = max(60.0, min(ttl_seconds, 300.0))
        self._next_prune_at = datetime.now(UTC) + timedelta(seconds=self._prune_interval_seconds)

    def track(self, user_msg_id: int, channel_id: int, response_msg_id: int) -> None:
        now = datetime.now(UTC)
        self._maybe_prune_stale_entries(now)
        self._map[channel_id][user_msg_id] = TrackedResponse(
            response_msg_id=response_msg_id,
            channel_id=channel_id,
            invoked_at=now,
        )

    def get(self, user_msg_id: int, channel_id: int) -> TrackedResponse | None:
        now = datetime.now(UTC)
        self._maybe_prune_stale_entries(now)
        channel_map = self._map.get(channel_id)
        if channel_map is None:
            return None
        entry = channel_map.get(user_msg_id)
        if not entry:
            return None
        if (now - entry.invoked_at).total_seconds() > self._ttl:
            del channel_map[user_msg_id]
            if not channel_map:
                del self._map[channel_id]
            return None
        return entry

    def untrack(self, user_msg_id: int, channel_id: int) -> None:
        if channel_id in self._map and user_msg_id in self._map[channel_id]:
            del self._map[channel_id][user_msg_id]
            if not self._map[channel_id]:
                del self._map[channel_id]

    def _maybe_prune_stale_entries(self, now: datetime) -> None:
        if now < self._next_prune_at:
            return

        stale_channels: list[int] = []
        for channel_id, channel_map in self._map.items():
            stale_user_msg_ids = [
                user_msg_id
                for user_msg_id, entry in channel_map.items()
                if (now - entry.invoked_at).total_seconds() > self._ttl
            ]
            for user_msg_id in stale_user_msg_ids:
                del channel_map[user_msg_id]
            if not channel_map:
                stale_channels.append(channel_id)

        for channel_id in stale_channels:
            del self._map[channel_id]

        self._next_prune_at = now + timedelta(seconds=self._prune_interval_seconds)
