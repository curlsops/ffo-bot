from __future__ import annotations

import discord


async def send_ephemeral(interaction: discord.Interaction, content: str, **kwargs) -> None:
    fn = (
        interaction.followup.send
        if interaction.response.is_done()
        else interaction.response.send_message
    )
    await fn(content, ephemeral=True, **kwargs)
