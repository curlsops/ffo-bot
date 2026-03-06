import os

import pytest

from bot.services.spotify import spotify_playlist_to_search_queries

SPOTIFY_PLAYLIST_URL = (
    "https://open.spotify.com/playlist/5bCeKZhm0Vrk4cOydmil2N?si=04bf39def50c41bc"
)
EXPECTED_FIRST_TRACKS = [
    "Yuka Kitamura - Slave Knight Gael",
    "Yuka Kitamura - Soul of Cinder",
    "SQUARE ENIX MUSIC - Shadowlord",
]


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_spotify_playlist_fetches_real_tracks():
    cid = os.environ.get("SPOTIFY_CLIENT_ID")
    csec = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not cid or not csec:
        pytest.skip("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET required")

    result = await spotify_playlist_to_search_queries(SPOTIFY_PLAYLIST_URL, cid, csec)
    assert result is not None
    assert len(result) >= len(EXPECTED_FIRST_TRACKS)
    for i, expected in enumerate(EXPECTED_FIRST_TRACKS):
        assert result[i] == expected, f"Track {i + 1}: got {result[i]!r}"
