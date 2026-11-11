"""배포 확인 스크립트 (docs/DEPLOY.md). 표준 라이브러리만 쓴다 (새 의존성 없음).

사용:
    python scripts/smoke_deploy.py https://<배포 주소>
    python scripts/smoke_deploy.py https://<배포 주소> --analyze   # 문장 분석 1회 (Gemini 호출 1건)

확인:
1. GET /healthz → {"status": "ok"}
2. GET /api/config → analyze_enabled(bool), survey_url(str|null)
3. POST /api/calculate 승인 케이스 3건 (✅ C1, ⚠️ N2, 🔍 P1) → 배지와 환급액이 승인값과 같은지
4. POST /api/guide (같은 3건) → 문안에 승인 금액이 있고, 고지 한 줄이 있는지
5. (--analyze만) POST /api/analyze 문장 1개 → 200(추출) 또는 안내 코드(꺼짐·상한·한도)
기대값은 docs/sources/gym_cases_draft.md의 승인 케이스 값 그대로다 (backend/tests/test_gym_calc.py와 같음).
--analyze는 실제 Gemini 호출 1건을 쓴다. 키는 이 스크립트에 넣지 않는다 (서버 환경변수에만 있음).
응답 본문은 출력하지 않고 통과·실패와 필드 이름만 출력한다.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

TIMEOUT = 60  # 무료 호스트가 잠들어 있으면 첫 요청이 느리다

DISCLAIMER_LINE = "참고용이며 법률 자문이 아닙니다."

# 승인 케이스 (사용자 승인(보고서 검토) C1·N2, 사용자 검증 완료 P1)
CASES: list[dict[str, Any]] = [
    {
        "id": "C1",
        "badge": "✅ 기준 확인",
        "refunds": {"period": (540_000, 540_000)},  # (A 환급액, B 환급액)
        "body": {
            "judgment_requested": False, "industry": "fitness", "withdrawal_cleared": True,
            "termination_cause": "consumer", "contract_type": "period",
            "total_contract_amount": 600_000, "paid_amount": 600_000,
            "start_date": "2026-03-01", "end_date": "2026-08-31", "notice_date": "2026-02-20",
            "has_refund_limit_clause": True, "list_price": 600_000, "had_postponement": False,
        },
    },
    {
        "id": "N2",
        "badge": "⚠️ 주의 신호",
        "refunds": {"session": (340_000, 240_000)},
        "body": {
            "judgment_requested": False, "industry": "yoga_pilates",
            "termination_cause": "consumer", "contract_type": "session",
            "refund_basis": "session", "total_contract_amount": 600_000,
            "paid_amount": 600_000, "start_date": "2026-03-01", "end_date": "2026-08-31",
            "notice_date": "2026-05-01", "total_sessions": 30, "used_sessions": 10,
            "has_refund_limit_clause": True, "list_price": 900_000,
            "provider_offer": 200_000, "had_postponement": False,
        },
    },
    {
        "id": "P1",
        "badge": "🔍 추가 확인 필요",
        "refunds": {"period": (784_110, None)},
        "body": {
            "judgment_requested": False, "industry": "fitness",
            "termination_cause": "consumer", "contract_type": "period",
            "total_contract_amount": 1_200_000, "paid_amount": 1_200_000,
            "start_date": "2026-01-01", "end_date": "2026-12-31", "notice_date": "2026-03-31",
            "has_refund_limit_clause": True, "had_postponement": False,
        },
    },
]  # fmt: skip

ANALYZE_TEXT = (
    "헬스장 1년권을 2026년 1월 1일부터 2026년 12월 31일까지 쓰기로 하고 "
    "120만원을 결제했는데, 2026년 3월 31일에 해지하겠다고 문자를 보냈어요."
)
ANALYZE_NOTICE_CODES = {"ANALYZE_DISABLED", "ANALYZE_DAILY_LIMIT", "rate_limited"}


def request(base: str, method: str, path: str, body: Any = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"content-type": "application/json; charset=utf-8"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, None


class Checker:
    def __init__(self) -> None:
        self.failed = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        print(
            f"[{'통과' if ok else '실패'}] {name}"
            + (f" — {detail}" if detail and not ok else "")
        )
        if not ok:
            self.failed += 1


def won(n: int) -> str:
    return f"{n:,}원"


def run(base: str, analyze: bool) -> int:
    base = base.rstrip("/")
    c = Checker()

    status, data = request(base, "GET", "/healthz")
    c.check(
        "GET /healthz", status == 200 and data == {"status": "ok"}, f"HTTP {status}"
    )

    status, data = request(base, "GET", "/api/config")
    ok = (
        status == 200
        and isinstance(data, dict)
        and set(data) == {"analyze_enabled", "survey_url"}
        and isinstance(data["analyze_enabled"], bool)
    )
    c.check("GET /api/config", ok, f"HTTP {status}")
    if ok:
        print(
            f"    analyze_enabled={data['analyze_enabled']}, "
            f"survey_url={'있음' if data['survey_url'] else '없음'}"
        )

    for case in CASES:
        status, data = request(base, "POST", "/api/calculate", case["body"])
        ok = status == 200 and data["result"]["badge"] == case["badge"]
        if ok:
            for basis, (a, b) in case["refunds"].items():
                got = data["result"]["results"][basis]
                ok = ok and got["A"]["refund"] == a
                ok = ok and (got["B"]["refund"] if got["B"] else None) == b
        c.check(
            f"POST /api/calculate {case['id']} ({case['badge']})", ok, f"HTTP {status}"
        )

        status, data = request(base, "POST", "/api/guide", case["body"])
        ok = status == 200 and isinstance(data, dict)
        if ok:
            text = "\n".join(data["explanation"])
            amounts = [
                v for pair in case["refunds"].values() for v in pair if v is not None
            ]
            ok = all(won(v) in text for v in amounts)
            ok = ok and DISCLAIMER_LINE in data["explanation"]
            ok = ok and data["company_message"] is not None
            ok = ok and bool(data["citations"])
        c.check(f"POST /api/guide {case['id']}", ok, f"HTTP {status}")

    if analyze:
        status, data = request(base, "POST", "/api/analyze", {"text": ANALYZE_TEXT})
        code = data.get("code") if isinstance(data, dict) else None
        if status == 200:
            c.check("POST /api/analyze (추출)", data.get("status") == "extracted")
            if data.get("extraction"):
                print(f"    채운 항목: {sorted(data['extraction'].get('fields', {}))}")
        else:
            c.check(
                "POST /api/analyze (안내 코드)",
                code in ANALYZE_NOTICE_CODES,
                f"HTTP {status}, code={code}",
            )
            print(f"    HTTP {status}, code={code} (폼 입력은 계속 쓸 수 있어야 한다)")

    print(f"\n실패 {c.failed}건" if c.failed else "\n모두 통과")
    return 1 if c.failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="기준대로 배포 확인")
    parser.add_argument("base_url", help="배포 주소 (예: https://example.onrender.com)")
    parser.add_argument(
        "--analyze", action="store_true", help="문장 분석 1회 확인 (Gemini 호출 1건)"
    )
    args = parser.parse_args()
    sys.exit(run(args.base_url, args.analyze))


if __name__ == "__main__":
    main()
