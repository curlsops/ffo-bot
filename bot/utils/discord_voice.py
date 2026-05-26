import importlib.metadata
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
        try:
            version = importlib.metadata.version("davey")
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
        logger.info("Voice deps OK (davey %s)", version)
        logger.debug("Voice dependency check passed (davey %s)", version)
    else:
        logger.warning("Voice deps missing (davey not installed); voice commands will fail")
        logger.debug("Voice dependency check failed: davey package not importable")
