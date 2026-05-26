import logging

import aiohttp

from bot.utils.http_session import get_session as _get_session
from bot.utils.http_session import session_scope

get_session = _get_session

logger = logging.getLogger(__name__)

SUPPORTED_CONTENT_TYPES = {"audio/ogg", "audio/opus", "audio/webm", "audio/mpeg", "audio/wav"}
WHISPER_MAX_BYTES = 25 * 1024 * 1024


class VoiceTranscriber:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def is_voice_attachment(self, filename: str, content_type: str | None) -> bool:
        fn_lower = filename.lower()
        if fn_lower.endswith((".ogg", ".opus", ".webm", ".mp3", ".wav", ".m4a")):
            return True
        if content_type and content_type.split(";")[0].strip().lower() in SUPPORTED_CONTENT_TYPES:
            return True
        return False

    async def transcribe(self, url: str, filename: str) -> str | None:
        if not self.api_key:
            return None

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with session_scope(timeout=timeout, session=get_session()) as session:
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status != 200:
                        logger.warning("Voice fetch failed: %s", resp.status)
                        return None
                    data = await resp.read()

                if len(data) > WHISPER_MAX_BYTES:
                    logger.warning("Voice message too large for transcription")
                    return None

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
                    return text or None
        except Exception as e:
            logger.error("Transcription error: %s", e, exc_info=True)
            return None
