"""repair_servers_config_array

Revision ID: 014_repair_servers_config_array
Revises: 013_query_performance_indexes
Create Date: 2026-03-18 09:04:31.315443

Repairs servers.config that were corrupted into JSON arrays (from config || object
appending when config was already an array). Merges all object elements into a
single JSON object, last value wins per key.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "014_repair_servers_config_array"
down_revision: Union[str, None] = "013_query_performance_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
__all__ = [revision, down_revision]


def upgrade() -> None:
    op.execute("""
        WITH elements AS (
            SELECT
                s.server_id,
                CASE
                    WHEN jsonb_typeof(elem) = 'object' THEN elem
                    WHEN jsonb_typeof(elem) = 'string'
                        AND jsonb_typeof((elem #>> '{}')::jsonb) = 'object'
                    THEN (elem #>> '{}')::jsonb
                    ELSE NULL
                END AS obj,
                ord
            FROM servers s,
                jsonb_array_elements(s.config) WITH ORDINALITY AS t(elem, ord)
            WHERE jsonb_typeof(s.config) = 'array'
        ),
        key_values AS (
            SELECT server_id, kv.key, kv.value, ord
            FROM elements e, jsonb_each_text(e.obj) AS kv
            WHERE e.obj IS NOT NULL
        ),
        last_values AS (
            SELECT server_id, key,
                (array_agg(value ORDER BY ord))[array_upper(array_agg(value ORDER BY ord), 1)] AS val
            FROM key_values
            GROUP BY server_id, key
        ),
        merged AS (
            SELECT server_id, jsonb_object_agg(key, val) AS fixed
            FROM last_values
            GROUP BY server_id
        )
        UPDATE servers s
        SET config = m.fixed, updated_at = NOW()
        FROM merged m
        WHERE s.server_id = m.server_id
    """)


def downgrade() -> None:
    pass
