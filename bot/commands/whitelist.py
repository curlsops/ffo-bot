import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.command_helpers import require_admin, require_mod, require_rcon
from bot.services.minecraft_rcon import MinecraftRCONError, parse_whitelist_list_response
from bot.services.mojang import get_profile, get_profile_by_uuid, get_profiles_batch
from bot.utils.pagination import ListPaginatedView, truncate_for_discord
from bot.utils.whitelist_cache import (
    add_to_cache,
    get_cache_entry,
    get_cached_usernames,
    reconcile_whitelist_cache,
    remove_from_cache,
    sync_from_rcon,
)
from bot.utils.whitelist_channel import get_whitelist_channel_id, set_whitelist_channel

logger = logging.getLogger(__name__)

WHITELIST_APPROVE_EMOJI = "\u2705"
WHITELIST_REJECT_EMOJI = "\u274c"

OPERATION_CHOICES = [
    app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="ClearChannel", value="clear_channel"),
    app_commands.Choice(name="List", value="list"),
    app_commands.Choice(name="Off", value="off"),
    app_commands.Choice(name="On", value="on"),
    app_commands.Choice(name="Push", value="push"),
    app_commands.Choice(name="Repair", value="repair"),
    app_commands.Choice(name="Remove", value="remove"),
    app_commands.Choice(name="Set", value="set"),
    app_commands.Choice(name="Sync", value="sync"),
]

TOGGLE_OPERATIONS = {"off", "on"}
MODERATION_OPERATIONS = {"add", "list", "push", "repair", "remove", "sync"}


async def _whitelist_username_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not interaction.guild_id:
        return []
    bot = interaction.client
    if not bot.minecraft_rcon:
        return []
    usernames = await get_cached_usernames(bot.db_pool, interaction.guild_id, cache=bot.cache)
    if not usernames and bot.minecraft_rcon._is_configured():
        await sync_from_rcon(
            bot.db_pool,
            interaction.guild_id,
            bot.minecraft_rcon,
            batch_fetch=get_profiles_batch,
            cache=bot.cache,
        )
        usernames = await get_cached_usernames(bot.db_pool, interaction.guild_id, cache=bot.cache)
    cur = current.lower()
    choices = [
        app_commands.Choice(name=u, value=u) for u in usernames if not cur or cur in u.lower()
    ]
    return choices[:25]


def _validate_username(username: str) -> str | None:
    s = username.strip()
    if not (3 <= len(s) <= 16):
        return None
    return s if s.replace("_", "").isalnum() else None


def _rcon_remove_sounds_failed(resp: str) -> bool:
    s = (resp or "").lower()
    return any(
        phrase in s
        for phrase in (
            "not whitelisted",
            "isn't whitelisted",
            "nothing changed",
            "unknown player",
            "cannot find",
            "no player",
            "is not on the whitelist",
            "that player isn't",
        )
    )


def _whitelist_command(cog: "WhitelistCommands"):
    @app_commands.command(
        name="whitelist",
        description="Minecraft whitelist management. Provide operation and/or channel.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        operation="Add, ClearChannel, List, Off, On, Push, Repair, Remove, Set, Sync",
        username="Minecraft username (Add/Remove only)",
        channel="Channel for IGN posts (admin; required for Set, omit with ClearChannel to disable)",
    )
    @app_commands.choices(operation=OPERATION_CHOICES)
    @app_commands.autocomplete(username=_whitelist_username_autocomplete)
    async def whitelist_cmd(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str] | None = None,
        username: str | None = None,
        channel: discord.TextChannel | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        await cog.dispatch_whitelist(
            interaction,
            operation=operation,
            username=username,
            channel=channel,
        )

    return whitelist_cmd


class WhitelistCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.whitelist_cmd = _whitelist_command(self)

    async def dispatch_whitelist(
        self,
        interaction: discord.Interaction,
        operation: app_commands.Choice[str] | None = None,
        username: str | None = None,
        channel: discord.TextChannel | None = None,
    ):
        op = operation.value if operation is not None else None

        if channel is not None or op == "set":
            await self._handle_channel_set(interaction, channel)
            return

        if op is None:
            await interaction.followup.send(
                "Provide operation (Add, ClearChannel, List, Off, On, Push, Repair, Remove, Set, Sync) "
                "or channel to set.",
                ephemeral=True,
            )
            return

        if op == "clear_channel":
            await self._handle_channel_clear(interaction)
            return

        if op in TOGGLE_OPERATIONS:
            await self._dispatch_toggle_operation(interaction, op)
            return

        if op in MODERATION_OPERATIONS:
            await self._dispatch_moderation_operation(interaction, op, username)
            return

        await interaction.followup.send("Unknown operation.", ephemeral=True)

    async def _dispatch_toggle_operation(self, interaction: discord.Interaction, op: str):
        if not await require_admin(interaction, "whitelist", self.bot):
            return
        if not await require_rcon(interaction, self.bot):
            return
        await self._handle_whitelist_toggle(interaction, op)

    async def _dispatch_moderation_operation(
        self, interaction: discord.Interaction, op: str, username: str | None
    ):
        if not await require_mod(interaction, "whitelist", self.bot):
            return
        if not await require_rcon(interaction, self.bot):
            return
        if op == "add":
            await self._handle_add(interaction, username)
        elif op == "remove":
            await self._handle_remove(interaction, username)
        elif op == "list":
            await self._handle_list(interaction)
        elif op == "push":
            await self._handle_push(interaction)
        elif op == "repair":
            await self._handle_repair(interaction)
        else:
            await self._handle_sync(interaction)

    async def _handle_channel_set(
        self, interaction: discord.Interaction, channel: discord.TextChannel | None
    ):
        if channel is None:
            await interaction.followup.send(
                "Channel required for Set (e.g. operation:Set channel:#whitelist).",
                ephemeral=True,
            )
            return
        if not await require_admin(interaction, "whitelist channel", self.bot):
            return
        await self.bot._register_server(interaction.guild)
        new_channel_id = channel.id
        current_id = await get_whitelist_channel_id(
            self.bot.db_pool, interaction.guild_id, cache=self.bot.cache
        )
        if current_id == new_channel_id:
            await interaction.followup.send(
                f"Whitelist channel is already set to {channel.mention}."
            )
            return
        success = await set_whitelist_channel(
            self.bot.db_pool,
            interaction.guild_id,
            new_channel_id,
            cache=self.bot.cache,
        )
        if not success:
            await interaction.followup.send("Failed to update whitelist channel.")
            return
        if self.bot.notifier and self.bot.settings.feature_notify_moderation:
            await self.bot.notifier.notify_whitelist(
                interaction.guild_id,
                "Channel Set",
                interaction.user.id,
                channel_id=new_channel_id,
            )
        await interaction.followup.send(
            f"Whitelist channel set to {channel.mention}. "
            "Users should post only their Minecraft IGN (one per message)."
        )

    async def _handle_channel_clear(self, interaction: discord.Interaction):
        if not await require_admin(interaction, "whitelist channel", self.bot):
            return
        current_id = await get_whitelist_channel_id(
            self.bot.db_pool, interaction.guild_id, cache=self.bot.cache
        )
        if current_id is None:
            await interaction.followup.send("Whitelist channel is already disabled.")
            return
        success = await set_whitelist_channel(
            self.bot.db_pool,
            interaction.guild_id,
            None,
            cache=self.bot.cache,
        )
        if not success:
            await interaction.followup.send("Failed to update whitelist channel.")
            return
        if self.bot.notifier and self.bot.settings.feature_notify_moderation:
            await self.bot.notifier.notify_whitelist(
                interaction.guild_id,
                "Channel Cleared",
                interaction.user.id,
            )
        await interaction.followup.send("Whitelist channel disabled.")

    async def _handle_whitelist_toggle(self, interaction: discord.Interaction, op: str):
        try:
            if op == "on":
                resp = await self.bot.minecraft_rcon.whitelist_on()
            else:
                resp = await self.bot.minecraft_rcon.whitelist_off()
            if self.bot.notifier and self.bot.settings.feature_notify_moderation:
                action = "Enabled" if op == "on" else "Disabled"
                await self.bot.notifier.notify_whitelist(
                    interaction.guild_id, action, interaction.user.id
                )
            await interaction.followup.send(f"Whitelist: {resp}", ephemeral=True)
        except MinecraftRCONError as e:
            logger.warning("RCON whitelist %s failed: %s", op, e)
            await interaction.followup.send(
                "Could not connect to the Minecraft server. Check RCON configuration.",
                ephemeral=True,
            )

    async def _handle_add(self, interaction: discord.Interaction, username: str | None):
        if not username:
            await interaction.followup.send(
                "Username required for Add (e.g. operation:Add username:Steve).",
                ephemeral=True,
            )
            return
        valid = _validate_username(username)
        if not valid:
            await interaction.followup.send(
                "Invalid username. Must be 3-16 characters, alphanumeric and underscores only.",
                ephemeral=True,
            )
            return
        try:
            resp = await self.bot.minecraft_rcon.whitelist_add(valid)
            profile = await get_profile(valid)
            minecraft_uuid = profile[0] if profile else None
            await add_to_cache(
                self.bot.db_pool,
                interaction.guild_id,
                valid,
                added_by=interaction.user.id,
                minecraft_uuid=minecraft_uuid,
                cache=self.bot.cache,
            )
            if self.bot.notifier and self.bot.settings.feature_notify_moderation:
                await self.bot.notifier.notify_whitelist(
                    interaction.guild_id,
                    "Add",
                    interaction.user.id,
                    username=valid,
                )
            await interaction.followup.send(f"Whitelist: {resp}", ephemeral=True)
        except MinecraftRCONError as e:
            logger.warning("RCON whitelist add failed: %s", e)
            await interaction.followup.send(
                "Could not connect to the Minecraft server. Check RCON configuration.",
                ephemeral=True,
            )

    async def _handle_list(self, interaction: discord.Interaction):
        try:
            resp = await self.bot.minecraft_rcon.whitelist_list()
            usernames = parse_whitelist_list_response(resp)
            if not usernames:
                await interaction.followup.send("Whitelist: (empty)", ephemeral=True)
                return

            def fmt(u):
                return f"• {u}"

            view = ListPaginatedView(usernames, "**Whitelisted players:**", fmt)
            await interaction.followup.send(
                view._format_page(),
                view=view,
                ephemeral=True,
            )
        except MinecraftRCONError as e:
            logger.warning("RCON whitelist list failed: %s", e)
            await interaction.followup.send(
                "Could not connect to the Minecraft server. Check RCON configuration.",
                ephemeral=True,
            )

    async def _handle_sync(self, interaction: discord.Interaction):
        success = await sync_from_rcon(
            self.bot.db_pool,
            interaction.guild_id,
            self.bot.minecraft_rcon,
            batch_fetch=get_profiles_batch,
            cache=self.bot.cache,
        )
        if success:
            count = len(
                await get_cached_usernames(
                    self.bot.db_pool, interaction.guild_id, cache=self.bot.cache
                )
            )
            await interaction.followup.send(
                f"Synced {count} players from Minecraft server.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "Failed to sync from Minecraft server.",
                ephemeral=True,
            )

    async def _handle_push(self, interaction: discord.Interaction):
        master = await get_cached_usernames(
            self.bot.db_pool, interaction.guild_id, cache=self.bot.cache
        )
        if not master:
            await interaction.followup.send(
                "Whitelist cache is empty. Approve IGN posts or use Add.",
                ephemeral=True,
            )
            return
        try:
            results = await self.bot.minecraft_rcon.push_master_whitelist(master)
        except MinecraftRCONError as e:
            logger.warning("RCON push master failed: %s", e)
            await interaction.followup.send(
                "Could not push to Minecraft servers. Check RCON configuration.",
                ephemeral=True,
            )
            return
        lines = []
        for tr in results:
            if tr.error:
                lines.append(f"**{tr.target_id}**: error: {tr.error}")
            else:
                lines.append(
                    f"**{tr.target_id}**: +{len(tr.added)} added, −{len(tr.removed)} removed"
                )
        summary = truncate_for_discord("\n".join(lines))
        if self.bot.notifier and self.bot.settings.feature_notify_moderation:
            await self.bot.notifier.notify_whitelist(
                interaction.guild_id,
                "Push",
                interaction.user.id,
            )
        await interaction.followup.send(summary, ephemeral=True)

    async def _handle_repair(self, interaction: discord.Interaction):
        summary = await reconcile_whitelist_cache(
            self.bot.db_pool, interaction.guild_id, cache=self.bot.cache
        )
        lines: list[str] = []
        if summary["updated"]:
            lines.append(
                "Renamed in cache (Mojang): "
                + ", ".join(summary["updated"][:40])
                + (" …" if len(summary["updated"]) > 40 else "")
            )
        if summary["uuid_filled"]:
            lines.append(f"UUID saved for {len(summary['uuid_filled'])} account(s).")
        if summary["pruned"]:
            lines.append(
                "Removed stale names (no Mojang profile): "
                + ", ".join(summary["pruned"][:40])
                + (" …" if len(summary["pruned"]) > 40 else "")
            )
        if not lines:
            lines.append(
                "No cache changes (entries match Mojang UUID lookup, or APIs did not respond)."
            )
        msg = truncate_for_discord("\n".join(lines))
        if self.bot.notifier and self.bot.settings.feature_notify_moderation:
            await self.bot.notifier.notify_whitelist(
                interaction.guild_id,
                "Repair",
                interaction.user.id,
            )
        await interaction.followup.send(msg, ephemeral=True)

    async def _handle_remove(self, interaction: discord.Interaction, username: str | None):
        if not username:
            await interaction.followup.send(
                "Username required for Remove (e.g. operation:Remove username:Steve).",
                ephemeral=True,
            )
            return
        valid = _validate_username(username)
        if not valid:
            await interaction.followup.send(
                "Invalid username. Must be 3-16 characters, alphanumeric and underscores only.",
                ephemeral=True,
            )
            return
        try:
            resp = await self.bot.minecraft_rcon.whitelist_remove(valid)
            if _rcon_remove_sounds_failed(resp):
                entry = await get_cache_entry(self.bot.db_pool, interaction.guild_id, valid)
                uid = entry.get("minecraft_uuid") if entry else None
                if uid:
                    prof = await get_profile_by_uuid(uid)
                    if prof and prof[1].lower() != valid.lower():
                        resp = await self.bot.minecraft_rcon.whitelist_remove(prof[1])
            if _rcon_remove_sounds_failed(resp):
                await interaction.followup.send(
                    "Could not remove that name on the server (it may be outdated after a "
                    "Mojang rename). Try **Repair**, then Remove again with the updated name, "
                    f"or Sync from RCON. Last response: {resp[:300]}",
                    ephemeral=True,
                )
                return
            await remove_from_cache(
                self.bot.db_pool, interaction.guild_id, valid, cache=self.bot.cache
            )
            if self.bot.notifier and self.bot.settings.feature_notify_moderation:
                await self.bot.notifier.notify_whitelist(
                    interaction.guild_id,
                    "Remove",
                    interaction.user.id,
                    username=valid,
                )
            await interaction.followup.send(f"Whitelist: {resp}", ephemeral=True)
        except MinecraftRCONError as e:
            logger.warning("RCON whitelist remove failed: %s", e)
            await interaction.followup.send(
                "Could not connect to the Minecraft server. Check RCON configuration.",
                ephemeral=True,
            )

    async def cog_load(self):
        self.bot.tree.add_command(self.whitelist_cmd)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.whitelist_cmd.name)


async def setup(bot):
    await bot.add_cog(WhitelistCommands(bot))
