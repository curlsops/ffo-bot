"""drop media_files and message_metadata.has_media

Revision ID: 016_drop_media_files
Revises: 015_anon_post_dest_channel
Create Date: 2026-04-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016_drop_media_files"
down_revision: Union[str, None] = "015_anon_post_dest_channel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
__all__ = [revision, down_revision]


def upgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS media_files CASCADE"))
    op.execute(sa.text("ALTER TABLE message_metadata DROP COLUMN IF EXISTS has_media"))


def downgrade() -> None:
    op.add_column(
        "message_metadata",
        sa.Column("has_media", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "media_files",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("uploader_id", sa.BigInteger(), nullable=False),
        sa.Column("file_name", sa.String(length=500), nullable=False),
        sa.Column("file_type", sa.String(length=50), nullable=False),
        sa.Column("file_extension", sa.String(length=20), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("download_url", sa.Text(), nullable=False),
        sa.Column(
            "downloaded_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "file_name", name="_message_file_uc"),
    )
    op.create_index(
        "idx_media_files_server",
        "media_files",
        ["server_id", sa.text("downloaded_at DESC")],
        unique=False,
    )
    op.create_index("idx_media_files_message", "media_files", ["message_id"], unique=False)
    op.create_index(
        "idx_media_files_uploader",
        "media_files",
        ["server_id", "uploader_id", sa.text("downloaded_at DESC")],
        unique=False,
    )
    op.create_index("idx_media_files_storage", "media_files", ["storage_path"], unique=False)
