import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_connection(database_url):
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        version = await conn.fetchval("SELECT version()")
        assert "PostgreSQL" in version
        servers = await conn.fetchval(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'servers'"
        )
        assert servers == 1
    finally:
        await conn.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_pool_create(database_url):
    from database.connection import DatabasePool

    pool = await DatabasePool.create(database_url)
    try:
        version = await pool.fetchval("SELECT version()")
        assert "PostgreSQL" in version
    finally:
        await pool.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_set_server_role_then_get_roundtrip(database_url):
    """Verify set_server_role persists and get_server_role_ids reads it back."""
    from database.connection import DatabasePool

    from bot.cache.memory import InMemoryCache
    from bot.utils.server_roles import get_server_role_ids, set_server_role
    from config.constants import Role

    pool = await DatabasePool.create(database_url, min_size=1, max_size=2)
    cache = InMemoryCache(max_size=100, default_ttl=60)
    try:
        server_id = 999888777
        role_id = 111222333
        await pool.execute(
            "INSERT INTO servers (server_id, server_name) VALUES ($1, $2) ON CONFLICT (server_id) DO NOTHING",
            server_id,
            "TestServer",
        )
        success = await set_server_role(
            pool, server_id, Role.MODERATOR, role_id, cache=cache, server_name="TestServer"
        )
        assert success is True
        role_ids = await get_server_role_ids(pool, server_id, cache=cache)
        assert role_ids == {Role.MODERATOR: role_id}
    finally:
        await pool.execute("DELETE FROM servers WHERE server_id = $1", server_id)
        await pool.close()
