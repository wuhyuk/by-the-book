"""배포 파일 점검 (2026-11-12): 의존성 고정 파일, .dockerignore, Dockerfile.

이미지를 빌드하지 않고 파일 내용만 본다 (빌드 확인은 docs/DEPLOY.md 절차).
"""

import re
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def lock_names() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in (BACKEND / "requirements.lock").read_text("utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, _, version = line.partition("==")
            assert version, f"버전 고정이 없음: {line}"
            pins[_norm(name)] = version
    return pins


def test_lock_covers_pyproject_dependencies() -> None:
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text("utf-8"))
    deps = project["project"]["dependencies"]
    names = {_norm(re.split(r"[<>=!~\[ ]", d, maxsplit=1)[0]) for d in deps}
    assert names <= set(lock_names())


def test_dockerignore_excludes_secrets_and_artifacts() -> None:
    lines = set((ROOT / ".dockerignore").read_text("utf-8").splitlines())
    for pattern in [
        "**/.env",
        "**/.env.*",
        ".git",
        "**/.venv",
        "**/node_modules",
        "**/__pycache__",
        "**/.pytest_cache",
    ]:
        assert pattern in lines, pattern


def test_dockerfile_basics() -> None:
    text = (ROOT / "Dockerfile").read_text("utf-8")
    assert text.count("FROM ") == 2  # Node 빌드 → Python 런타임
    assert re.search(r"^USER (?!root)\S+", text, re.MULTILINE)  # 비루트
    assert "${PORT:-8000}" in text
    assert not re.search(r"^(COPY|ADD)\b.*\.env", text, re.MULTILINE)  # .env 복사 없음
    assert "COPY --from=web /app/frontend/dist /app/frontend/dist" in text
