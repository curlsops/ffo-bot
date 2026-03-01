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
