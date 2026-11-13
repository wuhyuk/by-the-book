"""배포 확인 스크립트(scripts/smoke_deploy.py)의 출력 인코딩 (2026-11-13).

Windows 콘솔·파이프 기본 인코딩(cp949)에서는 배지 기호(✅·⚠️)를 print하다 멈췄다.
PYTHONIOENCODING=cp949로 그 환경을 재현하고, configure_stdio() 뒤에는 멈추지 않는지 본다.
서버에 요청하지 않는다 (출력 부분만 확인).
"""

import os
import subprocess
import sys
from pathlib import Path

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
