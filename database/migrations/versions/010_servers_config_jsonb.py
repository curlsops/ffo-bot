"""servers.config jsonb

Revision ID: 010_servers_config_jsonb
Revises: 009_anonymous_post_channels
Create Date: 2026-03-10

Note: 001_initial_schema already creates config as JSONB. This migration exists
for upgrade paths from older revisions that may have used json type.
"""

from typing import Union

from alembic import op

revision: str = "010_servers_config_jsonb"
down_revision: Union[str, None] = "009_anonymous_post_channels"
__all__ = [revision, down_revision]


def upgrade() -> None:
    op.execute("""
        ALTER TABLE servers
        ALTER COLUMN config TYPE jsonb
        USING COALESCE(config::jsonb, '{}'::jsonb)
        """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE servers
        ALTER COLUMN config TYPE json
        USING config::text::json
        """)
