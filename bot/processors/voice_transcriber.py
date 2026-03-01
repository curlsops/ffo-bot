"""Voice message transcription using OpenAI Whisper API."""

import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# Discord voice messages are OGG Opus; Whisper API supports various formats
SUPPORTED_CONTENT_TYPES = {"audio/ogg", "audio/opus", "audio/webm", "audio/mpeg", "audio/wav"}


class VoiceTranscriber:
    """Transcribe voice message attachments using OpenAI Whisper API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self._enabled = bool(api_key)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def is_voice_attachment(self, filename: str, content_type: Optional[str]) -> bool:
        """Check if attachment appears to be a voice message."""
        fn_lower = filename.lower()
        if fn_lower.endswith((".ogg", ".opus", ".webm", ".mp3", ".wav", ".m4a")):
            return True
        if content_type and content_type.split(";")[0].strip().lower() in SUPPORTED_CONTENT_TYPES:
            return True
        return False

    async def transcribe(self, url: str, filename: str) -> Optional[str]:
        """Download audio from URL and transcribe via OpenAI API. Returns text or None on failure."""
        if not self._enabled:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning("Voice fetch failed: %s", resp.status)
                        return None
                    data = await resp.read()

            if len(data) > 25 * 1024 * 1024:  # 25MB Whisper API limit
                logger.warning("Voice message too large for transcription")
                return None

            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field("file", data, filename=filename)
                form.add_field("model", "whisper-1")
                form.add_field("response_format", "text")

                headers = {"Authorization": f"Bearer {self.api_key}"}
                async with session.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    data=form,
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        err = await resp.text()
                        logger.warning("Whisper API error %s: %s", resp.status, err[:200])
                        return None
                    text = (await resp.read()).decode("utf-8").strip()
                    return text if text else None
        except Exception as e:
            logger.error("Transcription error: %s", e, exc_info=True)
            return None
