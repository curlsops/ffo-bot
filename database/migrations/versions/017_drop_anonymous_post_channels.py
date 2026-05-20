"""drop anonymous_post_channels (feature removed)

Revision ID: 017_drop_anonymous_post_channels
Revises: 016_drop_media_files
Create Date: 2026-05-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017_drop_anonymous_post_channels"
down_revision: Union[str, None] = "016_drop_media_files"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
__all__ = [revision, down_revision]


def upgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS anonymous_post_channels CASCADE"))


def downgrade() -> None:
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
        sa.Column("post_channel_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("server_id"),
    )
    op.create_index(
        "idx_anonymous_post_channels_message",
        "anonymous_post_channels",
        ["message_id"],
    )
