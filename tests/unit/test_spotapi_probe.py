import json
from unittest.mock import AsyncMock, patch

import pytest

from scripts import spotapi_probe


class TestSpotapiProbe:
    def test_operation_and_id_track(self):
        op, entity_id = spotapi_probe._operation_and_id(
            "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"
        )
        assert op == "track"
        assert entity_id == "4iV5W9uYEdYUVa79Axb7Rh"

    def test_operation_and_id_unsupported_exits(self):
        with pytest.raises(SystemExit, match="unsupported"):
            spotapi_probe._operation_and_id("https://example.com/not-spotify")

    @pytest.mark.asyncio
    async def test_run_probe_in_process(self):
        with patch(
            "scripts.spotapi_probe.run_spotapi_operation_sync",
            return_value="Artist - Song",
        ):
            result = await spotapi_probe._run_probe(
                "https://open.spotify.com/track/abc",
                in_process=True,
                timeout_sec=30.0,
            )
        assert result == "Artist - Song"

    @pytest.mark.asyncio
    async def test_run_probe_subprocess(self):
        with patch(
            "scripts.spotapi_probe.spotapi_subprocess.run_spotapi_subprocess",
            AsyncMock(return_value=["A - B"]),
        ) as sub_mock:
            result = await spotapi_probe._run_probe(
                "https://open.spotify.com/playlist/abc",
                in_process=False,
                timeout_sec=45.0,
            )
        assert result == ["A - B"]
        sub_mock.assert_awaited_once_with("playlist", "abc", timeout_sec=45.0)

    def test_main_success(self, capsys):
        with patch(
            "scripts.spotapi_probe.asyncio.run",
            return_value="Artist - Title",
        ):
            code = spotapi_probe.main(["https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"])
        assert code == 0
        out = json.loads(capsys.readouterr().out)
        assert out == "Artist - Title"

    def test_main_failure(self, capsys):
        with patch("scripts.spotapi_probe.asyncio.run", return_value=None):
            code = spotapi_probe.main(["https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"])
        assert code == 1
