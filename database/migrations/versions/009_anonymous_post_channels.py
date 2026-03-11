"""Anonymous post channel setup

Revision ID: 009_anonymous_post_channels
Revises: 008_faq_submissions
Create Date: 2026-03-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_anonymous_post_channels"
down_revision: Union[str, None] = "008_faq_submissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "anonymous_post_channels",
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("server_id"),
    )
    op.create_index(
        "idx_anonymous_post_channels_message",
        "anonymous_post_channels",
        ["message_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_anonymous_post_channels_message", table_name="anonymous_post_channels")
    op.drop_table("anonymous_post_channels")
