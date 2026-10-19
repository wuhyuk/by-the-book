"""health 엔드포인트 테스트."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    """/health는 200과 status=ok를 돌려준다."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
