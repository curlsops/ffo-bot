import importlib.util
import logging

logger = logging.getLogger(__name__)

VOICE_DEPS_MISSING_USER_MSG = (
    "Voice is unavailable (missing davey). Rebuild the bot image or contact an administrator."
)


def discord_voice_dependencies_available() -> bool:
    return importlib.util.find_spec("davey") is not None


def log_voice_dependency_status() -> None:
    if discord_voice_dependencies_available():
        logger.info("davey loaded")
    else:
        logger.warning("davey not installed; voice commands will fail")
