import os

import pytest

from bot.services.spotify import spotify_playlist_catalog_queries

SPOTIFY_PLAYLIST_URL = (
    "https://open.spotify.com/playlist/7soPh0TWD5LFOt7doETqNq?si=b14fe019fa6a47fa"
)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_spotify_playlist_fetches_real_tracks():
    cid = os.environ.get("SPOTIFY_CLIENT_ID")
    csec = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not cid or not csec:
        pytest.skip("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET required")

    result = await spotify_playlist_catalog_queries(SPOTIFY_PLAYLIST_URL, cid, csec)
    assert result is not None
    assert len(result) >= 40
    assert all(isinstance(s, str) and s.strip() for s in result)
