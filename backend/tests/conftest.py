"""공통 픽스처. 운영 설정은 환경변수로 기본값을 넣어 실제 backend/.env를 열지 않게 한다."""

from collections.abc import Iterator

import pytest

import api.analyze as analyze_module
import api.settings as settings_module


@pytest.fixture(autouse=True)
def default_app_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """ANALYZE_ENABLED=true, DAILY_ANALYZE_LIMIT=450, SURVEY_URL 없음. 카운터는 테스트마다 새로."""
    monkeypatch.setenv("ANALYZE_ENABLED", "true")
    monkeypatch.setenv("DAILY_ANALYZE_LIMIT", "450")
    monkeypatch.setenv("SURVEY_URL", "")
    settings_module.app_settings.cache_clear()
    analyze_module.daily_counter.cache_clear()
    yield
    settings_module.app_settings.cache_clear()
    analyze_module.daily_counter.cache_clear()
