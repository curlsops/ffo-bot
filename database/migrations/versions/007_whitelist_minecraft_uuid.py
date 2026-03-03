"""Add minecraft_uuid to whitelist_cache and whitelist_pending

Revision ID: 007_whitelist_minecraft_uuid
Revises: 006_whitelist_cache
Create Date: 2026-03-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_whitelist_minecraft_uuid"
down_revision: Union[str, None] = "006_whitelist_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "whitelist_cache",
        sa.Column("minecraft_uuid", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "whitelist_pending",
        sa.Column("minecraft_uuid", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("whitelist_pending", "minecraft_uuid")
    op.drop_column("whitelist_cache", "minecraft_uuid")
