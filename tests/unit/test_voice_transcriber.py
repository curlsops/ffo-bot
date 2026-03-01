from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.processors.voice_transcriber import SUPPORTED_CONTENT_TYPES, VoiceTranscriber


class TestIsVoiceAttachment:
    @pytest.fixture
    def vt(self):
        return VoiceTranscriber(api_key="sk-test")

    @pytest.mark.parametrize(
        "filename",
        ["voice.ogg", "audio.opus", "msg.webm", "sound.mp3", "recording.wav", "voice.m4a"],
    )
    def test_extension_match(self, vt, filename):
        assert vt.is_voice_attachment(filename, None) is True

    @pytest.mark.parametrize(
        "content_type",
        ["audio/ogg", "audio/opus", "audio/webm", "audio/mpeg", "audio/wav"],
    )
    def test_content_type_match(self, vt, content_type):
        assert vt.is_voice_attachment("unknown.xyz", content_type) is True

    def test_content_type_with_params(self, vt):
        assert vt.is_voice_attachment("x.xyz", "audio/ogg; codecs=opus") is True

    @pytest.mark.parametrize("filename", ["image.png", "doc.pdf", "data.bin", ""])
    def test_not_voice_by_extension(self, vt, filename):
        assert vt.is_voice_attachment(filename, None) is False

    def test_not_voice_by_content_type(self, vt):
        assert vt.is_voice_attachment("x.xyz", "image/png") is False


class TestEnabled:
    def test_enabled_with_api_key(self):
        vt = VoiceTranscriber(api_key="sk-test")
        assert vt.enabled is True

    def test_disabled_without_api_key(self):
        vt = VoiceTranscriber(api_key=None)
        assert vt.enabled is False


class TestTranscribe:
    @pytest.fixture
    def vt(self):
        return VoiceTranscriber(api_key="sk-test")

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self):
        vt = VoiceTranscriber(api_key=None)
        result = await vt.transcribe("https://example.com/voice.ogg", "voice.ogg")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_none(self, vt):
        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status = 404
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(get=MagicMock(return_value=mock_resp))
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await vt.transcribe("https://example.com/voice.ogg", "voice.ogg")
            assert result is None

    @pytest.mark.asyncio
    async def test_too_large_returns_none(self, vt):
        large_data = b"x" * (26 * 1024 * 1024)
        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read = AsyncMock(return_value=large_data)
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(get=MagicMock(return_value=mock_resp))
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await vt.transcribe("https://example.com/voice.ogg", "voice.ogg")
            assert result is None

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self, vt):
        with patch("aiohttp.ClientSession") as mock_session:
            get_resp = MagicMock()
            get_resp.status = 200
            get_resp.read = AsyncMock(return_value=b"fake_audio")
            get_resp.__aenter__ = AsyncMock(return_value=get_resp)
            get_resp.__aexit__ = AsyncMock(return_value=None)

            post_resp = MagicMock()
            post_resp.status = 500
            post_resp.text = AsyncMock(return_value="API error")
            post_resp.read = AsyncMock(return_value=b"")
            post_resp.__aenter__ = AsyncMock(return_value=post_resp)
            post_resp.__aexit__ = AsyncMock(return_value=None)

            mock_ctx = MagicMock()
            mock_ctx.get.return_value = get_resp
            mock_ctx.post.return_value = post_resp
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await vt.transcribe("https://example.com/voice.ogg", "voice.ogg")
            assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_success(self, vt):
        with patch("aiohttp.ClientSession") as mock_session:
            get_resp = MagicMock()
            get_resp.status = 200
            get_resp.read = AsyncMock(return_value=b"fake_audio_data")
            get_resp.__aenter__ = AsyncMock(return_value=get_resp)
            get_resp.__aexit__ = AsyncMock(return_value=None)

            post_resp = MagicMock()
            post_resp.status = 200
            post_resp.read = AsyncMock(return_value=b"Hello world")
            post_resp.__aenter__ = AsyncMock(return_value=post_resp)
            post_resp.__aexit__ = AsyncMock(return_value=None)

            mock_ctx = MagicMock()
            mock_ctx.get.return_value = get_resp
            mock_ctx.post.return_value = post_resp
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await vt.transcribe("https://example.com/voice.ogg", "voice.ogg")
            assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_transcribe_empty_text_returns_none(self, vt):
        with patch("aiohttp.ClientSession") as mock_session:
            get_resp = MagicMock()
            get_resp.status = 200
            get_resp.read = AsyncMock(return_value=b"fake_audio")
            get_resp.__aenter__ = AsyncMock(return_value=get_resp)
            get_resp.__aexit__ = AsyncMock(return_value=None)

            post_resp = MagicMock()
            post_resp.status = 200
            post_resp.read = AsyncMock(return_value=b"   ")
            post_resp.__aenter__ = AsyncMock(return_value=post_resp)
            post_resp.__aexit__ = AsyncMock(return_value=None)

            mock_ctx = MagicMock()
            mock_ctx.get.return_value = get_resp
            mock_ctx.post.return_value = post_resp
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await vt.transcribe("https://example.com/voice.ogg", "voice.ogg")
            assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_exception_returns_none(self, vt):
        with patch("aiohttp.ClientSession") as mock_session:
            mock_ctx = MagicMock()
            mock_ctx.get.side_effect = OSError("Connection refused")
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await vt.transcribe("https://example.com/voice.ogg", "voice.ogg")
            assert result is None


class TestSupportedContentTypes:
    def test_constants_defined(self):
        assert "audio/ogg" in SUPPORTED_CONTENT_TYPES
        assert "audio/opus" in SUPPORTED_CONTENT_TYPES
