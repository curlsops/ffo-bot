"""quotebook server_id quote_text index

Revision ID: 011_quotebook_quote_idx
Revises: 010_servers_config_jsonb
Create Date: 2026-03-10

"""

from typing import Union

from alembic import op

revision: str = "011_quotebook_quote_idx"
down_revision: Union[str, None] = "010_servers_config_jsonb"
__all__ = [revision, down_revision]


def upgrade() -> None:
    op.create_index(
        "idx_quotebook_server_quote_text",
        "quotebook",
        ["server_id", "quote_text"],
    )


def downgrade() -> None:
    op.drop_index("idx_quotebook_server_quote_text", table_name="quotebook")
