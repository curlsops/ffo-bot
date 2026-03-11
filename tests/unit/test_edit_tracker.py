from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from bot.utils.edit_tracker import EditTracker, TrackedResponse


def test_track_and_get():
    t = EditTracker(ttl_seconds=60)
    t.track(user_msg_id=1, channel_id=2, response_msg_id=3)
    entry = t.get(1, 2)
    assert entry is not None
    assert entry.response_msg_id == 3


def test_get_missing():
    t = EditTracker()
    assert t.get(999, 999) is None


def test_untrack():
    t = EditTracker()
    t.track(1, 2, 3)
    t.untrack(1, 2)
    assert t.get(1, 2) is None


def test_get_expired_returns_none():
    t = EditTracker(ttl_seconds=60)
    before = datetime.now(UTC)
    t.track(1, 2, 3)
    with patch("bot.utils.edit_tracker.datetime") as m:
        m.now.return_value = before + timedelta(seconds=61)
        result = t.get(1, 2)
    assert result is None


def test_untrack_nonexistent_no_op():
    t = EditTracker()
    t.untrack(999, 999)
    assert t.get(999, 999) is None
