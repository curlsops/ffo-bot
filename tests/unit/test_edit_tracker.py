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


def test_track_prunes_expired_entries_across_channels():
    before = datetime.now(UTC)
    with patch("bot.utils.edit_tracker.datetime") as m:
        m.now.return_value = before
        m.UTC = UTC
        t = EditTracker(ttl_seconds=60)
        t.track(1, 10, 100)
        t.track(2, 20, 200)
        assert set(t._map) == {10, 20}

        m.now.return_value = before + timedelta(seconds=61)
        t.track(3, 30, 300)
        assert set(t._map) == {30}
        assert t.get(1, 10) is None
        assert t.get(2, 20) is None
        assert t.get(3, 30) is not None


def test_untrack_removes_empty_channel_bucket():
    t = EditTracker()
    t.track(1, 2, 3)
    assert 2 in t._map
    t.untrack(1, 2)
    assert 2 not in t._map


def test_get_missing_entry_in_existing_channel_returns_none():
    t = EditTracker()
    t.track(1, 2, 3)
    assert t.get(999, 2) is None


def test_get_expired_entry_removes_channel_bucket():
    before = datetime.now(UTC)
    with patch("bot.utils.edit_tracker.datetime") as m:
        m.now.return_value = before
        m.UTC = UTC
        t = EditTracker(ttl_seconds=60)
        t.track(1, 2, 3)
        t._next_prune_at = before + timedelta(days=1)

        m.now.return_value = before + timedelta(seconds=61)
        assert t.get(1, 2) is None
        assert 2 not in t._map


def test_get_expired_entry_keeps_channel_when_other_entries_exist():
    before = datetime.now(UTC)
    with patch("bot.utils.edit_tracker.datetime") as m:
        m.now.return_value = before
        m.UTC = UTC
        t = EditTracker(ttl_seconds=60)
        t.track(1, 2, 3)
        t.track(2, 2, 4)
        t._next_prune_at = before + timedelta(days=1)
        t._map[2][2].invoked_at = before + timedelta(seconds=30)

        m.now.return_value = before + timedelta(seconds=61)
        assert t.get(1, 2) is None
        assert 2 in t._map
        assert 2 in t._map[2]


def test_untrack_keeps_channel_when_other_entries_exist():
    t = EditTracker()
    t.track(1, 2, 3)
    t.track(2, 2, 4)
    t.untrack(1, 2)
    assert 2 in t._map
    assert 2 in t._map[2]


def test_prune_mixed_channels_keeps_non_empty_channel():
    before = datetime.now(UTC)
    with patch("bot.utils.edit_tracker.datetime") as m:
        m.now.return_value = before
        m.UTC = UTC
        t = EditTracker(ttl_seconds=60)
        t.track(1, 10, 100)
        t.track(2, 20, 200)
        t.track(3, 20, 300)
        t._map[20][3].invoked_at = before + timedelta(seconds=30)
        t._next_prune_at = before + timedelta(seconds=1)

        m.now.return_value = before + timedelta(seconds=61)
        t.track(4, 30, 400)
        assert 10 not in t._map
        assert 20 in t._map
        assert 3 in t._map[20]
