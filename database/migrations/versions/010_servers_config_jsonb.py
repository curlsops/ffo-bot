"""servers.config jsonb compatibility migration

Revision ID: 010_servers_config_jsonb
Revises: 009_anonymous_post_channels
Create Date: 2026-03-10

`001_initial_schema` already creates `servers.config` as JSONB.
This migration remains in-chain for upgrade paths from older schemas where
`servers.config` may still be JSON.
"""

from typing import Union

from alembic import op

revision: str = "010_servers_config_jsonb"
down_revision: Union[str, None] = "009_anonymous_post_channels"
__all__ = [revision, down_revision]


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'servers'
                  AND column_name = 'config'
                  AND udt_name = 'json'
            ) THEN
                ALTER TABLE servers
                ALTER COLUMN config TYPE jsonb
                USING COALESCE(config::jsonb, '{}'::jsonb);
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    # Keep downgrade explicit/reversible for older app versions that still expect JSON.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'servers'
                  AND column_name = 'config'
                  AND udt_name = 'jsonb'
            ) THEN
                ALTER TABLE servers
                ALTER COLUMN config TYPE json
                USING config::text::json;
            END IF;
        END
        $$;
    """)
