"""Whitelist cache table - usernames from RCON for autocomplete/audit

Revision ID: 006_whitelist_cache
Revises: 005_faq_entries
Create Date: 2026-03-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_whitelist_cache"
down_revision: Union[str, None] = "005_faq_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "whitelist_cache",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=16), nullable=False),
        sa.Column("added_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "added_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_whitelist_cache_server_username",
        "whitelist_cache",
        ["server_id", "username"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_whitelist_cache_server_username", table_name="whitelist_cache")
    op.drop_table("whitelist_cache")
