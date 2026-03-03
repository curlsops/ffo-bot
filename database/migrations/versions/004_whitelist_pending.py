"""Whitelist pending table for IGN approval flow

Revision ID: 004_whitelist_pending
Revises: 003_quotebook
Create Date: 2026-03-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_whitelist_pending"
down_revision: Union[str, None] = "003_quotebook"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "whitelist_pending",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=16), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_whitelist_pending_message",
        "whitelist_pending",
        ["server_id", "message_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_whitelist_pending_message", table_name="whitelist_pending")
    op.drop_table("whitelist_pending")
