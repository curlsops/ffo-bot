import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.processors.media_downloader import MediaAttachment, MediaDownloader


@pytest.fixture
def tmpdir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def downloader(tmpdir):
    return MediaDownloader(MagicMock(), tmpdir)


def _db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


def _attachment(
    url="https://example.com/img.png", filename="img.png", content_type="image/png", size=1024
):
    return MediaAttachment(url=url, filename=filename, content_type=content_type, size_bytes=size)


class AsyncCtx:
    def __init__(self, val):
        self.val = val

    async def __aenter__(self):
        return self.val

    async def __aexit__(self, *_):
        pass


async def _async_chunks(chunks):
    for c in chunks:
        yield c


class TestMediaAttachment:
    def test_creation(self):
        a = _attachment()
        assert a.url == "https://example.com/img.png"
        assert a.size_bytes == 1024


class TestMediaDownloaderInit:
    def test_initialization(self, tmpdir):
        d = MediaDownloader(MagicMock(), tmpdir, MagicMock())
        assert d.storage_base == Path(tmpdir)
        assert d.session is None

    def test_without_metrics(self, downloader):
        assert downloader.metrics is None


class TestFileType:
    @pytest.mark.parametrize(
        "content_type,expected",
        [
            ("image/png", "image"),
            ("image/jpeg", "image"),
            ("image/gif", "gif"),
            ("video/mp4", "video"),
            ("application/pdf", None),
            ("text/plain", None),
            (None, None),
        ],
    )
    def test_get_file_type(self, downloader, content_type, expected):
        assert downloader._get_file_type(content_type) == expected


class TestStoragePath:
    def test_generates_path(self, downloader):
        path = downloader._generate_storage_path(123, "test.png")
        assert path.suffix == ".png" and "123" in str(path) and path.parent.exists()

    def test_sanitizes_path(self, downloader):
        path = downloader._generate_storage_path(123, "../../../etc/passwd")
        assert "etc" not in str(path.parent) and path.name == "passwd"

    def test_handles_collision(self, downloader):
        p1 = downloader._generate_storage_path(123, "test.png")
        p1.touch()
        p2 = downloader._generate_storage_path(123, "test.png")
        assert p1 != p2 and "test_1.png" in str(p2)


class TestSessionManagement:
    @pytest.mark.asyncio
    async def test_initialize(self, downloader):
        with patch("aiohttp.ClientSession") as mock_cls:
            await downloader.initialize()
            assert downloader.session is not None

    @pytest.mark.asyncio
    async def test_close(self, downloader):
        downloader.session = AsyncMock()
        await downloader.close()
        downloader.session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_no_session(self, downloader):
        await downloader.close()


class TestDownloadOperations:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("with_metrics", [True, False])
    async def test_skips_large_files(self, tmpdir, with_metrics):
        metrics = MagicMock() if with_metrics else None
        d = MediaDownloader(MagicMock(), tmpdir, metrics)
        d.session = AsyncMock()
        await d.download_media(1, 2, 3, 4, [_attachment(size=200 * 1024 * 1024)])
        if with_metrics:
            metrics.media_downloads.labels.assert_called()

    @pytest.mark.asyncio
    async def test_skips_non_media(self, downloader):
        downloader.session = AsyncMock()
        await downloader.download_media(1, 2, 3, 4, [_attachment(content_type="text/plain")])

    @pytest.mark.asyncio
    async def test_initializes_session(self, downloader):
        with patch.object(downloader, "initialize", new_callable=AsyncMock) as m:
            await downloader.download_media(1, 2, 3, 4, [_attachment(content_type="text/plain")])
            m.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_file(self, downloader, tmpdir):
        resp = AsyncMock(raise_for_status=MagicMock())
        resp.content.iter_chunked = lambda _: _async_chunks([b"test data"])
        downloader.session = MagicMock(get=MagicMock(return_value=AsyncCtx(resp)))

        dest = Path(tmpdir) / "test.txt"
        checksum = await downloader._download_file("https://example.com/f", dest)

        assert dest.read_bytes() == b"test data" and len(checksum) == 64

    @pytest.mark.asyncio
    async def test_store_metadata(self, tmpdir):
        conn = AsyncMock()
        d = MediaDownloader(_db_ctx(conn), tmpdir)
        await d._store_metadata(
            123, 456, 789, 111, "t.png", "image", ".png", 1024, "path", "url", "hash"
        )
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("with_metrics", [True, False])
    async def test_download_success(self, tmpdir, with_metrics):
        conn = AsyncMock()
        metrics = MagicMock() if with_metrics else None
        if metrics:
            metrics.media_download_duration.labels.return_value.time.return_value = MagicMock()
        d = MediaDownloader(_db_ctx(conn), tmpdir, metrics)

        resp = AsyncMock(raise_for_status=MagicMock())
        resp.content.iter_chunked = lambda _: _async_chunks([b"test"])
        d.session = MagicMock(get=MagicMock(return_value=AsyncCtx(resp)))

        await d.download_media(1, 2, 3, 4, [_attachment()])
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("with_metrics", [True, False])
    async def test_download_error(self, tmpdir, with_metrics):
        metrics = MagicMock() if with_metrics else None
        d = MediaDownloader(MagicMock(), tmpdir, metrics)
        d.session = MagicMock(get=MagicMock(side_effect=Exception("err")))
        await d.download_media(1, 2, 3, 4, [_attachment()])
