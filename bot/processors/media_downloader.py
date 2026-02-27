"""Media file download and storage manager."""

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional

import aiofiles
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class MediaAttachment:
    """Discord media attachment metadata."""

    url: str
    filename: str
    content_type: str
    size_bytes: int


class MediaDownloader:
    """Download and store media files from Discord."""

    # Maximum file size: 100 MB
    MAX_FILE_SIZE = 100 * 1024 * 1024
    CHUNK_SIZE = 8192

    def __init__(self, db_pool, storage_base_path: str, metrics=None):
        """
        Initialize media downloader.

        Args:
            db_pool: Database connection pool
            storage_base_path: Base path for media storage
            metrics: Metrics collector (optional)
        """
        self.db_pool = db_pool
        self.storage_base = Path(storage_base_path)
        self.metrics = metrics
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Initialize HTTP session."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300)  # 5 minute timeout
        )
        logger.info("Media downloader initialized")

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            logger.info("Media downloader closed")

    async def download_media(
        self,
        message_id: int,
        channel_id: int,
        server_id: int,
        uploader_id: int,
        attachments: List[MediaAttachment],
    ):
        """
        Download media attachments and store metadata.

        Args:
            message_id: Discord message ID
            channel_id: Discord channel ID
            server_id: Discord server ID
            uploader_id: Discord user ID
            attachments: List of attachments to download
        """
        if not self.session:
            await self.initialize()

        for attachment in attachments:
            try:
                # Validate file size
                if attachment.size_bytes > self.MAX_FILE_SIZE:
                    logger.warning(
                        f"Skipping large file {attachment.filename} "
                        f"({attachment.size_bytes} bytes) from message {message_id}"
                    )
                    if self.metrics:
                        self.metrics.media_downloads.labels(
                            server_id=str(server_id), file_type="oversized", status="skipped"
                        ).inc()
                    continue

                # Determine file type
                file_type = self._get_file_type(attachment.content_type)

                if not file_type:
                    logger.debug(f"Skipping non-media file {attachment.filename}")
                    continue

                # Track download time
                if self.metrics:
                    timer = self.metrics.media_download_duration.labels(file_type=file_type).time()
                else:
                    timer = None

                try:
                    # Generate storage path
                    storage_path = self._generate_storage_path(server_id, attachment.filename)

                    # Download file with streaming
                    checksum = await self._download_file(attachment.url, storage_path)

                    # Store metadata in database
                    await self._store_metadata(
                        server_id=server_id,
                        message_id=message_id,
                        channel_id=channel_id,
                        uploader_id=uploader_id,
                        filename=attachment.filename,
                        file_type=file_type,
                        file_extension=Path(attachment.filename).suffix,
                        file_size=attachment.size_bytes,
                        storage_path=str(storage_path.relative_to(self.storage_base)),
                        download_url=attachment.url,
                        checksum=checksum,
                    )

                    logger.info(f"Downloaded media {attachment.filename} from message {message_id}")

                    if self.metrics:
                        self.metrics.media_downloads.labels(
                            server_id=str(server_id), file_type=file_type, status="success"
                        ).inc()

                finally:
                    if timer:
                        timer.__exit__(None, None, None)

            except Exception as e:
                logger.error(
                    f"Failed to download {attachment.filename} " f"from message {message_id}: {e}",
                    exc_info=True,
                )
                if self.metrics:
                    self.metrics.media_downloads.labels(
                        server_id=str(server_id),
                        file_type=file_type if file_type else "unknown",
                        status="error",
                    ).inc()

    def _get_file_type(self, content_type: str) -> Optional[str]:
        """
        Determine file type from MIME type.

        Args:
            content_type: MIME content type

        Returns:
            File type or None
        """
        if content_type.startswith("image/gif"):
            return "gif"
        elif content_type.startswith("image/"):
            return "image"
        elif content_type.startswith("video/"):
            return "video"
        return None

    def _generate_storage_path(self, server_id: int, filename: str) -> Path:
        """
        Generate organized storage path.

        Path format: /media/<server_id>/<YYYY-MM-DD>/<filename>

        Args:
            server_id: Discord server ID
            filename: Original filename

        Returns:
            Full storage path
        """
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")

        # Sanitize filename to prevent path traversal
        safe_filename = Path(filename).name  # Removes any path components

        path = self.storage_base / str(server_id) / date_str / safe_filename

        # Create directory if not exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Handle filename collisions
        counter = 1
        original_path = path
        while path.exists():
            stem = original_path.stem
            suffix = original_path.suffix
            path = original_path.parent / f"{stem}_{counter}{suffix}"
            counter += 1

        return path

    async def _download_file(self, url: str, destination: Path) -> str:
        """
        Download file with streaming and return SHA256 checksum.

        Args:
            url: Download URL
            destination: Destination file path

        Returns:
            SHA256 checksum
        """
        sha256 = hashlib.sha256()

        async with self.session.get(url) as response:
            response.raise_for_status()

            async with aiofiles.open(destination, "wb") as f:
                async for chunk in response.content.iter_chunked(self.CHUNK_SIZE):
                    await f.write(chunk)
                    sha256.update(chunk)

        return sha256.hexdigest()

    async def _store_metadata(self, **kwargs):
        """
        Store media file metadata in database.

        Args:
            **kwargs: Metadata fields
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO media_files (
                    server_id, message_id, channel_id, uploader_id,
                    file_name, file_type, file_extension, file_size_bytes,
                    storage_path, download_url, checksum_sha256
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (message_id, file_name) DO NOTHING
                """,
                kwargs["server_id"],
                kwargs["message_id"],
                kwargs["channel_id"],
                kwargs["uploader_id"],
                kwargs["filename"],
                kwargs["file_type"],
                kwargs["file_extension"],
                kwargs["file_size"],
                kwargs["storage_path"],
                kwargs["download_url"],
                kwargs["checksum"],
            )
