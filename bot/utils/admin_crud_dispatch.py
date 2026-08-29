from collections.abc import Awaitable, Callable

import discord

OperationHandlers = dict[str, Callable[[], Awaitable[None]]]


async def dispatch_operation(
    interaction: discord.Interaction,
    operation: str,
    handlers: OperationHandlers,
    *,
    ephemeral: bool = True,
) -> None:
    await interaction.response.defer(ephemeral=ephemeral)
    handler = handlers.get(operation)
    if handler is not None:
        await handler()
