"""배포 확인 스크립트 (docs/DEPLOY.md). 표준 라이브러리만 쓴다 (새 의존성 없음).

사용:
    python scripts/smoke_deploy.py https://<배포 주소>
    python scripts/smoke_deploy.py https://<배포 주소> --analyze   # 문장 분석 1회 (Gemini 호출 1건)

확인:
1. GET /healthz → {"status": "ok"}
2. GET /api/config → analyze_enabled(bool), survey_url(str|null), enabled_features(list[str])
2-1. 세탁 Set 일부 손상 (승인 L4 입력, 2026-11-15): enabled_features에 set_partial이 없으면 ❔
     SET_PARTIAL_UNSUPPORTED, 있으면 🔍 DECISION_SENSITIVE 136,500~210,000 (L4 재승인 값)
2-2. 가전 (승인 케이스 A-1, 2026-11-15): enabled_features에 appliance가 없으면 item=appliance가 422,
     있으면 ✅ 920,000 (docs/sources/appliance_cases.md A-1)
2-3. 제시액 차액·다음 행동 (승인 N2, 2026-11-16, MVP_SPEC 14절): offer_gap이 켜져 있으면 결과에
     offer_gap(240,000~340,000원, 최솟값보다 40,000원 적음)과 표시 한 줄, 꺼져 있으면 키가 없다.
     next_steps가 켜져 있으면 /api/guide에 다음 행동(채널 3곳·체크리스트), 꺼져 있으면 키가 없다.
2-4. GET /api/sources/art5_1 → 200 조항 원문, /api/sources/no_such_clause → 404 (플래그 없음)
3. POST /api/calculate 승인 케이스 3건 (✅ C1, ⚠️ N2, 🔍 P1) → 배지와 환급액이 승인값과 같은지
4. POST /api/guide (같은 3건) → 문안에 승인 금액이 있고, 고지 한 줄이 있는지
5. (--analyze만) POST /api/analyze 문장 1개 → 200(추출) 또는 안내 코드(꺼짐·상한·한도).
   200이면 enabled_features에 rag가 있을 때 응답에 clauses{candidates, selected}(후보 5개 이하, selected ⊆ candidates),
   없을 때 clauses 키가 없는지 본다 (MVP_SPEC 15.2, 2026-11-16).
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

# 승인 L4 (세탁, 2026-11-10)와 R2 재승인 L4 (2026-11-15). 기대값은 docs/sources/laundry_cases_draft.md L4
L4_COMMON: dict[str, Any] = {
    "judgment_requested": False, "service_type": "laundry_shop", "damage_type": "defect",
    "item_key": "womens_suit", "variant_key": "spring_fall", "purchase_price": 300_000,
    "purchase_date": "2026-02-22", "request_date": "2026-09-10", "proof_available": True,
    "set_type": "top_bottom",
}  # fmt: skip
L4_OFF = {**L4_COMMON, "set_part": "top"}
L4_ON = {**L4_COMMON, "damaged_parts": ["top"], "set_partial_request": False}

# 가전 승인 케이스 A-1 (docs/sources/appliance_cases.md, 2026-11-15)
APPLIANCE_A1: dict[str, Any] = {
    "judgment_requested": False, "item_key": "tv", "purchase_price": 1_200_000,
    "purchase_date": "2022-03-15", "request_date": "2025-03-15",
    "manufacture_date": "2022-01-10", "parts_unavailable": True, "certificate_confirmed": True,
}  # fmt: skip

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


def check_appliance(base: str, c: Checker, on: bool) -> None:
    """가전 (승인 A-1). 꺼져 있으면 item=appliance가 422여야 한다."""
    status, data = request(base, "POST", "/api/calculate?item=appliance", APPLIANCE_A1)
    if on:
        r = data.get("result", {}) if isinstance(data, dict) else {}
        ok = (
            status == 200
            and r.get("badge") == "✅ 기준 확인"
            and r.get("amount") == 920_000
        )
        c.check("POST /api/calculate 가전 A-1 (켜짐 ✅ 920,000)", ok, f"HTTP {status}")
    else:
        c.check("POST /api/calculate 가전 (꺼짐 422)", status == 422, f"HTTP {status}")


def check_set_partial(base: str, c: Checker, on: bool) -> None:
    """세탁 Set 일부 손상 (승인 L4 입력). 플래그에 따라 기대값이 다르다."""
    path = "/api/calculate?item=laundry"
    if on:
        status, data = request(base, "POST", path, L4_ON)
        r = data.get("result", {}) if isinstance(data, dict) else {}
        ok = status == 200 and r.get("flags") == ["DECISION_SENSITIVE"]
        ok = ok and (r.get("sensitivity_min"), r.get("sensitivity_max")) == (
            136_500,
            210_000,
        )
        c.check("POST /api/calculate 세탁 L4 (Set 일부, 켜짐 🔍)", ok, f"HTTP {status}")
    else:
        status, data = request(base, "POST", path, L4_OFF)
        r = data.get("result", {}) if isinstance(data, dict) else {}
        ok = status == 200 and r.get("flags") == ["SET_PARTIAL_UNSUPPORTED"]
        c.check("POST /api/calculate 세탁 L4 (Set 일부, 꺼짐 ❔)", ok, f"HTTP {status}")


# 승인 N2의 차액 (승인 B 240,000 · A 340,000, 제시액 200,000에서 정수 뺄셈, docs/sources/offer_gap_cases.md)
N2_OFFER_GAP = {
    "offer": 200_000, "reference_min": 240_000, "reference_max": 340_000,
    "gap_to_min": 40_000, "gap_to_max": -140_000, "direction": "below_min",
}  # fmt: skip
NEXT_STEPS_CHANNELS = ["ccn_1372", "kca_relief", "klac_132"]


def check_offer_gap_next_steps(base: str, c: Checker, features: list[str]) -> None:
    """제시액 차액(offer_gap)·다음 행동(next_steps). 꺼져 있으면 응답에 새 키가 없어야 한다."""
    body = CASES[1]["body"]  # N2
    status, data = request(base, "POST", "/api/calculate", body)
    r = data.get("result", {}) if isinstance(data, dict) else {}
    d = data.get("display", {}) if isinstance(data, dict) else {}
    if "offer_gap" in features:
        ok = status == 200 and r.get("offer_gap") == N2_OFFER_GAP
        ok = ok and "40,000원 적습니다" in (d.get("offer_gap_text") or "")
        c.check("POST /api/calculate N2 차액 (켜짐)", ok, f"HTTP {status}")
    else:
        ok = status == 200 and "offer_gap" not in r and "offer_gap_text" not in d
        c.check("POST /api/calculate N2 차액 (꺼짐, 키 없음)", ok, f"HTTP {status}")
    status, data = request(base, "POST", "/api/guide", body)
    ns = data.get("next_steps") if isinstance(data, dict) else None
    if "next_steps" in features:
        ok = status == 200 and isinstance(ns, dict)
        ok = ok and [x.get("id") for x in ns.get("channels", [])] == NEXT_STEPS_CHANNELS
        ok = ok and bool(ns.get("checklist"))
        c.check("POST /api/guide N2 다음 행동 (켜짐)", ok, f"HTTP {status}")
    else:
        ok = status == 200 and isinstance(data, dict) and "next_steps" not in data
        c.check("POST /api/guide N2 다음 행동 (꺼짐, 키 없음)", ok, f"HTTP {status}")


def check_sources(base: str, c: Checker) -> None:
    status, data = request(base, "GET", "/api/sources/art5_1")
    ok = status == 200 and isinstance(data, dict) and bool(data.get("text"))
    ok = ok and isinstance(data.get("verified"), bool)
    c.check("GET /api/sources/art5_1", ok, f"HTTP {status}")
    status, _ = request(base, "GET", "/api/sources/no_such_clause")
    c.check("GET /api/sources (없는 ID 404)", status == 404, f"HTTP {status}")


def check_clauses(c: Checker, data: dict[str, Any], rag: bool) -> None:
    """문장 분석 응답의 조항 후보 (rag). 꺼져 있으면 키가 없어야 한다."""
    clauses = data.get("clauses")
    if not rag:
        c.check(
            "POST /api/analyze 조항 후보 (rag 꺼짐, 키 없음)", "clauses" not in data
        )
        return
    ok = isinstance(clauses, dict)
    if ok:
        cand = [x.get("clause_id") for x in clauses.get("candidates", [])]
        sel = [x.get("clause_id") for x in clauses.get("selected", [])]
        ok = len(cand) <= 5 and set(sel) <= set(cand)
        print(f"    조항 후보 {cand}, 고른 조항 {sel}")
    c.check("POST /api/analyze 조항 후보 (rag 켜짐)", ok)


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
        and set(data) == {"analyze_enabled", "survey_url", "enabled_features"}
        and isinstance(data["analyze_enabled"], bool)
        and isinstance(data["enabled_features"], list)
    )
    c.check("GET /api/config", ok, f"HTTP {status}")
    features: list[str] = []
    if ok:
        features = data["enabled_features"]
        print(
            f"    analyze_enabled={data['analyze_enabled']}, "
            f"survey_url={'있음' if data['survey_url'] else '없음'}, "
            f"enabled_features={features}"
        )
    check_set_partial(base, c, "set_partial" in features)
    check_appliance(base, c, "appliance" in features)
    check_offer_gap_next_steps(base, c, features)
    check_sources(base, c)

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
            check_clauses(c, data, "rag" in features)
        else:
            c.check(
                "POST /api/analyze (안내 코드)",
                code in ANALYZE_NOTICE_CODES,
                f"HTTP {status}, code={code}",
            )
            print(f"    HTTP {status}, code={code} (폼 입력은 계속 쓸 수 있어야 한다)")

    print(f"\n실패 {c.failed}건" if c.failed else "\n모두 통과")
    return 1 if c.failed else 0


def configure_stdio() -> None:
    """stdout·stderr를 UTF-8(errors="replace")로 맞춘다.

    Windows 콘솔·파이프의 기본 인코딩(cp949)은 배지 기호(✅·⚠️)를 인코딩하지 못해
    print에서 UnicodeEncodeError로 멈춘다. reconfigure가 없는 스트림은 그대로 둔다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    configure_stdio()
    parser = argparse.ArgumentParser(description="기준대로 배포 확인")
    parser.add_argument("base_url", help="배포 주소 (예: https://example.onrender.com)")
    parser.add_argument(
        "--analyze", action="store_true", help="문장 분석 1회 확인 (Gemini 호출 1건)"
    )
    args = parser.parse_args()
    sys.exit(run(args.base_url, args.analyze))


if __name__ == "__main__":
    main()
