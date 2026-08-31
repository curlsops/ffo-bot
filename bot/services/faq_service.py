from config.constants import Constants

CACHE_FAQ_TOPICS = "faq_topics:{server_id}"
CACHE_FAQ_ENTRY = "faq_entry:{server_id}:{topic}"
CACHE_FAQ_ALL = "faq_all:{server_id}"


class FaqService:
    """Persistence and caching policy for FAQ entries/submissions, bound to a db_pool.

    Cache is passed per-call (not bound at construction) since callers may
    reassign bot.cache after the service is already constructed.
    """

    def __init__(self, db_pool):
        self.db_pool = db_pool

    def _invalidate(self, cache, server_id: int, topic: str | None = None) -> None:
        if cache:
            cache.delete(CACHE_FAQ_TOPICS.format(server_id=server_id))
            cache.delete(CACHE_FAQ_ALL.format(server_id=server_id))
            if topic:
                cache.delete(CACHE_FAQ_ENTRY.format(server_id=server_id, topic=topic))

    async def list_topics(self, server_id: int) -> list:
        async with self.db_pool.acquire() as conn:
            rows: list = await conn.fetch(
                """
                SELECT topic FROM faq_entries
                WHERE server_id = $1
                ORDER BY sort_order, topic
                """,
                server_id,
            )
        return rows

    async def fetch_entry(self, server_id: int, topic: str, cache=None) -> dict | None:
        cache_key = CACHE_FAQ_ENTRY.format(server_id=server_id, topic=topic)
        row = cache.get(cache_key) if cache else None
        if row is None:
            async with self.db_pool.acquire() as conn:
                fetched = await conn.fetchrow(
                    "SELECT question, answer FROM faq_entries WHERE server_id = $1 AND topic = $2",
                    server_id,
                    topic,
                )
            if fetched is None:
                return None
            row = dict(fetched)
            if cache:
                cache.set(cache_key, row, ttl=Constants.CACHE_TTL)
        return row

    async def fetch_all_entries(self, server_id: int, cache=None) -> list[dict]:
        cache_key = CACHE_FAQ_ALL.format(server_id=server_id)
        rows = cache.get(cache_key) if cache else None
        if rows is None:
            async with self.db_pool.acquire() as conn:
                fetched = await conn.fetch(
                    """
                    SELECT topic, question, answer
                    FROM faq_entries
                    WHERE server_id = $1
                    ORDER BY sort_order, topic
                    """,
                    server_id,
                )
            rows = [dict(r) for r in fetched]
            if cache:
                cache.set(cache_key, rows, ttl=Constants.CACHE_TTL)
        return rows

    async def submit_question(self, server_id: int, question: str, submitter_id: int) -> str:
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO faq_submissions (server_id, question, submitter_id)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                server_id,
                question,
                submitter_id,
            )
        return str(row["id"])

    async def count_entries(self, server_id: int) -> int:
        async with self.db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM faq_entries WHERE server_id = $1",
                server_id,
            )
        return count or 0

    async def upsert_entry(
        self, server_id: int, topic: str, question: str, answer: str, cache=None
    ) -> None:
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO faq_entries (server_id, topic, question, answer, sort_order)
                VALUES ($1, $2, $3, $4, COALESCE(
                    (SELECT MAX(sort_order) + 1 FROM faq_entries WHERE server_id = $1), 0
                ))
                ON CONFLICT (server_id, topic) DO UPDATE
                SET question = EXCLUDED.question, answer = EXCLUDED.answer, updated_at = NOW()
                """,
                server_id,
                topic,
                question,
                answer,
            )
        self._invalidate(cache, server_id, topic)

    async def edit_entry(
        self,
        server_id: int,
        topic: str,
        question: str | None,
        answer: str | None,
        cache=None,
    ) -> dict | None:
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE faq_entries
                SET question = COALESCE($1, question), answer = COALESCE($2, answer), updated_at = NOW()
                WHERE server_id = $3 AND topic = $4
                RETURNING question, answer
                """,
                question,
                answer,
                server_id,
                topic,
            )
        if row is None:
            return None
        self._invalidate(cache, server_id, topic)
        return dict(row)

    async def list_submissions(self, server_id: int) -> list[dict]:
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, question, submitter_id, created_at
                FROM faq_submissions
                WHERE server_id = $1
                ORDER BY created_at DESC
                LIMIT 25
                """,
                server_id,
            )
        return [dict(r) for r in rows]

    async def delete_entry(self, server_id: int, topic: str, cache=None) -> bool:
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM faq_entries WHERE server_id = $1 AND topic = $2",
                server_id,
                topic,
            )
        deleted = bool(result) and "DELETE 0" not in result
        if deleted:
            self._invalidate(cache, server_id, topic)
        return deleted
