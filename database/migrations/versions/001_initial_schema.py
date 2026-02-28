"""Initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-01-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Servers table
    op.create_table(
        "servers",
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("server_name", sa.String(length=255), nullable=False),
        sa.Column(
            "joined_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
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
        sa.PrimaryKeyConstraint("server_id"),
        comment="Discord servers (guilds) where the bot is active",
    )
    op.create_index(
        "idx_servers_active",
        "servers",
        ["is_active"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "idx_servers_config", "servers", ["config"], unique=False, postgresql_using="gin"
    )

    # User permissions table
    op.create_table(
        "user_permissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("granted_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "granted_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint("role IN ('super_admin', 'admin', 'moderator')"),
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "_server_user_role_active_uc",
        "user_permissions",
        ["server_id", "user_id", "role"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "idx_user_permissions_lookup",
        "user_permissions",
        ["server_id", "user_id", "is_active"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "idx_user_permissions_role",
        "user_permissions",
        ["server_id", "role"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )

    # Command permissions table
    op.create_table(
        "command_permissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("command_name", sa.String(length=100), nullable=False),
        sa.Column("granted_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "granted_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "_server_user_command_active_uc",
        "command_permissions",
        ["server_id", "user_id", "command_name"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "idx_command_permissions_lookup",
        "command_permissions",
        ["server_id", "user_id", "command_name", "is_active"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )

    # Reaction roles table
    op.create_table(
        "reaction_roles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("emoji", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
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
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "_server_message_emoji_uc",
        "reaction_roles",
        ["server_id", "message_id", "emoji"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "idx_reaction_roles_message",
        "reaction_roles",
        ["message_id", "is_active"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "idx_reaction_roles_server",
        "reaction_roles",
        ["server_id", "is_active"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )

    # Phrase reactions table
    op.create_table(
        "phrase_reactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("phrase", sa.String(length=500), nullable=False),
        sa.Column("emoji", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("match_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_matched_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
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
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="Phrase patterns that trigger automatic emoji reactions",
    )
    op.create_index(
        "_server_phrase_emoji_uc",
        "phrase_reactions",
        ["server_id", "phrase", "emoji"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "idx_phrase_reactions_server",
        "phrase_reactions",
        ["server_id", "is_active"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "idx_phrase_reactions_phrase",
        "phrase_reactions",
        ["server_id", "phrase"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )

    # Message metadata table
    op.create_table(
        "message_metadata",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("phrase_matched", sa.String(length=500), nullable=True),
        sa.Column("reaction_added", sa.String(length=255), nullable=True),
        sa.Column("has_media", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "processed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "retention_expires_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW() + INTERVAL '1 year'"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="_message_id_uc"),
        comment="Message tracking metadata (NOT message content) with 1-year retention",
    )
    op.create_index(
        "idx_message_metadata_retention", "message_metadata", ["retention_expires_at"], unique=False
    )
    op.create_index(
        "idx_message_metadata_user",
        "message_metadata",
        ["server_id", "user_id", "processed_at"],
        unique=False,
    )
    op.create_index(
        "idx_message_metadata_channel",
        "message_metadata",
        ["server_id", "channel_id", "processed_at"],
        unique=False,
    )

    # User preferences table
    op.create_table(
        "user_preferences",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "message_tracking_opt_out",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("opted_out_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id", "user_id", name="_server_user_prefs_uc"),
    )
    op.create_index(
        "idx_user_preferences_opt_out",
        "user_preferences",
        ["server_id", "user_id", "message_tracking_opt_out"],
        unique=False,
        postgresql_where=sa.text("message_tracking_opt_out = true"),
    )

    # Media files table
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

    # Notifiarr failures table
    op.create_table(
        "notifiarr_failures",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("failure_type", sa.String(length=100), nullable=False),
        sa.Column("media_title", sa.String(length=500), nullable=False),
        sa.Column("media_type", sa.String(length=50), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("notifiarr_message_id", sa.BigInteger(), nullable=True),
        sa.Column("alert_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("alert_sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "detected_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_notifiarr_failures_server",
        "notifiarr_failures",
        ["server_id", sa.text("detected_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_notifiarr_failures_type",
        "notifiarr_failures",
        ["failure_type", sa.text("detected_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_notifiarr_failures_alert",
        "notifiarr_failures",
        ["alert_sent"],
        unique=False,
        postgresql_where=sa.text("alert_sent = false"),
    )

    # Bot config table
    op.create_table(
        "bot_config",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
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
        sa.PrimaryKeyConstraint("key"),
    )

    # Audit log table
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("server_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.String(length=255), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["server_id"], ["servers.server_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_audit_log_server",
        "audit_log",
        ["server_id", sa.text("occurred_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_audit_log_user", "audit_log", ["user_id", sa.text("occurred_at DESC")], unique=False
    )
    op.create_index(
        "idx_audit_log_action", "audit_log", ["action", sa.text("occurred_at DESC")], unique=False
    )
    op.create_index("idx_audit_log_retention", "audit_log", ["occurred_at"], unique=False)

    # Create function for updating updated_at timestamp
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create triggers
    for table in [
        "servers",
        "user_permissions",
        "command_permissions",
        "reaction_roles",
        "phrase_reactions",
        "user_preferences",
        "bot_config",
    ]:
        op.execute(f"""
            CREATE TRIGGER update_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    # Drop triggers
    for table in [
        "servers",
        "user_permissions",
        "command_permissions",
        "reaction_roles",
        "phrase_reactions",
        "user_preferences",
        "bot_config",
    ]:
        op.execute(f"DROP TRIGGER IF EXISTS update_{table}_updated_at ON {table}")

    # Drop function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    # Drop tables in reverse order
    op.drop_table("audit_log")
    op.drop_table("bot_config")
    op.drop_table("notifiarr_failures")
    op.drop_table("media_files")
    op.drop_table("user_preferences")
    op.drop_table("message_metadata")
    op.drop_table("phrase_reactions")
    op.drop_table("reaction_roles")
    op.drop_table("command_permissions")
    op.drop_table("user_permissions")
    op.drop_table("servers")

    # Drop UUID extension
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
