import pytest

from bot.services.spotify import spotify_playlist_catalog_queries

SPOTIFY_PLAYLIST_URL = (
    "https://open.spotify.com/playlist/7soPh0TWD5LFOt7doETqNq?si=b14fe019fa6a47fa"
)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_spotify_playlist_fetches_real_tracks():
    result = await spotify_playlist_catalog_queries(SPOTIFY_PLAYLIST_URL)
    assert result is not None
    assert len(result) >= 5
    assert all(isinstance(s, str) and s.strip() for s in result)
