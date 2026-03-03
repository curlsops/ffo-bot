"""FAQ entries table

Revision ID: 005_faq_entries
Revises: 004_whitelist_pending
Create Date: 2026-03-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_faq_entries"
down_revision: Union[str, None] = "004_whitelist_pending"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "faq_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_faq_entries_server_topic",
        "faq_entries",
        ["server_id", "topic"],
        unique=True,
    )
    op.create_index(
        "idx_faq_entries_server_sort",
        "faq_entries",
        ["server_id", "sort_order"],
    )


def downgrade() -> None:
    op.drop_index("idx_faq_entries_server_sort", table_name="faq_entries")
    op.drop_index("idx_faq_entries_server_topic", table_name="faq_entries")
    op.drop_table("faq_entries")
