from pathlib import Path

_CLIENT = Path(__file__).parents[2] / "bot" / "client.py"


def test_client_clears_commands_before_sync():
    text = _CLIENT.read_text()
    assert "bulk_upsert_global_commands" in text and "bulk_upsert_guild_commands" in text
    assert ", []" in text
    g, w = text.find("bulk_upsert_global_commands"), text.find("bulk_upsert_guild_commands")
    assert g >= 0 and w >= 0 and g < w
