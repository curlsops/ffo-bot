from config.constants import Constants

CACHE_QUOTE_AUTOCOMPLETE = "quotebook_autocomplete:{server_id}"
CACHE_QUOTE_APPROVE_AUTOCOMPLETE = "quotebook_approve_autocomplete:{server_id}"
CACHE_QUOTE_PENDING = "quotebook_pending:{server_id}"
CACHE_QUOTE_APPROVED = "quotebook_approved:{server_id}"


class QuotebookService:
    """Persistence and caching policy for the quotebook, bound to a db_pool.

    Cache is passed per-call (not bound at construction) since callers may
    reassign bot.cache after the service is already constructed.
    """

    def __init__(self, db_pool):
        self.db_pool = db_pool

    def _invalidate(self, cache, server_id: int) -> None:
        if cache:
            for key in (
                CACHE_QUOTE_AUTOCOMPLETE,
                CACHE_QUOTE_APPROVE_AUTOCOMPLETE,
                CACHE_QUOTE_PENDING,
                CACHE_QUOTE_APPROVED,
            ):
                cache.delete(key.format(server_id=server_id))

    async def list_quote_ids(self, server_id: int) -> list:
        async with self.db_pool.acquire() as conn:
            rows: list = await conn.fetch(
                """
                SELECT id, quote_text, approved
                FROM quotebook
                WHERE server_id = $1
                ORDER BY approved, created_at DESC
                LIMIT 25
                """,
                server_id,
            )
        return rows

    async def list_all_quotes(self, server_id: int) -> list[dict]:
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, quote_text, attribution, approved
                FROM quotebook
                WHERE server_id = $1
                ORDER BY approved, created_at DESC
                """,
                server_id,
            )
        return [dict(r) for r in rows]

    async def submit_quote(
        self, server_id: int, text: str, submitter_id: int, attribution: str | None, cache=None
    ) -> str:
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO quotebook (server_id, quote_text, submitter_id, attribution, approved)
                VALUES ($1, $2, $3, $4, false)
                RETURNING id
                """,
                server_id,
                text,
                submitter_id,
                attribution,
            )
        self._invalidate(cache, server_id)
        return str(row["id"])

    async def approve_quote(self, quote_id, server_id: int, cache=None) -> dict | None:
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE quotebook SET approved = true, updated_at = NOW()
                WHERE id = $1 AND server_id = $2 AND approved = false
                RETURNING quote_text, attribution
                """,
                quote_id,
                server_id,
            )
        if row is None:
            return None
        self._invalidate(cache, server_id)
        return dict(row)

    async def delete_quote(self, quote_id, server_id: int, cache=None) -> None:
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM quotebook WHERE id = $1 AND server_id = $2",
                quote_id,
                server_id,
            )
        self._invalidate(cache, server_id)

    async def fetch_approved_quotes(self, server_id: int, cache=None) -> list[dict]:
        cache_key = CACHE_QUOTE_APPROVED.format(server_id=server_id)
        rows = cache.get(cache_key) if cache else None
        if rows is None:
            async with self.db_pool.acquire() as conn:
                fetched = await conn.fetch(
                    """
                    SELECT quote_text, attribution
                    FROM quotebook
                    WHERE server_id = $1 AND approved = true
                    """,
                    server_id,
                )
            rows = [dict(r) for r in fetched]
            if cache:
                cache.set(cache_key, rows, ttl=Constants.CACHE_TTL)
        return rows

    async def import_new_quotes(
        self,
        server_id: int,
        quotes: list[tuple[str, str | None, int]],
        approved: bool,
        cache=None,
    ) -> list[tuple[str, str | None]]:
        quote_texts = list({q[0] for q in quotes})
        async with self.db_pool.acquire() as conn:
            existing_rows = await conn.fetch(
                """
                SELECT quote_text FROM quotebook
                WHERE server_id = $1 AND quote_text = ANY($2::text[])
                """,
                server_id,
                quote_texts,
            )
            existing = {r["quote_text"] for r in existing_rows}

            inserted: list[tuple[str, str | None]] = []
            for quote_text, attribution, author_id in quotes:
                if quote_text in existing:
                    continue
                await conn.execute(
                    """
                    INSERT INTO quotebook (server_id, quote_text, submitter_id, attribution, approved)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    server_id,
                    quote_text,
                    author_id,
                    attribution,
                    approved,
                )
                existing.add(quote_text)
                inserted.append((quote_text, attribution))

        self._invalidate(cache, server_id)
        return inserted

    async def list_pending_quote_ids(self, server_id: int) -> list:
        async with self.db_pool.acquire() as conn:
            rows: list = await conn.fetch(
                """
                SELECT id, quote_text
                FROM quotebook
                WHERE server_id = $1 AND approved = false
                ORDER BY created_at DESC
                LIMIT 25
                """,
                server_id,
            )
        return rows
