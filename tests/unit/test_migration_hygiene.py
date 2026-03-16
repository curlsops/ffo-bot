import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "database" / "migrations" / "versions"


def _load_migration(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, MIGRATIONS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class TestMigrationMetadataStyle:
    def test_newer_migrations_define_standard_alembic_metadata(self):
        modules = [
            _load_migration("010_servers_config_jsonb.py", "migration_010"),
            _load_migration("011_quotebook_server_quote_text_index.py", "migration_011"),
            _load_migration("012_drop_servers_config_gin.py", "migration_012"),
            _load_migration("013_query_performance_indexes.py", "migration_013"),
        ]

        for module in modules:
            assert hasattr(module, "revision")
            assert hasattr(module, "down_revision")
            assert hasattr(module, "branch_labels")
            assert hasattr(module, "depends_on")
            assert module.branch_labels is None
            assert module.depends_on is None

    def test_revision_chain_is_unchanged_for_latest_steps(self):
        migration_010 = _load_migration("010_servers_config_jsonb.py", "migration_010_chain")
        migration_012 = _load_migration("012_drop_servers_config_gin.py", "migration_012_chain")
        migration_013 = _load_migration("013_query_performance_indexes.py", "migration_013_chain")

        assert migration_010.down_revision == "009_anonymous_post_channels"
        assert migration_012.down_revision == "011_quotebook_quote_idx"
        assert migration_013.down_revision == "012_drop_servers_config_gin"


class TestMigration010Compatibility:
    def test_upgrade_is_conditional_and_json_to_jsonb(self, monkeypatch):
        migration_010 = _load_migration("010_servers_config_jsonb.py", "migration_010_upgrade")
        statements = []
        monkeypatch.setattr(migration_010.op, "execute", statements.append)

        migration_010.upgrade()

        assert len(statements) == 1
        assert "udt_name = 'json'" in statements[0]
        assert "ALTER COLUMN config TYPE jsonb" in statements[0]
        assert "COALESCE(config::jsonb, '{}'::jsonb)" in statements[0]

    def test_downgrade_is_conditional_and_jsonb_to_json(self, monkeypatch):
        migration_010 = _load_migration("010_servers_config_jsonb.py", "migration_010_downgrade")
        statements = []
        monkeypatch.setattr(migration_010.op, "execute", statements.append)

        migration_010.downgrade()

        assert len(statements) == 1
        assert "udt_name = 'jsonb'" in statements[0]
        assert "ALTER COLUMN config TYPE json" in statements[0]
        assert "USING config::text::json" in statements[0]


class TestSafeDowngradeBehavior:
    def test_migration_012_uses_if_exists_and_if_not_exists(self, monkeypatch):
        migration_012 = _load_migration("012_drop_servers_config_gin.py", "migration_012_safe")
        statements = []
        monkeypatch.setattr(migration_012.op, "execute", statements.append)

        migration_012.upgrade()
        migration_012.downgrade()

        assert statements == [
            "DROP INDEX IF EXISTS idx_servers_config",
            "CREATE INDEX IF NOT EXISTS idx_servers_config ON servers USING gin (config)",
        ]

    def test_migration_013_downgrade_drops_indexes_with_if_exists(self, monkeypatch):
        migration_013 = _load_migration("013_query_performance_indexes.py", "migration_013_safe")
        statements = []
        monkeypatch.setattr(migration_013.op, "execute", statements.append)

        migration_013.downgrade()

        assert statements == [
            "DROP INDEX IF EXISTS idx_phrase_reactions_server_match_count_desc",
            "DROP INDEX IF EXISTS idx_faq_entries_server_sort_topic",
            "DROP INDEX IF EXISTS idx_giveaways_server_ended_desc_message_not_null",
            "DROP INDEX IF EXISTS idx_faq_submissions_server_created_desc",
        ]
