#!/usr/bin/env python3
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.services import spotapi_subprocess  # noqa: E402
from bot.services.spotapi_sync import run_spotapi_operation_sync  # noqa: E402
from bot.services.spotify import (  # noqa: E402
    SPOTIFY_ALBUM_PATTERN,
    SPOTIFY_ARTIST_PATTERN,
    SPOTIFY_PLAYLIST_PATTERN,
    SPOTIFY_TRACK_PATTERN,
)

_OPERATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("track", SPOTIFY_TRACK_PATTERN),
    ("playlist", SPOTIFY_PLAYLIST_PATTERN),
    ("album", SPOTIFY_ALBUM_PATTERN),
    ("artist", SPOTIFY_ARTIST_PATTERN),
)


def _operation_and_id(url: str) -> tuple[str, str]:
    for operation, pattern in _OPERATION_PATTERNS:
        match = pattern.search(url)
        if match:
            return operation, match.group(1)
    raise SystemExit(f"unsupported Spotify URL: {url}")


async def _run_probe(url: str, *, in_process: bool, timeout_sec: float) -> list[str] | str | None:
    operation, entity_id = _operation_and_id(url)
    if in_process:
        return run_spotapi_operation_sync(operation, entity_id)
    return await spotapi_subprocess.run_spotapi_subprocess(
        operation,
        entity_id,
        timeout_sec=timeout_sec,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe SpotAPI for a Spotify URL")
    parser.add_argument("url", help="Spotify track/playlist/album/artist URL")
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Run SpotAPI in this process (may SIGSEGV on Alpine/musl)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=90.0,
        help="Subprocess timeout in seconds (default: 90)",
    )
    args = parser.parse_args(argv)
    result = asyncio.run(
        _run_probe(args.url.strip(), in_process=args.in_process, timeout_sec=args.timeout)
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
