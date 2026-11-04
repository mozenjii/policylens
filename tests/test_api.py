"""The HTTP surface answers the way an operator and a load balancer expect."""

from fastapi.testclient import TestClient

import policylens
from policylens.api.app import create_app


def test_health_reports_ok_and_the_running_version() -> None:
    response = TestClient(create_app()).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": policylens.__version__}


def test_unknown_paths_are_404_not_a_fallback_page() -> None:
    assert TestClient(create_app()).get("/no-such-page").status_code == 404
