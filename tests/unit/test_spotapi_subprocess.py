import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services import spotapi_subprocess as subprocess_module
from bot.services.spotapi_sync import run_spotapi_operation_sync


class TestDecodeWorkerResponse:
    @pytest.mark.parametrize(
        "result,expected",
        [
            (["A - B"], ["A - B"]),
            ("Artist - Song", "Artist - Song"),
        ],
    )
    def test_ok_payload(self, result, expected):
        payload = json.dumps({"ok": True, "result": result}).encode()
        assert subprocess_module.decode_worker_response(payload) == expected

    def test_not_ok_returns_none(self):
        payload = json.dumps({"ok": False, "error": "SongError"}).encode()
        assert subprocess_module.decode_worker_response(payload) is None

    def test_empty_stdout_returns_none(self):
        assert subprocess_module.decode_worker_response(b"") is None

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            subprocess_module.decode_worker_response(b"not-json")


class TestRunSpotapiSubprocess:
    @pytest.mark.asyncio
    async def test_success(self):
        stdout = json.dumps({"ok": True, "result": "Artist - Title"}).encode()
        proc = MagicMock(returncode=0, communicate=AsyncMock(return_value=(stdout, b"")))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            result = await subprocess_module.run_spotapi_subprocess(
                "track", "tid", timeout_sec=30.0
            )
        assert result == "Artist - Title"

    @pytest.mark.asyncio
    async def test_signal_exit_returns_none(self):
        proc = MagicMock(returncode=-11, communicate=AsyncMock(return_value=(b"", b"")))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            result = await subprocess_module.run_spotapi_subprocess(
                "track", "tid", timeout_sec=30.0
            )
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("returncode,stderr", [(1, b"err"), (1, b"")])
    async def test_nonzero_exit_returns_none(self, returncode, stderr):
        proc = MagicMock(returncode=returncode, communicate=AsyncMock(return_value=(b"", stderr)))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            result = await subprocess_module.run_spotapi_subprocess(
                "track", "tid", timeout_sec=30.0
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_timeout_kills_worker(self):
        proc = MagicMock()
        proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        proc.kill = MagicMock()
        proc.wait = AsyncMock()
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            result = await subprocess_module.run_spotapi_subprocess("track", "tid", timeout_sec=1.0)
        assert result is None
        proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_json_stdout(self):
        proc = MagicMock(returncode=0, communicate=AsyncMock(return_value=(b"{bad", b"")))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            result = await subprocess_module.run_spotapi_subprocess(
                "track", "tid", timeout_sec=30.0
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_operation_raises(self):
        with pytest.raises(ValueError, match="unknown SpotAPI operation"):
            await subprocess_module.run_spotapi_subprocess("badop", "id", timeout_sec=5.0)


class TestRunSpotapiOperationSync:
    def test_unknown_operation_raises(self):
        with pytest.raises(ValueError, match="unknown SpotAPI operation"):
            run_spotapi_operation_sync("nope", "id")

    @pytest.mark.parametrize(
        ("operation", "sync_attr", "expected"),
        [
            ("track", "sync_track_query", "Artist - Song"),
            ("playlist", "sync_playlist_catalog", ["A - B"]),
            ("album", "sync_album_catalog", ["A - B"]),
            ("artist", "sync_artist_catalog", ["A - B"]),
        ],
    )
    def test_dispatch_operations(self, operation, sync_attr, expected):
        with patch(f"bot.services.spotapi_sync.{sync_attr}", return_value=expected):
            assert run_spotapi_operation_sync(operation, "id") == expected


class TestSubprocessEnv:
    def test_subprocess_env_sets_pythonpath(self, monkeypatch):
        monkeypatch.delenv("PYTHONPATH", raising=False)
        env = subprocess_module._subprocess_env()
        assert str(subprocess_module._APP_ROOT) in env["PYTHONPATH"]

    def test_subprocess_env_appends_existing_pythonpath(self, monkeypatch):
        monkeypatch.setenv("PYTHONPATH", "/existing")
        env = subprocess_module._subprocess_env()
        assert env["PYTHONPATH"].startswith(str(subprocess_module._APP_ROOT))
        assert "/existing" in env["PYTHONPATH"]
