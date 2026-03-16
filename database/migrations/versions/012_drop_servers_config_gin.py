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
    # Defensive IF EXISTS keeps upgrade resilient on drifted environments.
    op.execute("DROP INDEX IF EXISTS idx_servers_config")


def downgrade() -> None:
    # Recreate only when missing so downgrade is safe to re-run after partial failures.
    op.execute("CREATE INDEX IF NOT EXISTS idx_servers_config ON servers USING gin (config)")
