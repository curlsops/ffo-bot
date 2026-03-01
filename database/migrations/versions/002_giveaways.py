"""Giveaways schema

Revision ID: 002_giveaways
Revises: 001_initial
Create Date: 2026-02-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_giveaways"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "giveaways",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("host_id", sa.BigInteger(), nullable=False),
        sa.Column("donor_id", sa.BigInteger(), nullable=True),
        sa.Column("prize", sa.String(500), nullable=False),
        sa.Column("winners_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("ends_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "required_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "blacklist_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "bypass_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "bonus_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "message_req",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("no_donor_win", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("no_defaults", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("ping", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("extra_text", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
    op.create_index("idx_giveaways_server", "giveaways", ["server_id"])
    op.create_index("idx_giveaways_active", "giveaways", ["is_active", "ends_at"])
    op.create_index("idx_giveaways_message", "giveaways", ["message_id"])

    op.create_table(
        "giveaway_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("giveaway_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("entries", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_winner", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["giveaway_id"], ["giveaways.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("giveaway_id", "user_id", name="uq_giveaway_user"),
    )
    op.create_index("idx_giveaway_entries_giveaway", "giveaway_entries", ["giveaway_id"])
    op.create_index("idx_giveaway_entries_user", "giveaway_entries", ["user_id"])


def downgrade() -> None:
    op.drop_table("giveaway_entries")
    op.drop_table("giveaways")
