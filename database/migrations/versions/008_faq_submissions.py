"""FAQ question submissions from users

Revision ID: 008_faq_submissions
Revises: 007_whitelist_minecraft_uuid
Create Date: 2026-03-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_faq_submissions"
down_revision: Union[str, None] = "007_whitelist_minecraft_uuid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "faq_submissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("submitter_id", sa.BigInteger(), nullable=False),
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
        "idx_faq_submissions_server",
        "faq_submissions",
        ["server_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_faq_submissions_server", table_name="faq_submissions")
    op.drop_table("faq_submissions")
