import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, cast

from bot.auth.permissions import PermissionContext
from bot.services.minecraft_rcon import WhitelistListMergeResult
from bot.utils.telemetry import trace_span
from config.constants import Constants, Role

if TYPE_CHECKING:
    from bot.cache.memory import InMemoryCache

logger = logging.getLogger(__name__)

_CACHE_KEY_WHITELIST = "whitelist_usernames:{server_id}"
_MOJANG_CACHE_KEY = "mojang:profile:{username}"
_MOJANG_CACHE_TTL = 300
_MOJANG_NOT_FOUND = object()


class RconPort(Protocol):  # pragma: no cover - structural typing only
    async def whitelist_add(self, username: str) -> str: ...

    async def whitelist_list_merge(self) -> WhitelistListMergeResult: ...


class MojangPort(Protocol):  # pragma: no cover - structural typing only
    async def get_profile(self, username: str) -> tuple[str, str] | None: ...

    async def get_profile_by_uuid(self, uuid_str: str) -> tuple[str, str] | None: ...

    async def get_profiles_batch(self, usernames: list[str]) -> dict[str, tuple[str, str]]: ...


class NotificationPort(Protocol):  # pragma: no cover - structural typing only
    async def notify_whitelist(
        self,
        server_id: int,
        action: str,
        changed_by_id: int,
        *,
        channel_id: int | None = None,
        username: str | None = None,
    ) -> bool: ...


class PermissionCheckPort(Protocol):  # pragma: no cover - structural typing only
    async def check_role(self, ctx: PermissionContext, required_role: Role) -> bool: ...


@dataclass(frozen=True)
class SyncFromRconResult:
    ok: bool
    player_count: int = 0
    reachable_targets: int = 0
    unreachable_target_ids: tuple[str, ...] = ()


class SubmissionOutcome(Enum):
    ACCEPTED = auto()
    INVALID_FORMAT = auto()
    NOT_FOUND = auto()


@dataclass(frozen=True)
class SubmissionResult:
    outcome: SubmissionOutcome
    username: str | None = None
    minecraft_uuid: str | None = None


class ResolutionOutcome(Enum):
    APPROVED = auto()
    APPROVE_FAILED = auto()
    REJECTED = auto()
    PERMISSION_DENIED = auto()
    NOT_APPLICABLE = auto()


@dataclass(frozen=True)
class ResolutionResult:
    outcome: ResolutionOutcome
    username: str | None = None
    author_id: int | None = None
    channel_id: int | None = None
    rcon_response: str | None = None
    error: str | None = None


class WhitelistService:
    APPROVE_EMOJI: ClassVar[str] = "✅"
    REJECT_EMOJI: ClassVar[str] = "❌"

    def __init__(
        self,
        db_pool,
        rcon: RconPort,
        mojang: MojangPort,
        cache: "InMemoryCache | None",
        notifier: NotificationPort,
        permission_checker: PermissionCheckPort,
        metrics: Any = None,
    ):
        self.db_pool = db_pool
        self.rcon = rcon
        self.mojang = mojang
        self.cache = cache
        self.notifier = notifier
        self.permission_checker = permission_checker
        self.metrics = metrics

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    async def submit_ign(
        self, *, server_id: int, channel_id: int, message_id: int, author_id: int, content: str
    ) -> SubmissionResult:
        with trace_span(
            "whitelist.submit_ign",
            feature="whitelist",
            attributes={
                "discord.guild_id": str(server_id),
                "discord.channel_id": str(channel_id),
            },
        ) as span:
            text = (content or "").strip()
            if not text or " " in text or not (3 <= len(text) <= 16):
                span.set_attribute("whitelist.outcome", "INVALID_FORMAT")
                return SubmissionResult(SubmissionOutcome.INVALID_FORMAT)
            if not text.replace("_", "").isalnum():
                span.set_attribute("whitelist.outcome", "INVALID_FORMAT")
                return SubmissionResult(SubmissionOutcome.INVALID_FORMAT)

            username = text
            span.set_attribute("whitelist.username", username)
            profile = await self._get_mojang_profile_cached(username)
            if not profile:
                span.set_attribute("whitelist.outcome", "NOT_FOUND")
                return SubmissionResult(SubmissionOutcome.NOT_FOUND, username=username)
            minecraft_uuid, _ = profile

            try:
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO whitelist_pending (server_id, message_id, channel_id, username, author_id, minecraft_uuid)
                        VALUES ($1, $2, $3, $4, $5, $6::uuid)
                        ON CONFLICT (server_id, message_id) DO NOTHING
                        """,
                        server_id,
                        message_id,
                        channel_id,
                        username,
                        author_id,
                        minecraft_uuid,
                    )
            except Exception as e:
                logger.error("Whitelist pending insert error: %s", e, exc_info=True)

            span.set_attribute("whitelist.outcome", "ACCEPTED")
            if self.metrics:
                self.metrics.whitelist_events_total.labels(event="submit", outcome="ACCEPTED").inc()
            return SubmissionResult(
                SubmissionOutcome.ACCEPTED, username=username, minecraft_uuid=minecraft_uuid
            )

    async def _get_mojang_profile_cached(self, username: str):
        key = _MOJANG_CACHE_KEY.format(username=username.lower())
        if self.cache:
            cached = self.cache.get(key)
            if cached is not None:
                return None if cached is _MOJANG_NOT_FOUND else cached
        profile = await self.mojang.get_profile(username)
        if self.cache:
            self.cache.set(
                key, _MOJANG_NOT_FOUND if profile is None else profile, ttl=_MOJANG_CACHE_TTL
            )
        return profile

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    async def resolve_reaction(
        self, *, server_id: int, message_id: int, moderator_id: int, emoji: str
    ) -> ResolutionResult:
        with trace_span(
            "whitelist.resolve_reaction",
            feature="whitelist",
            attributes={
                "discord.guild_id": str(server_id),
                "discord.message_id": str(message_id),
                "whitelist.emoji": emoji,
            },
        ) as span:
            if emoji not in (self.APPROVE_EMOJI, self.REJECT_EMOJI):
                span.set_attribute("whitelist.outcome", "NOT_APPLICABLE")
                return ResolutionResult(ResolutionOutcome.NOT_APPLICABLE)

            ctx = PermissionContext(
                server_id=server_id, user_id=moderator_id, command_name="whitelist_approve"
            )
            if not await self.permission_checker.check_role(ctx, Role.MODERATOR):
                span.set_attribute("whitelist.outcome", "PERMISSION_DENIED")
                return ResolutionResult(ResolutionOutcome.PERMISSION_DENIED)

            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    DELETE FROM whitelist_pending
                    WHERE server_id = $1 AND message_id = $2
                    RETURNING username, channel_id, author_id, minecraft_uuid
                    """,
                    server_id,
                    message_id,
                )
            if not row:
                span.set_attribute("whitelist.outcome", "NOT_APPLICABLE")
                return ResolutionResult(ResolutionOutcome.NOT_APPLICABLE)

            username = row["username"]
            channel_id = row["channel_id"]
            author_id = row["author_id"]
            span.set_attribute("whitelist.username", username)

            if emoji == self.REJECT_EMOJI:
                span.set_attribute("whitelist.outcome", "REJECTED")
                if self.metrics:
                    self.metrics.whitelist_events_total.labels(
                        event="reject", outcome="REJECTED"
                    ).inc()
                return ResolutionResult(
                    ResolutionOutcome.REJECTED,
                    username=username,
                    author_id=author_id,
                    channel_id=channel_id,
                )

            minecraft_uuid = row.get("minecraft_uuid")
            if minecraft_uuid is None:
                profile = await self.mojang.get_profile(username)
                minecraft_uuid = profile[0] if profile else None

            try:
                rcon_response = await self.rcon.whitelist_add(username)
            except Exception as e:
                logger.warning("RCON whitelist add on approve failed: %s", e)
                span.set_attribute("whitelist.outcome", "APPROVE_FAILED")
                if self.metrics:
                    self.metrics.whitelist_events_total.labels(
                        event="approve", outcome="APPROVE_FAILED"
                    ).inc()
                return ResolutionResult(
                    ResolutionOutcome.APPROVE_FAILED,
                    username=username,
                    author_id=author_id,
                    channel_id=channel_id,
                    error=str(e),
                )

            await self.add_to_cache(
                server_id,
                username,
                added_by=moderator_id,
                minecraft_uuid=str(minecraft_uuid) if minecraft_uuid else None,
            )
            await self.notifier.notify_whitelist(
                server_id, "Approve", moderator_id, username=username
            )

            span.set_attribute("whitelist.outcome", "APPROVED")
            if self.metrics:
                self.metrics.whitelist_events_total.labels(
                    event="approve", outcome="APPROVED"
                ).inc()
            return ResolutionResult(
                ResolutionOutcome.APPROVED,
                username=username,
                author_id=author_id,
                channel_id=channel_id,
                rcon_response=rcon_response,
            )

    # ------------------------------------------------------------------
    # Moderation-Ops persistence (absorbed from bot/utils/whitelist_cache.py)
    # ------------------------------------------------------------------

    def _invalidate_whitelist_cache(self, server_id: int) -> None:
        if self.cache:
            self.cache.delete(_CACHE_KEY_WHITELIST.format(server_id=server_id))

    async def get_cached_usernames(self, server_id: int) -> list[str]:
        if self.cache:
            cached = self.cache.get(_CACHE_KEY_WHITELIST.format(server_id=server_id))
            if cached is not None:
                return cast(list[str], cached)
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT username FROM whitelist_cache WHERE server_id = $1 ORDER BY username",
                    server_id,
                )
            result = [r["username"] for r in rows]
            if self.cache:
                self.cache.set(
                    _CACHE_KEY_WHITELIST.format(server_id=server_id),
                    result,
                    ttl=Constants.CACHE_TTL,
                )
            return result
        except Exception as e:
            logger.warning("Failed to get whitelist cache: %s", e)
            return []

    async def add_to_cache(
        self,
        server_id: int,
        username: str,
        *,
        added_by: int | None = None,
        minecraft_uuid: str | None = None,
    ) -> None:
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO whitelist_cache (server_id, username, added_by, minecraft_uuid)
                    VALUES ($1, $2, $3, $4::uuid)
                    ON CONFLICT (server_id, username) DO UPDATE
                    SET added_by = EXCLUDED.added_by, added_at = NOW(),
                        minecraft_uuid = COALESCE(EXCLUDED.minecraft_uuid, whitelist_cache.minecraft_uuid)
                    """,
                    server_id,
                    username,
                    added_by,
                    minecraft_uuid,
                )
            self._invalidate_whitelist_cache(server_id)
        except Exception as e:
            logger.warning("Failed to add to whitelist cache: %s", e)

    async def get_cache_entry(self, server_id: int, username: str) -> dict[str, Any] | None:
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT username, minecraft_uuid FROM whitelist_cache
                    WHERE server_id = $1 AND username = $2
                    """,
                    server_id,
                    username,
                )
            if not row:
                return None
            mu = row["minecraft_uuid"]
            return {
                "username": row["username"],
                "minecraft_uuid": str(mu) if mu is not None else None,
            }
        except Exception as e:
            logger.warning("Failed to fetch whitelist cache entry: %s", e)
            return None

    async def remove_from_cache(self, server_id: int, username: str) -> None:
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM whitelist_cache WHERE server_id = $1 AND username = $2",
                    server_id,
                    username,
                )
            self._invalidate_whitelist_cache(server_id)
        except Exception as e:
            logger.warning("Failed to remove from whitelist cache: %s", e)

    async def reconcile_whitelist_cache(self, server_id: int) -> dict[str, list]:
        with trace_span(
            "whitelist.reconcile_cache",
            feature="whitelist",
            attributes={"discord.guild_id": str(server_id)},
        ) as span:
            updated: list[str] = []
            uuid_filled: list[str] = []
            pruned: list[str] = []
            try:
                async with self.db_pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT username, minecraft_uuid FROM whitelist_cache
                        WHERE server_id = $1 ORDER BY username
                        """,
                        server_id,
                    )
                for row in rows:
                    un = row["username"]
                    mu = row["minecraft_uuid"]
                    str_uuid = str(mu) if mu is not None else None
                    if str_uuid:
                        prof = await self.mojang.get_profile_by_uuid(str_uuid)
                        if not prof:
                            continue
                        _, current = prof
                        if current != un:
                            async with self.db_pool.acquire() as conn:
                                await conn.execute(
                                    """
                                    INSERT INTO whitelist_cache (server_id, username, minecraft_uuid)
                                    VALUES ($1, $2, $3::uuid)
                                    ON CONFLICT (server_id, username) DO UPDATE SET
                                        minecraft_uuid = EXCLUDED.minecraft_uuid
                                    """,
                                    server_id,
                                    current,
                                    prof[0],
                                )
                                await conn.execute(
                                    """
                                    DELETE FROM whitelist_cache
                                    WHERE server_id = $1 AND username = $2
                                    """,
                                    server_id,
                                    un,
                                )
                            updated.append(f"{un} → {current}")
                        continue
                    prof = await self.mojang.get_profile(un)
                    if prof:
                        uu, canonical = prof[0], prof[1]
                        if canonical.lower() != un.lower():
                            async with self.db_pool.acquire() as conn:
                                await conn.execute(
                                    """
                                    INSERT INTO whitelist_cache (server_id, username, minecraft_uuid)
                                    VALUES ($1, $2, $3::uuid)
                                    ON CONFLICT (server_id, username) DO UPDATE SET
                                        minecraft_uuid = EXCLUDED.minecraft_uuid
                                    """,
                                    server_id,
                                    canonical,
                                    uu,
                                )
                                await conn.execute(
                                    """
                                    DELETE FROM whitelist_cache
                                    WHERE server_id = $1 AND username = $2
                                    """,
                                    server_id,
                                    un,
                                )
                            updated.append(f"{un} → {canonical}")
                        else:
                            async with self.db_pool.acquire() as conn:
                                await conn.execute(
                                    """
                                    UPDATE whitelist_cache SET minecraft_uuid = $1::uuid
                                    WHERE server_id = $2 AND username = $3
                                    """,
                                    uu,
                                    server_id,
                                    un,
                                )
                            uuid_filled.append(un)
                    else:
                        async with self.db_pool.acquire() as conn:
                            await conn.execute(
                                """
                                DELETE FROM whitelist_cache
                                WHERE server_id = $1 AND username = $2
                                """,
                                server_id,
                                un,
                            )
                        pruned.append(un)
                self._invalidate_whitelist_cache(server_id)
            except Exception as e:
                logger.warning("whitelist cache reconcile failed: %s", e)
            span.set_attribute("whitelist.updated_count", len(updated))
            span.set_attribute("whitelist.pruned_count", len(pruned))
            span.set_attribute("whitelist.uuid_filled_count", len(uuid_filled))
            return {"updated": updated, "uuid_filled": uuid_filled, "pruned": pruned}

    async def sync_from_rcon(self, server_id: int) -> SyncFromRconResult:
        with trace_span(
            "whitelist.sync_from_rcon",
            feature="whitelist",
            attributes={"discord.guild_id": str(server_id)},
        ) as span:
            result = await self._sync_from_rcon_impl(server_id)
            if result.ok:
                span.set_attribute("whitelist.player_count", result.player_count)
                span.set_attribute("whitelist.reachable_targets", result.reachable_targets)
            return result

    async def _sync_from_rcon_impl(self, server_id: int) -> SyncFromRconResult:
        try:
            merge = await self.rcon.whitelist_list_merge()
        except Exception as e:
            logger.warning("Failed to sync whitelist from RCON: %s", e)
            return SyncFromRconResult(ok=False)
        if not merge.reachable_target_ids:
            logger.warning(
                "Failed to sync whitelist from RCON: no reachable RCON targets (unreachable=%s)",
                (
                    ",".join(merge.unreachable_target_ids)
                    if merge.unreachable_target_ids
                    else "(none)"
                ),
            )
            return SyncFromRconResult(
                ok=False,
                unreachable_target_ids=merge.unreachable_target_ids,
            )
        usernames = merge.usernames

        try:
            uuid_map: dict[str, str] = {}
            try:
                profiles = await self.mojang.get_profiles_batch(usernames)
                uuid_map = {name: profile[0] for name, profile in profiles.items()}
                logger.debug("Batch fetched %d/%d UUIDs", len(uuid_map), len(usernames))
            except Exception as e:
                logger.warning("Batch UUID fetch failed: %s", e)

            async with self.db_pool.acquire() as conn:
                await conn.execute("DELETE FROM whitelist_cache WHERE server_id = $1", server_id)
                if usernames:
                    rows = [
                        (server_id, username, uuid_map.get(username.lower()))
                        for username in usernames
                    ]
                    await conn.executemany(
                        """
                        INSERT INTO whitelist_cache (server_id, username, minecraft_uuid)
                        VALUES ($1, $2, $3::uuid)
                        """,
                        rows,
                    )
            self._invalidate_whitelist_cache(server_id)
            return SyncFromRconResult(
                ok=True,
                player_count=len(usernames),
                reachable_targets=len(merge.reachable_target_ids),
                unreachable_target_ids=merge.unreachable_target_ids,
            )
        except Exception as e:
            logger.warning("Failed to sync whitelist from RCON: %s", e)
            return SyncFromRconResult(
                ok=False,
                unreachable_target_ids=merge.unreachable_target_ids,
            )
