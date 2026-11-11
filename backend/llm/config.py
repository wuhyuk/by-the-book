"""LLM 설정 읽기 (MVP_SPEC 9절 확정 3·4, 2026-11-08 결정).

필수: LLM_PROVIDER, LLM_API_KEY, LLM_MODEL. 모델 이름은 코드에 쓰지 않고 설정에서만 읽는다.
선택:
- LLM_TEMPERATURE: 줄이 없으면 0, 값을 비워 두면 temperature를 보내지 않는다, 숫자면 그 값(0~2).
- LLM_MAX_RPM: 모델별 분당 호출 상한 (코드가 호출 간격을 지킨다). 없거나 비면 12.
- LLM_FALLBACK_MODEL: 기본 모델이 재시도 후에도 429일 때 1회만 부를 예비 모델. 없거나 비면 쓰지 않는다.

값은 환경변수가 먼저이고, 없으면 backend/.env 파일에서 위 이름만 읽는다 (새 의존성 없이 직접 파싱).
키는 SecretStr로 감싸 repr·로그·예외 메시지에 나오지 않게 한다. 오류 메시지에는 설정 이름만 넣는다.
"""

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, SecretStr

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
REQUIRED_KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL")
OPTIONAL_KEYS = ("LLM_TEMPERATURE", "LLM_MAX_RPM", "LLM_FALLBACK_MODEL")
KEYS = (*REQUIRED_KEYS, *OPTIONAL_KEYS)
SUPPORTED_PROVIDERS = ("gemini",)

DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_RPM = 12
MAX_TEMPERATURE = 2.0
MAX_RPM_LIMIT = 1000


class LLMConfigError(Exception):
    """설정이 없거나 맞지 않는다. 메시지에는 설정 이름만 넣고 값은 넣지 않는다."""


class LLMSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    api_key: SecretStr
    model: str
    temperature: float | None = DEFAULT_TEMPERATURE  # None = 보내지 않음
    max_rpm: int = DEFAULT_MAX_RPM
    fallback_model: str | None = None


def read_env_file(path: Path, keys: tuple[str, ...] = KEYS) -> dict[str, str]:
    """KEY=VALUE 줄에서 keys에 있는 이름만 읽는다. 따옴표는 벗긴다. 파일이 없으면 빈 dict."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip().removeprefix("export ").strip()
        if name not in keys:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    return values


def _temperature(raw: str | None) -> float | None:
    if raw is None:
        return DEFAULT_TEMPERATURE
    if raw == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        raise LLMConfigError(
            "LLM_TEMPERATURE는 0~2 사이 숫자이거나 빈 값이어야 합니다."
        ) from None
    if not 0 <= value <= MAX_TEMPERATURE:
        raise LLMConfigError(
            "LLM_TEMPERATURE는 0~2 사이 숫자이거나 빈 값이어야 합니다."
        )
    return value


def _max_rpm(raw: str | None) -> int:
    if not raw:
        return DEFAULT_MAX_RPM
    if not raw.isdigit() or not 1 <= int(raw) <= MAX_RPM_LIMIT:
        raise LLMConfigError("LLM_MAX_RPM은 1 이상의 정수여야 합니다.")
    return int(raw)


def load_settings(
    environ: Mapping[str, str] | None = None, env_file: Path | None = ENV_FILE
) -> LLMSettings:
    """환경변수 → .env 순서로 읽는다. 테스트는 environ과 env_file=None을 넘겨 실제 파일을 읽지 않는다."""
    env = os.environ if environ is None else environ
    file_values = read_env_file(env_file) if env_file is not None else {}

    def raw(key: str) -> str | None:
        """환경변수에 있으면 그 값, 없으면 파일 값, 둘 다 없으면 None (빈 값과 구분)."""
        if key in env:
            return env[key].strip()
        if key in file_values:
            return file_values[key].strip()
        return None

    required = {
        k: (env.get(k) or "").strip() or (file_values.get(k) or "").strip()
        for k in REQUIRED_KEYS
    }
    empty = [k for k in REQUIRED_KEYS if not required[k]]
    if empty:
        raise LLMConfigError(f"LLM 설정이 비어 있습니다: {', '.join(empty)}")
    provider = required["LLM_PROVIDER"].lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise LLMConfigError("LLM_PROVIDER 값이 지원 목록에 없습니다.")
    return LLMSettings(
        provider=provider,
        api_key=SecretStr(required["LLM_API_KEY"]),
        model=required["LLM_MODEL"],
        temperature=_temperature(raw("LLM_TEMPERATURE")),
        max_rpm=_max_rpm(raw("LLM_MAX_RPM")),
        fallback_model=raw("LLM_FALLBACK_MODEL") or None,
    )
