"""drop unused servers.config GIN index

Revision ID: 012_drop_servers_config_gin
Revises: 011_quotebook_quote_idx
Create Date: 2026-03-16

"""

from typing import Union

from alembic import op

revision: str = "012_drop_servers_config_gin"
down_revision: Union[str, None] = "011_quotebook_quote_idx"
__all__ = [revision, down_revision]


def upgrade() -> None:
    op.drop_index("idx_servers_config", table_name="servers")


def downgrade() -> None:
    op.create_index(
        "idx_servers_config",
        "servers",
        ["config"],
        unique=False,
        postgresql_using="gin",
    )
