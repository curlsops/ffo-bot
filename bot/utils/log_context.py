from __future__ import annotations

import logging
from typing import Any

import discord

from bot.utils.telemetry import feature_debug, logging_extra, span_context_fields


def trace_fields_for_log() -> dict[str, str]:
    return span_context_fields()


def log_debug(logger: logging.Logger, msg: str, *args: object, **fields: Any) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return
    logger.debug(msg, *args, extra=logging_extra(**fields))


def interaction_log_fields(interaction: discord.Interaction) -> dict[str, Any]:
    user = interaction.user
    return {
        "guild_id": interaction.guild_id,
        "user_id": user.id if user else None,
        "interaction_id": interaction.id,
        "channel_id": interaction.channel_id,
    }


def log_command_start(
    logger: logging.Logger,
    feature: str,
    command: str,
    interaction: discord.Interaction,
) -> None:
    fields = interaction_log_fields(interaction)
    logger.info(
        "%s start guild=%s user=%s interaction=%s",
        command,
        fields.get("guild_id"),
        fields.get("user_id"),
        fields.get("interaction_id"),
        extra=logging_extra(feature=feature, command=command, **fields),
    )
    feature_debug(logger, feature, "%s deferred", command, command=command, **fields)
