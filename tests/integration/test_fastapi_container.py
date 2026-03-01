import os

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
    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "fixtures",
        "fastapi_app",
    )
    with DockerImage(path=fixture_path, tag="ffobot-fastapi-test:latest", clean_up=False) as image:
        with FastAPIContainer(str(image), port=8000) as container:
            yield container


@pytest.mark.integration
@pytest.mark.xdist_group("fastapi_container")
def test_fastapi_container_root(fastapi_container):
    url = fastapi_container.get_url()
    response = httpx.get(f"{url}/", timeout=10)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.integration
@pytest.mark.xdist_group("fastapi_container")
def test_fastapi_container_health(fastapi_container):
    url = fastapi_container.get_url()
    response = httpx.get(f"{url}/health", timeout=10)
    assert response.status_code == 200
    assert response.json() == {"healthy": True}
