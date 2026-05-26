import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from bot.utils.telemetry import TraceContextFilter

_BOT_LOGGER = "bot"

_THIRD_PARTY_VERBOSE = (
    "discord",
    "discord.http",
    "discord.gateway",
    "discord.voice_client",
    "discord.voice_state",
    "aiohttp",
    "mafic",
    "mafic.node",
    "mafic.player",
)

# asyncpg at INFO when root is DEBUG: query/parameter DEBUG is very noisy for troubleshooting.
_ASYNCPG_LOGGER = "asyncpg"

_OTEL_SDK_LOGGERS = (
    "opentelemetry",
    "opentelemetry.sdk",
    "opentelemetry.sdk.trace",
    "opentelemetry.exporter.otlp",
)


class _StructuredLogDefaultsFilter(logging.Filter):
    _OPTIONAL_FIELDS = ("feature", "command", "guild_id", "user_id", "interaction_id", "channel_id")

    def filter(self, record: logging.LogRecord) -> bool:
        for key in self._OPTIONAL_FIELDS:
            if not hasattr(record, key):
                setattr(record, key, "")
        return True


def _configure_bot_loggers(root_level: int) -> None:
    bot_logger = logging.getLogger(_BOT_LOGGER)
    if root_level <= logging.DEBUG:
        bot_logger.setLevel(logging.DEBUG)
    else:
        bot_logger.setLevel(logging.NOTSET)


def _configure_third_party_loggers(root_level: int, *, verbose: bool) -> None:
    if verbose:
        for name in _THIRD_PARTY_VERBOSE:
            logging.getLogger(name).setLevel(logging.DEBUG)
        logging.getLogger(_ASYNCPG_LOGGER).setLevel(logging.INFO)
        return
    for name in _THIRD_PARTY_VERBOSE:
        if name == "discord":
            logging.getLogger(name).setLevel(logging.INFO)
        else:
            logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger(_ASYNCPG_LOGGER).setLevel(logging.WARNING)


def _configure_otel_sdk_loggers(enabled: bool) -> None:
    level = logging.DEBUG if enabled else logging.WARNING
    for name in _OTEL_SDK_LOGGERS:
        logging.getLogger(name).setLevel(level)


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    *,
    log_verbose_third_party: bool | None = None,
    otel_tracing_enabled: bool = False,
) -> logging.Logger:
    root = logging.getLogger()
    level_name = log_level.upper()
    root.setLevel(level_name)
    root.handlers.clear()

    verbose_third = (
        log_verbose_third_party
        if log_verbose_third_party is not None
        else root.level <= logging.DEBUG
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(TraceContextFilter())
    handler.addFilter(_StructuredLogDefaultsFilter())
    if log_format == "json":
        handler.setFormatter(
            JsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(funcName)s %(lineno)d "
                "%(message)s %(trace_id)s %(span_id)s %(feature)s %(command)s "
                "%(guild_id)s %(user_id)s %(interaction_id)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)8s] %(name)s trace=%(trace_id)s span=%(span_id)s "
                "feature=%(feature)s command=%(command)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                defaults={
                    "trace_id": "",
                    "span_id": "",
                    "feature": "",
                    "command": "",
                },
            )
        )
    root.addHandler(handler)

    _configure_bot_loggers(root.level)
    _configure_third_party_loggers(root.level, verbose=verbose_third)
    _configure_otel_sdk_loggers(otel_tracing_enabled)
    return root
