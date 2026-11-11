"""운영 설정 (2026-11-11 결정, 1차 배포용 안전 스위치).

- ANALYZE_ENABLED: 문장 분석(/api/analyze) 사용 여부. 없거나 비면 true.
  true/1/yes/on → 켬, false/0/no/off → 끔. 그 밖의 값은 안전하게 끈다 (설정 이름만 경고 로그).
- DAILY_ANALYZE_LIMIT: 하루(KST) Gemini 호출 상한. 없거나 비면 450 (기본 모델 RPD 500보다 낮게).
  0 이상의 정수가 아니면 기본값을 쓴다 (설정 이름만 경고 로그).
- SURVEY_URL: 화면에 보여 줄 설문 링크. 없거나 비면 null. http(s) 주소가 아니면 null.

값은 환경변수가 먼저이고, 없으면 backend/.env에서 위 이름만 읽는다 (llm/config.py와 같은 방식).
비밀값이 아니지만 로그에는 설정 이름만 남긴다.
"""

import logging
import os
from collections.abc import Mapping
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from llm.config import ENV_FILE, read_env_file

logger = logging.getLogger("by_the_book.api")

APP_KEYS = ("ANALYZE_ENABLED", "DAILY_ANALYZE_LIMIT", "SURVEY_URL")
DEFAULT_DAILY_ANALYZE_LIMIT = 450
_TRUE = frozenset({"true", "1", "yes", "on"})
_FALSE = frozenset({"false", "0", "no", "off"})


class AppSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    analyze_enabled: bool = True
    daily_analyze_limit: int = DEFAULT_DAILY_ANALYZE_LIMIT
    survey_url: str | None = None


def _enabled(raw: str) -> bool:
    if not raw:
        return True
    value = raw.lower()
    if value in _TRUE:
        return True
    if value not in _FALSE:
        logger.warning("ANALYZE_ENABLED 값이 맞지 않아 문장 분석을 끕니다.")
    return False


def _limit(raw: str) -> int:
    if not raw:
        return DEFAULT_DAILY_ANALYZE_LIMIT
    if not raw.isdigit():
        logger.warning("DAILY_ANALYZE_LIMIT 값이 맞지 않아 기본값을 씁니다.")
        return DEFAULT_DAILY_ANALYZE_LIMIT
    return int(raw)


def _survey_url(raw: str) -> str | None:
    if not raw:
        return None
    if not raw.startswith(("https://", "http://")):
        logger.warning("SURVEY_URL 값이 http(s) 주소가 아니어서 쓰지 않습니다.")
        return None
    return raw


def load_app_settings(
    environ: Mapping[str, str] | None = None, env_file: Path | None = ENV_FILE
) -> AppSettings:
    """환경변수 → .env 순서로 읽는다. 테스트는 environ과 env_file=None을 넘긴다."""
    env = os.environ if environ is None else environ
    # 세 값이 모두 환경변수에 있으면 파일을 열지 않는다 (테스트·배포 호스트).
    need_file = env_file is not None and any(k not in env for k in APP_KEYS)
    file_values = read_env_file(env_file, APP_KEYS) if need_file and env_file else {}

    def raw(key: str) -> str:
        if key in env:
            return env[key].strip()
        return file_values.get(key, "").strip()

    return AppSettings(
        analyze_enabled=_enabled(raw("ANALYZE_ENABLED")),
        daily_analyze_limit=_limit(raw("DAILY_ANALYZE_LIMIT")),
        survey_url=_survey_url(raw("SURVEY_URL")),
    )


@cache
def app_settings() -> AppSettings:
    """프로세스에서 한 번 읽는다. 값을 바꾸면 서버를 다시 시작한다."""
    return load_app_settings()


def get_app_settings() -> AppSettings:
    """FastAPI 의존성. 테스트에서 바꿔 끼운다."""
    return app_settings()
