"""LLM 설정 읽기 테스트. 실제 backend/.env는 읽지 않는다 (env_file=None 또는 tmp 파일, 가짜 키)."""

from pathlib import Path

import pytest

from llm.config import LLMConfigError, LLMSettings, load_settings, read_env_file

FAKE_KEY = "FAKE-KEY-ZQX-0000"
ENV = {"LLM_PROVIDER": "gemini", "LLM_API_KEY": FAKE_KEY, "LLM_MODEL": "model-a"}


def test_load_from_environ() -> None:
    s = load_settings(ENV, env_file=None)
    assert s.provider == "gemini"
    assert s.model == "model-a"
    assert s.api_key.get_secret_value() == FAKE_KEY


def test_key_hidden_in_repr_and_str() -> None:
    s = load_settings(ENV, env_file=None)
    for text in (repr(s), str(s), repr(s.api_key), str(s.api_key), s.model_dump_json()):
        assert FAKE_KEY not in text


@pytest.mark.parametrize("empty", ["LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL"])
def test_missing_value_error_names_only(empty: str) -> None:
    env = {**ENV, empty: ""}
    with pytest.raises(LLMConfigError) as exc:
        load_settings(env, env_file=None)
    assert empty in str(exc.value)
    assert FAKE_KEY not in str(exc.value)


def test_unsupported_provider() -> None:
    with pytest.raises(LLMConfigError) as exc:
        load_settings({**ENV, "LLM_PROVIDER": "other"}, env_file=None)
    assert FAKE_KEY not in str(exc.value)
    assert "other" not in str(exc.value)


def test_env_file_parsing(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text(
        "# 주석\n"
        'LLM_PROVIDER="gemini"\n'
        f"export LLM_API_KEY='{FAKE_KEY}'\n"
        "LLM_MODEL = model-b\n"
        "OTHER_SECRET=should-not-be-read\n",
        encoding="utf-8",
    )
    values = read_env_file(f)
    assert values == {
        "LLM_PROVIDER": "gemini",
        "LLM_API_KEY": FAKE_KEY,
        "LLM_MODEL": "model-b",
    }
    s = load_settings({}, env_file=f)
    assert s.model == "model-b"


def test_environ_overrides_file(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text("LLM_MODEL=from-file\n", encoding="utf-8")
    s = load_settings({**ENV, "LLM_MODEL": "from-env"}, env_file=f)
    assert s.model == "from-env"


def test_missing_env_file_is_empty(tmp_path: Path) -> None:
    assert read_env_file(tmp_path / "none.env") == {}


def test_settings_model_forbids_extra() -> None:
    with pytest.raises(ValueError):
        LLMSettings(provider="gemini", api_key=FAKE_KEY, model="m", extra=1)  # type: ignore[call-arg]
