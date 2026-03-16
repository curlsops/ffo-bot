"""add query performance indexes for faq, giveaways, and phrases

Revision ID: 013_query_performance_indexes
Revises: 012_drop_servers_config_gin
Create Date: 2026-03-16

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_query_performance_indexes"
down_revision: Union[str, None] = "012_drop_servers_config_gin"
__all__ = [revision, down_revision]


def upgrade() -> None:
    op.create_index(
        "idx_faq_submissions_server_created_desc",
        "faq_submissions",
        ["server_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_giveaways_server_ended_desc_message_not_null",
        "giveaways",
        ["server_id", sa.text("ended_at DESC")],
        postgresql_where=sa.text("message_id IS NOT NULL"),
    )
    op.create_index(
        "idx_faq_entries_server_sort_topic",
        "faq_entries",
        ["server_id", "sort_order", "topic"],
    )
    op.create_index(
        "idx_phrase_reactions_server_match_count_desc",
        "phrase_reactions",
        ["server_id", sa.text("match_count DESC")],
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    # IF EXISTS makes downgrade idempotent for partially-applied/stale environments.
    op.execute("DROP INDEX IF EXISTS idx_phrase_reactions_server_match_count_desc")
    op.execute("DROP INDEX IF EXISTS idx_faq_entries_server_sort_topic")
    op.execute("DROP INDEX IF EXISTS idx_giveaways_server_ended_desc_message_not_null")
    op.execute("DROP INDEX IF EXISTS idx_faq_submissions_server_created_desc")
