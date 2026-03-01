"""Logging configuration."""

import logging
import sys

from pythonjsonlogger.json import JsonFormatter


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(log_level.upper())
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        handler.setFormatter(
            JsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(funcName)s %(lineno)d %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)8s] %(name)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
        )
    root.addHandler(handler)

    for name in ["discord", "discord.http", "discord.gateway", "aiohttp", "asyncpg"]:
        logging.getLogger(name).setLevel(logging.WARNING if name != "discord" else logging.INFO)

    return root
