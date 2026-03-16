"""servers.config jsonb

Revision ID: 010_servers_config_jsonb
Revises: 009_anonymous_post_channels
Create Date: 2026-03-10

"""

from typing import Sequence, Union

from alembic import op

revision: str = "010_servers_config_jsonb"
down_revision: Union[str, None] = "009_anonymous_post_channels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
