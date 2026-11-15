"""배포 확인 스크립트(scripts/smoke_deploy.py)의 출력 인코딩 (2026-11-13).

Windows 콘솔·파이프 기본 인코딩(cp949)에서는 배지 기호(✅·⚠️)를 print하다 멈췄다.
PYTHONIOENCODING=cp949로 그 환경을 재현하고, configure_stdio() 뒤에는 멈추지 않는지 본다.
서버에 요청하지 않는다 (출력 부분은 하위 프로세스, 플래그 확인은 TestClient로 앱을 직접 부른다).
"""

import io
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

PRINT_BADGES = """
import sys
sys.path.insert(0, {scripts!r})
import smoke_deploy
if {configure}:
    smoke_deploy.configure_stdio()
c = smoke_deploy.Checker()
for case in smoke_deploy.CASES:
    c.check(f"POST /api/calculate {{case['id']}} ({{case['badge']}})", True)
print("한글 출력", file=sys.stderr)
"""


def _run(configure: bool) -> subprocess.CompletedProcess[bytes]:
    code = PRINT_BADGES.format(scripts=str(SCRIPTS), configure=configure)
    env = {**os.environ, "PYTHONIOENCODING": "cp949", "PYTHONUTF8": "0"}
    return subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        env=env,
        timeout=60,
    )


def test_cp949_console_crashes_without_configure() -> None:
    """대조군: 설정하지 않으면 cp949에서 배지 출력이 실패한다 (재현 확인)."""
    proc = _run(configure=False)
    assert proc.returncode != 0
    assert b"UnicodeEncodeError" in proc.stderr


def test_configure_stdio_prints_badges_on_cp949() -> None:
    proc = _run(configure=True)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    out = proc.stdout.decode("utf-8")
    for badge in ["✅ 기준 확인", "⚠️ 주의 신호", "🔍 추가 확인 필요"]:
        assert f"({badge})" in out
    assert "한글 출력" in proc.stderr.decode("utf-8")


def test_main_configures_stdio_first() -> None:
    """main()이 인자 처리보다 먼저 configure_stdio()를 부른다."""
    source = (SCRIPTS / "smoke_deploy.py").read_text("utf-8")
    body = source.split("def main() -> None:", 1)[1]
    first = next(line.strip() for line in body.splitlines() if line.strip())
    assert first == "configure_stdio()"


# ---- 기능 플래그 켜짐/꺼짐 (ENABLED_FEATURES, 2026-11-15) ----
# 배포 서버 대신 앱을 TestClient로 불러 스크립트의 확인 전체(run)가 통과하는지 본다.


def _run_against_app(
    monkeypatch: pytest.MonkeyPatch, features: tuple[str, ...]
) -> tuple[int, str]:
    sys.path.insert(0, str(SCRIPTS))
    import smoke_deploy

    from api.settings import AppSettings, get_app_settings
    from main import app

    client = TestClient(app)

    def fake_request(base: str, method: str, path: str, body: Any = None) -> Any:
        res = client.request(method, path, json=body)
        return res.status_code, res.json()

    monkeypatch.setattr(smoke_deploy, "request", fake_request)
    app.dependency_overrides[get_app_settings] = lambda: AppSettings(
        analyze_enabled=False, enabled_features=features
    )
    out = io.StringIO()
    try:
        monkeypatch.setattr(sys, "stdout", out)
        code = smoke_deploy.run("http://test", analyze=False)
    finally:
        app.dependency_overrides.pop(get_app_settings, None)
    return code, out.getvalue()


def test_smoke_passes_with_set_partial_off(monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = _run_against_app(monkeypatch, ())
    assert code == 0, out
    assert "세탁 L4 (Set 일부, 꺼짐 ❔)" in out


def test_smoke_passes_with_set_partial_on(monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = _run_against_app(monkeypatch, ("set_partial",))
    assert code == 0, out
    assert "세탁 L4 (Set 일부, 켜짐 🔍)" in out
