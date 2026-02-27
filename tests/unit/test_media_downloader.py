"""Tests for media downloader functionality."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.processors.media_downloader import MediaAttachment, MediaDownloader


class TestMediaAttachment:
    """Tests for MediaAttachment dataclass."""

    def test_media_attachment_creation(self):
        """Test creating a MediaAttachment."""
        attachment = MediaAttachment(
            url="https://cdn.discord.com/attachments/123/456/image.png",
            filename="image.png",
            content_type="image/png",
            size_bytes=1024,
        )

        assert attachment.url == "https://cdn.discord.com/attachments/123/456/image.png"
        assert attachment.filename == "image.png"
        assert attachment.content_type == "image/png"
        assert attachment.size_bytes == 1024


class TestMediaDownloaderInit:
    """Tests for MediaDownloader initialization."""

    def test_media_downloader_initialization(self):
        """Test MediaDownloader initialization."""
        mock_db_pool = MagicMock()
        mock_metrics = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir, mock_metrics)

            assert downloader.db_pool == mock_db_pool
            assert downloader.storage_base == Path(tmpdir)
            assert downloader.metrics == mock_metrics
            assert downloader.session is None

    def test_media_downloader_without_metrics(self):
        """Test MediaDownloader without metrics."""
        mock_db_pool = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir)

            assert downloader.metrics is None


class TestMediaDownloaderMethods:
    """Tests for MediaDownloader methods."""

    def test_get_file_type_image(self):
        """Test file type detection for images."""
        mock_db_pool = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir)

            assert downloader._get_file_type("image/png") == "image"
            assert downloader._get_file_type("image/jpeg") == "image"
            assert downloader._get_file_type("image/webp") == "image"

    def test_get_file_type_gif(self):
        """Test file type detection for GIFs."""
        mock_db_pool = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir)

            assert downloader._get_file_type("image/gif") == "gif"

    def test_get_file_type_video(self):
        """Test file type detection for videos."""
        mock_db_pool = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir)

            assert downloader._get_file_type("video/mp4") == "video"
            assert downloader._get_file_type("video/webm") == "video"

    def test_get_file_type_unsupported(self):
        """Test file type detection for unsupported types."""
        mock_db_pool = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir)

            assert downloader._get_file_type("application/pdf") is None
            assert downloader._get_file_type("text/plain") is None
            assert downloader._get_file_type("audio/mp3") is None

    def test_generate_storage_path(self):
        """Test storage path generation."""
        mock_db_pool = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir)

            path = downloader._generate_storage_path(123456789, "test_image.png")

            assert path.suffix == ".png"
            assert "123456789" in str(path)
            assert path.parent.exists()

    def test_generate_storage_path_sanitizes_filename(self):
        """Test storage path sanitizes malicious filenames."""
        mock_db_pool = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir)

            path = downloader._generate_storage_path(123456789, "../../../etc/passwd")

            assert "etc" not in str(path.parent)
            assert path.name == "passwd"

    def test_generate_storage_path_handles_collision(self):
        """Test storage path handles filename collisions."""
        mock_db_pool = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir)

            path1 = downloader._generate_storage_path(123456789, "test.png")
            path1.touch()

            path2 = downloader._generate_storage_path(123456789, "test.png")

            assert path1 != path2
            assert "test_1.png" in str(path2)


class TestMediaDownloaderAsync:
    """Tests for async MediaDownloader methods."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        """Test async initialization."""
        mock_db_pool = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir)

            with patch("aiohttp.ClientSession") as mock_session_class:
                mock_session = MagicMock()
                mock_session_class.return_value = mock_session

                await downloader.initialize()

                assert downloader.session == mock_session

    @pytest.mark.asyncio
    async def test_close(self):
        """Test async close."""
        mock_db_pool = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir)
            downloader.session = AsyncMock()

            await downloader.close()

            downloader.session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_no_session(self):
        """Test close with no session."""
        mock_db_pool = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir)

            await downloader.close()

    @pytest.mark.asyncio
    async def test_download_media_skips_large_files(self):
        """Test download skips files exceeding size limit."""
        mock_db_pool = MagicMock()
        mock_metrics = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir, mock_metrics)
            downloader.session = AsyncMock()

            large_attachment = MediaAttachment(
                url="https://example.com/large.mp4",
                filename="large.mp4",
                content_type="video/mp4",
                size_bytes=200 * 1024 * 1024,
            )

            await downloader.download_media(
                message_id=1,
                channel_id=2,
                server_id=3,
                uploader_id=4,
                attachments=[large_attachment],
            )

            mock_metrics.media_downloads.labels.assert_called()

    @pytest.mark.asyncio
    async def test_download_media_skips_non_media(self):
        """Test download skips non-media files."""
        mock_db_pool = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir)
            downloader.session = AsyncMock()

            text_attachment = MediaAttachment(
                url="https://example.com/file.txt",
                filename="file.txt",
                content_type="text/plain",
                size_bytes=100,
            )

            await downloader.download_media(
                message_id=1,
                channel_id=2,
                server_id=3,
                uploader_id=4,
                attachments=[text_attachment],
            )

    @pytest.mark.asyncio
    async def test_download_media_initializes_session_if_needed(self):
        """Test download initializes session if not present."""
        mock_db_pool = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MediaDownloader(mock_db_pool, tmpdir)

            text_attachment = MediaAttachment(
                url="https://example.com/file.txt",
                filename="file.txt",
                content_type="text/plain",
                size_bytes=100,
            )

            with patch.object(downloader, "initialize", new_callable=AsyncMock) as mock_init:
                await downloader.download_media(
                    message_id=1,
                    channel_id=2,
                    server_id=3,
                    uploader_id=4,
                    attachments=[text_attachment],
                )

                mock_init.assert_called_once()
