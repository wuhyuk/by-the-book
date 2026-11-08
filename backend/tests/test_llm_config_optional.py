"""선택 설정 테스트: LLM_TEMPERATURE·LLM_MAX_RPM·LLM_FALLBACK_MODEL (2026-11-08 결정).

실제 backend/.env는 읽지 않는다 (env_file=None 또는 tmp 파일, 가짜 키).
"""

from pathlib import Path

import pytest

from llm.config import LLMConfigError, load_settings

FAKE_KEY = "FAKE-KEY-ZQX-3333"
ENV = {"LLM_PROVIDER": "gemini", "LLM_API_KEY": FAKE_KEY, "LLM_MODEL": "model-a"}


def test_optional_defaults() -> None:
    s = load_settings(ENV, env_file=None)
    assert s.temperature == 0.0  # 줄이 없으면 0
    assert s.max_rpm == 12
    assert s.fallback_model is None


def test_temperature_empty_means_not_sent() -> None:
    s = load_settings({**ENV, "LLM_TEMPERATURE": ""}, env_file=None)
    assert s.temperature is None
    s = load_settings({**ENV, "LLM_TEMPERATURE": "0.3"}, env_file=None)
    assert s.temperature == 0.3


def test_optional_values_from_file(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text(
        "LLM_TEMPERATURE=\nLLM_MAX_RPM=5\nLLM_FALLBACK_MODEL=model-b\n",
        encoding="utf-8",
    )
    s = load_settings(ENV, env_file=f)
    assert s.temperature is None
    assert s.max_rpm == 5
    assert s.fallback_model == "model-b"


def test_environ_empty_overrides_file_number(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text("LLM_TEMPERATURE=0.5\n", encoding="utf-8")
    s = load_settings({**ENV, "LLM_TEMPERATURE": ""}, env_file=f)
    assert s.temperature is None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("LLM_TEMPERATURE", "abc"),
        ("LLM_TEMPERATURE", "3"),
        ("LLM_TEMPERATURE", "-1"),
        ("LLM_MAX_RPM", "0"),
        ("LLM_MAX_RPM", "x"),
        ("LLM_MAX_RPM", "1.5"),
    ],
)
def test_optional_invalid(key: str, value: str) -> None:
    with pytest.raises(LLMConfigError) as exc:
        load_settings({**ENV, key: value}, env_file=None)
    assert key in str(exc.value)
    assert FAKE_KEY not in str(exc.value)


def test_blank_fallback_is_none() -> None:
    s = load_settings({**ENV, "LLM_FALLBACK_MODEL": "  "}, env_file=None)
    assert s.fallback_model is None
