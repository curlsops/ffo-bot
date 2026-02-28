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


def make_db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


def make_attachment(
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


async def async_chunks(chunks):
    for c in chunks:
        yield c


class TestMediaAttachment:
    def test_creation(self):
        a = make_attachment()
        assert a.url == "https://example.com/img.png"
        assert a.filename == "img.png"
        assert a.content_type == "image/png"
        assert a.size_bytes == 1024


class TestMediaDownloaderInit:
    def test_initialization(self, tmpdir):
        pool, metrics = MagicMock(), MagicMock()
        d = MediaDownloader(pool, tmpdir, metrics)
        assert d.db_pool == pool
        assert d.storage_base == Path(tmpdir)
        assert d.metrics == metrics
        assert d.session is None

    def test_without_metrics(self, downloader):
        assert downloader.metrics is None


class TestMediaDownloaderMethods:
    def test_get_file_type_image(self, downloader):
        assert downloader._get_file_type("image/png") == "image"
        assert downloader._get_file_type("image/jpeg") == "image"

    def test_get_file_type_gif(self, downloader):
        assert downloader._get_file_type("image/gif") == "gif"

    def test_get_file_type_video(self, downloader):
        assert downloader._get_file_type("video/mp4") == "video"

    def test_get_file_type_unsupported(self, downloader):
        assert downloader._get_file_type("application/pdf") is None
        assert downloader._get_file_type("text/plain") is None

    def test_generate_storage_path(self, downloader):
        path = downloader._generate_storage_path(123, "test.png")
        assert path.suffix == ".png"
        assert "123" in str(path)
        assert path.parent.exists()

    def test_generate_storage_path_sanitizes(self, downloader):
        path = downloader._generate_storage_path(123, "../../../etc/passwd")
        assert "etc" not in str(path.parent)
        assert path.name == "passwd"

    def test_generate_storage_path_collision(self, downloader):
        p1 = downloader._generate_storage_path(123, "test.png")
        p1.touch()
        p2 = downloader._generate_storage_path(123, "test.png")
        assert p1 != p2
        assert "test_1.png" in str(p2)


class TestMediaDownloaderAsync:
    @pytest.mark.asyncio
    async def test_initialize(self, downloader):
        with patch("aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value = MagicMock()
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

    @pytest.mark.asyncio
    async def test_download_media_skips_large_files(self, tmpdir):
        metrics = MagicMock()
        d = MediaDownloader(MagicMock(), tmpdir, metrics)
        d.session = AsyncMock()
        await d.download_media(1, 2, 3, 4, [make_attachment(size=200 * 1024 * 1024)])
        metrics.media_downloads.labels.assert_called()

    @pytest.mark.asyncio
    async def test_download_media_skips_non_media(self, downloader):
        downloader.session = AsyncMock()
        await downloader.download_media(1, 2, 3, 4, [make_attachment(content_type="text/plain")])

    @pytest.mark.asyncio
    async def test_download_media_initializes_session(self, downloader):
        with patch.object(downloader, "initialize", new_callable=AsyncMock) as mock_init:
            await downloader.download_media(
                1, 2, 3, 4, [make_attachment(content_type="text/plain")]
            )
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_file(self, downloader, tmpdir):
        resp = AsyncMock(raise_for_status=MagicMock())
        resp.content.iter_chunked = lambda _: async_chunks([b"test data"])
        session = MagicMock()
        session.get = MagicMock(return_value=AsyncCtx(resp))
        downloader.session = session

        dest = Path(tmpdir) / "test.txt"
        checksum = await downloader._download_file("https://example.com/f", dest)

        assert dest.exists()
        assert dest.read_bytes() == b"test data"
        assert len(checksum) == 64

    @pytest.mark.asyncio
    async def test_store_metadata(self, tmpdir):
        conn = AsyncMock()
        d = MediaDownloader(make_db_ctx(conn), tmpdir)
        await d._store_metadata(
            123, 456, 789, 111, "t.png", "image", ".png", 1024, "path", "url", "hash"
        )
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("with_metrics", [True, False])
    async def test_download_media_success(self, tmpdir, with_metrics):
        conn = AsyncMock()
        metrics = MagicMock() if with_metrics else None
        if metrics:
            metrics.media_download_duration.labels.return_value.time.return_value = MagicMock()
        d = MediaDownloader(make_db_ctx(conn), tmpdir, metrics)

        resp = AsyncMock(raise_for_status=MagicMock())
        resp.content.iter_chunked = lambda _: async_chunks([b"test"])
        d.session = MagicMock(get=MagicMock(return_value=AsyncCtx(resp)))

        await d.download_media(1, 2, 3, 4, [make_attachment()])
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("with_metrics", [True, False])
    async def test_download_media_error(self, tmpdir, with_metrics):
        metrics = MagicMock() if with_metrics else None
        d = MediaDownloader(MagicMock(), tmpdir, metrics)
        d.session = MagicMock(get=MagicMock(side_effect=Exception("err")))
        await d.download_media(1, 2, 3, 4, [make_attachment()])

    @pytest.mark.asyncio
    @pytest.mark.parametrize("with_metrics", [True, False])
    async def test_download_media_skips_large(self, tmpdir, with_metrics):
        metrics = MagicMock() if with_metrics else None
        d = MediaDownloader(MagicMock(), tmpdir, metrics)
        d.session = AsyncMock()
        await d.download_media(1, 2, 3, 4, [make_attachment(size=200 * 1024 * 1024)])
