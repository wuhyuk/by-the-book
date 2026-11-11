"""화면 서빙(SPA 폴백)과 /healthz 테스트 (2026-11-12). 임시 dist 폴더로 확인한다."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.health import router as health_router
from api.spa import install_spa
from main import app as main_app

INDEX = "<!doctype html><title>기준대로</title><div id=root></div>"


@pytest.fixture
def spa(tmp_path: Path) -> TestClient:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("SECRET-ZQX", encoding="utf-8")
    app = FastAPI()
    app.include_router(health_router)

    @app.get("/api/ping")
    def ping() -> dict[str, str]:
        return {"pong": "1"}

    assert install_spa(app, dist) is True
    return TestClient(app)


def test_index_and_fallback(spa: TestClient) -> None:
    for path in ["/", "/laundry", "/some/deep/route", "/result?x=1"]:
        r = spa.get(path)
        assert r.status_code == 200
        assert r.text == INDEX
        assert r.headers["content-type"].startswith("text/html")
        assert r.headers["cache-control"] == "no-cache"


def test_static_asset(spa: TestClient) -> None:
    r = spa.get("/assets/app.js")
    assert r.status_code == 200 and r.text == "console.log(1)"


def test_api_is_not_fallback(spa: TestClient) -> None:
    assert spa.get("/api/ping").json() == {"pong": "1"}
    for path in ["/api", "/api/nope", "/api/nope/deeper"]:
        r = spa.get(path)
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("application/json")


def test_no_file_outside_dist(spa: TestClient) -> None:
    for path in ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"]:
        r = spa.get(path)
        assert "SECRET-ZQX" not in r.text


def test_healthz(spa: TestClient) -> None:
    assert spa.get("/healthz").json() == {"status": "ok"}


def test_missing_dist_registers_nothing(tmp_path: Path) -> None:
    app = FastAPI()
    assert install_spa(app, tmp_path / "none") is False
    assert TestClient(app).get("/").status_code == 404


def test_main_app_keeps_api_routes() -> None:
    """실제 앱: API·헬스체크가 화면 서빙에 가려지지 않는다."""
    c = TestClient(main_app)
    assert c.get("/healthz").json() == {"status": "ok"}
    assert c.get("/health").json() == {"status": "ok"}
    assert c.get("/api/config").status_code == 200
    assert c.get("/openapi.json").status_code == 200
