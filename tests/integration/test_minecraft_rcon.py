import pytest

from bot.services.minecraft_rcon import parse_whitelist_list_response


def _rcon_exec(container, command: str) -> str:
    result = container.exec(["rcon-cli", command])
    output = result.output.decode("utf-8") if isinstance(result.output, bytes) else result.output
    return output.strip()


@pytest.fixture(scope="module")
def minecraft_container():
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.wait_strategies import LogMessageWaitStrategy

    # itzg/minecraft-server: RCON enabled by default, rcon-cli available
    # ONLINE_MODE=false: skip Mojang validation so any username works (avoids "that player does not exist")
    container = (
        DockerContainer("itzg/minecraft-server:latest")
        .with_env("EULA", "TRUE")
        .with_env("ONLINE_MODE", "false")
        .with_env("RCON_PASSWORD", "testrcon123")
        .with_env("MEMORY", "512M")
        .with_env("TYPE", "VANILLA")
        .with_exposed_ports(25575)
        .waiting_for(
            LogMessageWaitStrategy("Done")
            .with_startup_timeout(180)  # Minecraft can take 60-120s on first start
            .with_poll_interval(2)
        )
    )
    with container:
        yield container


VALID_USERS = ("pn55", "MrCurlsTV", "notch")


@pytest.mark.integration
@pytest.mark.slow
def test_rcon_whitelist_add_list_remove(minecraft_container):
    user = VALID_USERS[0]
    add_resp = _rcon_exec(minecraft_container, f"whitelist add {user}")
    assert "added" in add_resp.lower() or "already" in add_resp.lower()

    list_resp = _rcon_exec(minecraft_container, "whitelist list")
    usernames = parse_whitelist_list_response(list_resp)
    assert user.lower() in [u.lower() for u in usernames]

    remove_resp = _rcon_exec(minecraft_container, f"whitelist remove {user}")
    assert "removed" in remove_resp.lower()

    list_resp2 = _rcon_exec(minecraft_container, "whitelist list")
    usernames2 = parse_whitelist_list_response(list_resp2)
    assert user.lower() not in [u.lower() for u in usernames2]


@pytest.mark.integration
@pytest.mark.slow
def test_rcon_whitelist_list_empty(minecraft_container):
    list_resp = _rcon_exec(minecraft_container, "whitelist list")
    usernames = parse_whitelist_list_response(list_resp)
    assert isinstance(usernames, list)


@pytest.mark.integration
@pytest.mark.slow
def test_rcon_whitelist_add_duplicate(minecraft_container):
    user = VALID_USERS[1]
    _rcon_exec(minecraft_container, f"whitelist add {user}")
    dup_resp = _rcon_exec(minecraft_container, f"whitelist add {user}")
    assert "already" in dup_resp.lower() or "whitelisted" in dup_resp.lower()

    # Cleanup
    _rcon_exec(minecraft_container, f"whitelist remove {user}")


@pytest.mark.integration
@pytest.mark.slow
def test_rcon_whitelist_multiple_users(minecraft_container):
    for user in VALID_USERS:
        add_resp = _rcon_exec(minecraft_container, f"whitelist add {user}")
        assert "added" in add_resp.lower() or "already" in add_resp.lower()

    list_resp = _rcon_exec(minecraft_container, "whitelist list")
    usernames = parse_whitelist_list_response(list_resp)
    usernames_lower = [u.lower() for u in usernames]
    for user in VALID_USERS:
        assert user.lower() in usernames_lower

    for user in VALID_USERS:
        _rcon_exec(minecraft_container, f"whitelist remove {user}")
