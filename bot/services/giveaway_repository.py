import logging
import uuid
from datetime import datetime
from typing import Any
from weakref import WeakKeyDictionary

from bot.utils.db import cached_or_fallback

logger = logging.getLogger(__name__)

_GIVEAWAY_COLUMNS = (
    "id, server_id, channel_id, message_id, host_id, donor_id, prize, winners_count, "
    "ends_at, started_at, ended_at, required_roles, blacklist_roles, bypass_roles, "
    "bonus_roles, message_req, no_donor_win, no_defaults, ping, extra_text, image_url, "
    "is_active, created_at, updated_at"
)


class GiveawayRepository:
    """Persistence for giveaways, bound to a db_pool (and optionally a cache).

    Mirrors WhitelistService's shape: a db_pool/cache pair bound once at
    construction instead of threaded through every call.
    """

    def __init__(self, db_pool, cache=None):
        self.db_pool = db_pool
        self.cache = cache

    async def insert_giveaway(
        self,
        *,
        id: uuid.UUID,
        server_id: int,
        channel_id: int,
        host_id: int,
        donor_id: int | None,
        prize: str,
        winners_count: int,
        ends_at: datetime,
        required_roles: list[int],
        blacklist_roles: list[int],
        bypass_roles: list[int],
        bonus_roles: dict[str, int],
        message_req: dict[str, Any] | None,
        no_donor_win: bool,
        no_defaults: bool,
        ping: bool,
        extra_text: str | None,
        image_url: str | None,
    ) -> None:
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO giveaways (id, server_id, channel_id, host_id, donor_id,
                   prize, winners_count, ends_at, required_roles, blacklist_roles,
                   bypass_roles, bonus_roles, message_req, no_donor_win, no_defaults,
                   ping, extra_text, image_url)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)""",
                id,
                server_id,
                channel_id,
                host_id,
                donor_id,
                prize,
                winners_count,
                ends_at,
                required_roles,
                blacklist_roles,
                bypass_roles,
                bonus_roles,
                message_req,
                no_donor_win,
                no_defaults,
                ping,
                extra_text,
                image_url,
            )

    async def set_message_id(self, giveaway_id: uuid.UUID, message_id: int) -> None:
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE giveaways SET message_id = $1 WHERE id = $2", message_id, giveaway_id
            )

    async def fetch_by_message_id(self, message_id: int, cache=None) -> dict | None:
        async def fetch():
            async with self.db_pool.acquire() as conn:
                return await conn.fetchrow(
                    "SELECT " + _GIVEAWAY_COLUMNS + " FROM giveaways WHERE message_id = $1",
                    message_id,
                )

        row = await cached_or_fallback(
            cache, f"giveaway:msg:{message_id}", fetch, 300, lambda r: dict(r) if r else None
        )
        return dict(row) if row else None

    async def fetch_by_id(self, giveaway_id: uuid.UUID) -> dict | None:
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT " + _GIVEAWAY_COLUMNS + " FROM giveaways WHERE id = $1", giveaway_id
            )
        return dict(row) if row else None

    async def fetch_expired(self, before: datetime) -> list[dict]:
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT "
                + _GIVEAWAY_COLUMNS
                + " FROM giveaways WHERE is_active = true AND ends_at <= $1",
                before,
            )
        return [dict(r) for r in rows]

    async def mark_ended(
        self,
        giveaway_id: uuid.UUID,
        ended_at: datetime,
        cache=None,
        message_id: int | None = None,
    ) -> None:
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE giveaways SET is_active = false, ended_at = $1 WHERE id = $2",
                ended_at,
                giveaway_id,
            )
        if cache and message_id is not None:
            cache.delete(f"giveaway:msg:{message_id}")

    async def fetch_entries(self, giveaway_id: uuid.UUID, cache=None) -> list[dict]:
        async def fetch():
            async with self.db_pool.acquire() as conn:
                return await conn.fetch(
                    "SELECT user_id, entries FROM giveaway_entries WHERE giveaway_id = $1 ORDER BY created_at",
                    giveaway_id,
                )

        rows = await cached_or_fallback(
            cache,
            f"giveaway:entries:{giveaway_id}",
            fetch,
            60,
            lambda r: [dict(x) for x in r],
        )
        return [dict(r) for r in rows]

    async def fetch_winner_ids(self, giveaway_id: uuid.UUID) -> set[int]:
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id FROM giveaway_entries WHERE giveaway_id = $1 AND is_winner = true",
                giveaway_id,
            )
        return {r["user_id"] for r in rows}

    async def add_entry(
        self, giveaway_id: uuid.UUID, user_id: int, entries: int, cache=None
    ) -> bool:
        async with self.db_pool.acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO giveaway_entries (giveaway_id, user_id, entries) VALUES ($1,$2,$3)",
                    giveaway_id,
                    user_id,
                    entries,
                )
            except Exception as e:
                logger.debug("Add entry failed: %s", e)
                return False
        if cache:
            cache.delete(f"giveaway:entries:{giveaway_id}")
        return True

    async def remove_entry(self, giveaway_id: uuid.UUID, user_id: int, cache=None) -> bool:
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM giveaway_entries WHERE giveaway_id = $1 AND user_id = $2",
                giveaway_id,
                user_id,
            )
        removed = bool(result) and "DELETE 1" in result
        if removed and cache:
            cache.delete(f"giveaway:entries:{giveaway_id}")
        return removed

    async def set_winners(self, giveaway_id: uuid.UUID, winner_ids: set[int]) -> None:
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE giveaway_entries SET is_winner = false WHERE giveaway_id = $1",
                giveaway_id,
            )
            if winner_ids:
                await conn.executemany(
                    "UPDATE giveaway_entries SET is_winner = true WHERE giveaway_id = $1 AND user_id = $2",
                    [(giveaway_id, w) for w in winner_ids],
                )

    async def count_entries(self, giveaway_id: uuid.UUID) -> int:
        async with self.db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = $1", giveaway_id
            )
        return count or 0

    async def fetch_recent_for_autocomplete(self, server_id: int) -> list[dict]:
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT message_id, prize, ended_at
                FROM giveaways
                WHERE server_id = $1 AND message_id IS NOT NULL
                ORDER BY ended_at DESC NULLS FIRST
                LIMIT 25
                """,
                server_id,
            )
        return [dict(r) for r in rows]


_repository_registry: "WeakKeyDictionary[object, GiveawayRepository]" = WeakKeyDictionary()


def get_repository(bot) -> GiveawayRepository:
    """Return the GiveawayRepository bound to this bot, constructing it on first use.

    Mirrors bot/views/giveaway.py's _get_scheduler per-bot registry pattern.
    """
    repository = _repository_registry.get(bot)
    if repository is None:
        repository = GiveawayRepository(bot.db_pool, bot.cache)
        _repository_registry[bot] = repository
    return repository
