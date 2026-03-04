import pytest

from bot.utils.config_repair import repair_servers_config


@pytest.mark.parametrize(
    "cfg,expected",
    [
        ({"admin_role_id": 123}, {"admin_role_id": 123}),
        ([{}, '{"admin_role_id": 789}'], {"admin_role_id": 789}),
        (['{"a": 1}', '{"whitelist_channel_id": 111}'], {"whitelist_channel_id": 111}),
        (['{"not json', '{"valid": 1}'], {"valid": 1}),
    ],
)
def test_repair_extracts_valid_config(cfg, expected):
    assert repair_servers_config(cfg) == expected


@pytest.mark.parametrize("cfg", ["invalid", None, [], [1, 2, 3], ['[1,2,3]', 'invalid', 123]])
def test_repair_returns_none_for_invalid(cfg):
    assert repair_servers_config(cfg) is None
