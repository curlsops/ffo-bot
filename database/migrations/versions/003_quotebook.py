"""Quotebook table

Revision ID: 003_quotebook
Revises: 002_giveaways
Create Date: 2026-03-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_quotebook"
down_revision: Union[str, None] = "002_giveaways"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quotebook",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("quote_text", sa.Text(), nullable=False),
        sa.Column("submitter_id", sa.BigInteger(), nullable=False),
        sa.Column("attribution", sa.String(length=255), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
    )
    op.create_index(
        "idx_quotebook_server_approved",
        "quotebook",
        ["server_id", "approved"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_quotebook_server_approved", table_name="quotebook")
    op.drop_table("quotebook")
