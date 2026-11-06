"""VS2 관통 확인: Vite 프록시 → /api/calculate → 응답을 승인 케이스 기대값과 비교한다.

사용 (저장소 루트, 백엔드·프론트 개발 서버를 먼저 띄운 뒤):
    backend/.venv/Scripts/python eval/vs2_walkthrough.py            # 기본 http://localhost:5173
    backend/.venv/Scripts/python eval/vs2_walkthrough.py --base-url http://127.0.0.1:8000
    backend/.venv/Scripts/python eval/vs2_walkthrough.py --checklist # 사람이 화면에서 확인할 표

케이스는 backend/tests/test_gym_calc.CASES(사용자 검증 완료·사용자 승인)에서 고른 가상 사례 5건이다.
기대값을 새로 만들지 않는다: 배지·사유 코드·금액은 케이스 기대값, 화면 문구는 엔진+표시 모듈 결과와 비교한다.
입력값과 응답 본문은 출력하지 않는다 (케이스 ID와 비교 결과만).
"""

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend" / "tests")]

from rules.gym import calculate_refund
from rules.gym_display import build_display
from rules.loader import load_rule

# 승인 케이스 모듈 (backend/tests). 경로를 위에서 넣으므로 import 정렬 대상에서 뺀다.
_cases = importlib.import_module("test_gym_calc")
CASES = _cases.CASES
Case = _cases.Case

# 고른 이유: ✅ / 🔍(기본) / ⚠️ / 두 기준 묶음(요가·필라테스 모름) / ❔(상담 창구)
WALKTHROUGH_IDS = ("C1", "P1", "K1", "U1", "B1")
BASIS_LABEL = {"period": "일수 기준", "session": "횟수 기준"}


def pick(case_id: str) -> Case:
    return next(c for c in CASES if c.id == case_id)


def expected_amounts(c: Case) -> dict[str, tuple[int, int | None]]:
    """케이스 기대값의 기준별 (A 환급액, B 환급액)."""
    if not c.exp.results:
        return {}
    return {
        b.value: (a[1], bb[1] if bb else None)
        for b, (_, _, a, bb) in c.exp.results.items()
    }


def got_amounts(result: dict[str, Any]) -> dict[str, tuple[int, int | None]]:
    return {
        b: (r["A"]["refund"], r["B"]["refund"] if r["B"] else None)
        for b, r in result["results"].items()
    }


def check(client: httpx.Client, c: Case) -> list[str]:
    """케이스 하나를 API로 보내 다른 점 목록을 돌려준다 (없으면 통과)."""
    rule = load_rule("gym_refund")
    response = client.post("/api/calculate", json=c.inp.model_dump(mode="json"))
    if response.status_code != 200:
        return [f"HTTP {response.status_code}"]
    data = response.json()
    result, display = data["result"], data["display"]
    problems: list[str] = []
    if result["badge"] != c.exp.badge.value:
        problems.append("배지")
    if set(result["flags"]) != {f.value for f in c.exp.flags}:
        problems.append("사유 코드")
    top = c.exp.top.value if c.exp.top else None
    if (display["screen_line"] or {}).get("code") != top:
        problems.append("화면 한 줄 코드")
    if result["calculated"] is not c.exp.calculated:
        problems.append("계산 여부")
    if got_amounts(result) != expected_amounts(c):
        problems.append("환급액")
    engine = calculate_refund(c.inp, rule)
    if display != build_display(engine, rule).model_dump(mode="json"):
        problems.append("화면 문구")
    return problems


def checklist() -> str:
    """사람이 브라우저에서 확인할 표 (기대값은 케이스 기대값·표시 모듈 결과)."""
    rule = load_rule("gym_refund")
    lines = [
        "| 케이스 | 배지 | 화면 한 줄 | 금액 (기준별 A / B) | 상담 창구 |",
        "|---|---|---|---|---|",
    ]
    for cid in WALKTHROUGH_IDS:
        c = pick(cid)
        d = build_display(calculate_refund(c.inp, rule), rule)
        amounts = "; ".join(
            f"{BASIS_LABEL[b]} {a:,}원 / {'계산하지 않음' if bb is None else f'{bb:,}원'}"
            for b, (a, bb) in expected_amounts(c).items()
        )
        lines.append(
            f"| {cid} | {c.exp.badge.value} | {d.screen_line.text if d.screen_line else '(없음)'} "
            f"| {amounts or '(계산 안 함)'} | {'표시' if d.consult else '없음'} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:5173")
    parser.add_argument("--checklist", action="store_true")
    args = parser.parse_args()
    if args.checklist:
        print(checklist())
        return 0
    failed = 0
    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        for cid in WALKTHROUGH_IDS:
            problems = check(client, pick(cid))
            failed += bool(problems)
            print(
                f"{cid}: {'통과' if not problems else '다름 - ' + ', '.join(problems)}"
            )
    print(f"{len(WALKTHROUGH_IDS) - failed}/{len(WALKTHROUGH_IDS)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
