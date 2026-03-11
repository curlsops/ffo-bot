import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiofiles
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class MediaAttachment:
    url: str
    filename: str
    content_type: str
    size_bytes: int


class MediaDownloader:
    MAX_FILE_SIZE = 100 * 1024 * 1024
    CHUNK_SIZE = 8192

    def __init__(self, db_pool, storage_base_path: str, metrics=None):
        self.db_pool = db_pool
        self.storage_base = Path(storage_base_path)
        self.metrics = metrics
        self.session: aiohttp.ClientSession | None = None

    async def initialize(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300))

    async def close(self):
        if self.session:
            await self.session.close()

    async def download_media(
        self,
        message_id: int,
        channel_id: int,
        server_id: int,
        uploader_id: int,
        attachments: list[MediaAttachment],
    ):
        if not self.session:
            await self.initialize()

        for att in attachments:
            try:
                if att.size_bytes > self.MAX_FILE_SIZE:
                    if self.metrics:
                        self.metrics.media_downloads.labels(
                            server_id=str(server_id), file_type="oversized", status="skipped"
                        ).inc()
                    continue

                file_type = self._get_file_type(att.content_type)
                if not file_type:
                    continue

                timer = (
                    self.metrics.media_download_duration.labels(file_type=file_type).time()
                    if self.metrics
                    else None
                )
                try:
                    storage_path = self._generate_storage_path(server_id, att.filename)
                    checksum = await self._download_file(att.url, storage_path)
                    await self._store_metadata(
                        server_id,
                        message_id,
                        channel_id,
                        uploader_id,
                        att.filename,
                        file_type,
                        Path(att.filename).suffix,
                        att.size_bytes,
                        str(storage_path.relative_to(self.storage_base)),
                        att.url,
                        checksum,
                    )
                    if self.metrics:
                        self.metrics.media_downloads.labels(
                            server_id=str(server_id), file_type=file_type, status="success"
                        ).inc()
                finally:
                    if timer:
                        timer.__exit__(None, None, None)
            except Exception as e:
                logger.error("Download failed %s: %s", att.filename, e, exc_info=True)
                if self.metrics:
                    self.metrics.media_downloads.labels(
                        server_id=str(server_id),
                        file_type=file_type if file_type else "unknown",
                        status="error",
                    ).inc()

    def _get_file_type(self, content_type: str | None) -> str | None:
        if not content_type:
            return None
        if content_type.startswith("image/gif"):
            return "gif"
        if content_type.startswith("image/"):
            return "image"
        if content_type.startswith("video/"):
            return "video"
        return None

    def _generate_storage_path(self, server_id: int, filename: str) -> Path:
        safe_filename = Path(filename).name
        path = (
            self.storage_base
            / str(server_id)
            / datetime.now(UTC).strftime("%Y-%m-%d")
            / safe_filename
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        counter = 1
        original = path
        while path.exists():
            path = original.parent / f"{original.stem}_{counter}{original.suffix}"
            counter += 1
        return path

    async def _download_file(self, url: str, destination: Path) -> str:
        if not self.session:
            await self.initialize()
        assert self.session is not None
        sha256 = hashlib.sha256()
        async with self.session.get(url) as response:
            response.raise_for_status()
            async with aiofiles.open(destination, "wb") as f:
                async for chunk in response.content.iter_chunked(self.CHUNK_SIZE):
                    await f.write(chunk)
                    sha256.update(chunk)
        return sha256.hexdigest()

    async def _store_metadata(
        self,
        server_id,
        message_id,
        channel_id,
        uploader_id,
        filename,
        file_type,
        ext,
        size,
        path,
        url,
        checksum,
    ):
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO media_files (server_id, message_id, channel_id, uploader_id, file_name, file_type, file_extension, file_size_bytes, storage_path, download_url, checksum_sha256) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) ON CONFLICT (message_id, file_name) DO NOTHING",
                server_id,
                message_id,
                channel_id,
                uploader_id,
                filename,
                file_type,
                ext,
                size,
                path,
                url,
                checksum,
            )
