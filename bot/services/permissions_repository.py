class PermissionsRepository:
    """Persistence for permission checks and grants, bound to a db_pool.

    Mirrors GiveawayRepository's shape: a db_pool bound once at
    construction instead of threaded through every call.
    """

    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def has_command_permission(
        self, server_id: int, user_id: int, command_name: str | None
    ) -> bool:
        async with self.db_pool.acquire() as conn:
            return bool(
                await conn.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM command_permissions
                        WHERE server_id = $1 AND user_id = $2 AND command_name = $3 AND is_active = true
                    )
                    """,
                    server_id,
                    user_id,
                    command_name,
                )
            )

    async def fetch_user_role(self, server_id: int, user_id: int) -> str | None:
        async with self.db_pool.acquire() as conn:
            role: str | None = await conn.fetchval(
                """
                SELECT role FROM user_permissions
                WHERE server_id = $1 AND user_id = $2 AND is_active = true
                ORDER BY CASE role WHEN 'super_admin' THEN 3 WHEN 'admin' THEN 2 WHEN 'moderator' THEN 1 END DESC
                LIMIT 1
                """,
                server_id,
                user_id,
            )
        return role

    async def log_permission_denial(self, server_id: int, user_id: int, details: dict) -> None:
        async with self.db_pool.acquire(timeout=2) as conn:
            await conn.execute(
                """
                INSERT INTO audit_log (server_id, user_id, action, target_type, details)
                VALUES ($1, $2, 'permission_denied', 'command', $3)
                """,
                server_id,
                user_id,
                details,
            )

    async def list_active_grants(self, server_id: int) -> list[dict]:
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, role FROM user_permissions WHERE server_id = $1 AND is_active = true "
                "ORDER BY CASE role WHEN 'super_admin' THEN 3 WHEN 'admin' THEN 2 WHEN 'moderator' THEN 1 END DESC",
                server_id,
            )
        return [dict(r) for r in rows]

    async def find_active_grant(self, server_id: int, user_id: int, role: str) -> bool:
        async with self.db_pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT 1 FROM user_permissions WHERE server_id = $1 AND user_id = $2 AND role = $3 AND is_active = true LIMIT 1",
                server_id,
                user_id,
                role,
            )
        return bool(existing)

    async def insert_grant(self, server_id: int, user_id: int, role: str, granted_by: int) -> None:
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_permissions (server_id, user_id, role, granted_by) VALUES ($1, $2, $3, $4)",
                server_id,
                user_id,
                role,
                granted_by,
            )

    async def revoke_grant(self, server_id: int, user_id: int, role: str) -> bool:
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE user_permissions SET is_active = false, revoked_at = NOW() WHERE server_id = $1 AND user_id = $2 AND role = $3 AND is_active = true",
                server_id,
                user_id,
                role,
            )
        return bool(result) and "UPDATE 1" in result
