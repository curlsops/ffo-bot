from pathlib import Path

import httpx
import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.image import DockerImage
from testcontainers.core.wait_strategies import HttpWaitStrategy


class FastAPIContainer(DockerContainer):
    def __init__(self, image: str, port: int = 8000) -> None:
        super().__init__(image)
        self._port = port
        self.with_exposed_ports(port)
        self.waiting_for(HttpWaitStrategy(port, "/").for_status_code(200))

    def get_url(self) -> str:
        host = self.get_container_host_ip()
        exposed = self.get_exposed_port(self._port)
        return f"http://{host}:{exposed}"


@pytest.fixture(scope="session")
def fastapi_container():
    fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / "fastapi_app"
    with DockerImage(
        path=str(fixture_path), tag="ffobot-fastapi-test:latest", clean_up=False
    ) as image:
        with FastAPIContainer(str(image), port=8000) as container:
            yield container


@pytest.mark.integration
@pytest.mark.xdist_group("fastapi_container")
@pytest.mark.parametrize(
    "path,expected",
    [("/", {"status": "ok"}), ("/health", {"healthy": True})],
    ids=["root", "health"],
)
def test_fastapi_container(fastapi_container, path, expected):
    url = fastapi_container.get_url()
    r = httpx.get(f"{url}{path}", timeout=10)
    assert r.status_code == 200
    assert r.json() == expected
