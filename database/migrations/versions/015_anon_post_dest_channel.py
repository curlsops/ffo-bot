"""Anonymous post destination channel

Revision ID: 015_anon_post_dest_channel
Revises: 014_repair_servers_config_array
Create Date: 2026-03-31

Add post_channel_id (anonymized message destination); backfill from channel_id.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_anon_post_dest_channel"
down_revision: Union[str, None] = "014_repair_servers_config_array"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
__all__ = [revision, down_revision]


def upgrade() -> None:
    op.add_column(
        "anonymous_post_channels",
        sa.Column("post_channel_id", sa.BigInteger(), nullable=True),
    )
    op.execute(
        "UPDATE anonymous_post_channels SET post_channel_id = channel_id "
        "WHERE post_channel_id IS NULL"
    )
    op.alter_column(
        "anonymous_post_channels",
        "post_channel_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("anonymous_post_channels", "post_channel_id")
