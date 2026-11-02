"""범위 판정 테스트 (MVP_SPEC 5.2 판정 순서 1~11, 5.1 입력 검증)."""

from datetime import date
from typing import Any

import pytest

from rules.badge import FlagCode as F
from rules.gym import Basis, GymInput, ScopeResult, check_scope, resolve_basis
from rules.loader import load_rule

RULE = load_rule("gym_refund")

# C1 입력(사용자 승인 케이스)을 바탕으로 한 유효한 기간제 입력
BASE: dict[str, Any] = {
    "judgment_requested": False,
    "industry": "fitness",
    "termination_cause": "consumer",
    "contract_type": "period",
    "total_contract_amount": 600_000,
    "paid_amount": 600_000,
    "start_date": date(2026, 3, 1),
    "end_date": date(2026, 8, 31),
    "notice_date": date(2026, 2, 20),
    "has_refund_limit_clause": True,
    "list_price": 600_000,
    "withdrawal_cleared": True,
}

# V3 입력(사용자 승인 케이스)을 바탕으로 한 유효한 요가·필라테스 횟수제 입력
SESSION: dict[str, Any] = {
    "judgment_requested": False,
    "industry": "yoga_pilates",
    "termination_cause": "consumer",
    "contract_type": "session",
    "refund_basis": "session",
    "total_contract_amount": 500_000,
    "paid_amount": 500_000,
    "start_date": date(2026, 3, 1),
    "end_date": date(2026, 5, 31),
    "notice_date": date(2026, 5, 31),
    "total_sessions": 20,
    "used_sessions": 15,
    "has_refund_limit_clause": True,
}


def scope(base: dict[str, Any] = BASE, **changes: Any) -> ScopeResult:
    return check_scope(GymInput(**{**base, **changes}), RULE)


def test_valid_inputs_pass() -> None:
    assert scope().stop_code is None
    assert scope(SESSION).stop_code is None


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"judgment_requested": True}, F.JUDGMENT_REQUESTED),  # 순서 1
        ({"industry": "swimming_pool"}, F.UNSUPPORTED_INDUSTRY),  # 순서 2
        ({"industry": "beauty"}, F.UNSUPPORTED_INDUSTRY),
        ({"academy_law_applies": True}, F.ACADEMY_LAW),  # 순서 3
        ({"is_withdrawal": True}, F.WITHDRAWAL),  # 순서 4
        ({"termination_cause": "business"}, F.BUSINESS_FAULT),  # 순서 5
        ({"termination_cause": "force_majeure"}, F.FORCE_MAJEURE),  # 순서 6
        ({"end_date": date(2026, 3, 27)}, F.PERIOD_UNDER_28_DAYS),  # 순서 7 (27일)
        ({"has_refund_limit_clause": False}, F.NO_REFUND_LIMIT_CLAUSE),  # 순서 8
        ({"termination_cause": "unknown"}, F.MISSING_REQUIRED),  # 순서 9
        ({"end_date": None}, F.MISSING_REQUIRED),
        ({"paid_amount": 600_001}, F.INVALID_INPUT),  # 순서 10
    ],
)
def test_each_row(changes: dict[str, Any], code: F) -> None:
    """5.2 표의 행마다 해당 코드에서 멈춘다."""
    assert scope(**changes).stop_code == code


def test_row_11_notice_after_validity() -> None:
    """순서 11: 횟수 기준에서 도달일 > 유효기간 종료일이면 계산 안 함 (V1)."""
    assert (
        scope(SESSION, notice_date=date(2026, 6, 1)).stop_code
        == F.NOTICE_AFTER_VALIDITY
    )


def test_row_11_same_day_passes() -> None:
    """도달일 = 유효기간 종료일이면 계산한다 (V3)."""
    assert scope(SESSION).stop_code is None


def test_row_11_not_for_period_basis() -> None:
    """기간 기준은 종료일 이후 도달이어도 순서 11을 적용하지 않는다 (X1)."""
    assert scope(notice_date=date(2026, 10, 1)).stop_code is None


def test_row_11_unknown_basis_stops_all() -> None:
    """요가·필라테스 환급 기준 unknown이면 기간 기준도 계산하지 않는다 (V4)."""
    result = scope(SESSION, refund_basis="unknown", notice_date=date(2026, 6, 1))
    assert result.stop_code == F.NOTICE_AFTER_VALIDITY


@pytest.mark.parametrize(
    ("end", "code"),
    [
        (date(2026, 3, 27), F.PERIOD_UNDER_28_DAYS),  # B1: 27일
        (date(2026, 3, 28), None),  # 28일 → 계산 (🔍 사유)
        (date(2026, 3, 31), None),  # B3: 31일
        (date(2026, 4, 1), None),  # B4: 32일
        (date(2026, 3, 1), F.PERIOD_UNDER_28_DAYS),  # 종료일 = 시작일 (유효, 1일)
        (
            date(2026, 2, 28),
            F.INVALID_INPUT,
        ),  # 종료일이 시작일보다 하루 이름 → 입력 오류
    ],
)
def test_period_boundaries(end: date, code: F | None) -> None:
    """계속거래 기간 경계와 날짜 역전 (5.2 순서 7·10)."""
    assert scope(notice_date=date(2026, 3, 10), end_date=end).stop_code == code


@pytest.mark.parametrize(
    ("end", "period_class"),
    [
        (date(2026, 3, 28), "needs_review"),
        (date(2026, 3, 31), "needs_review"),
        (date(2026, 4, 1), "ok"),
    ],
)
def test_period_class_reported(end: date, period_class: str) -> None:
    assert scope(end_date=end).period_class == period_class


def test_session_validity_under_28_days_is_out_of_scope() -> None:
    """횟수제 유효기간에도 순서 7을 적용한다 (Q7)."""
    result = scope(SESSION, end_date=date(2026, 3, 20), notice_date=date(2026, 3, 10))
    assert result.stop_code == F.PERIOD_UNDER_28_DAYS


def test_precedence() -> None:
    """먼저 걸리는 것이 이긴다."""
    assert (
        scope(judgment_requested=True, industry="x").stop_code == F.JUDGMENT_REQUESTED
    )
    assert scope(industry="x", is_withdrawal=True).stop_code == F.UNSUPPORTED_INDUSTRY
    assert scope(is_withdrawal=True, end_date=None).stop_code == F.WITHDRAWAL
    assert scope(end_date=None, paid_amount=700_000).stop_code == F.MISSING_REQUIRED
    assert (
        scope(SESSION, paid_amount=700_000, notice_date=date(2026, 6, 1)).stop_code
        == F.INVALID_INPUT
    )


@pytest.mark.parametrize(
    ("base", "changes", "missing"),
    [
        (BASE, {"end_date": None}, ["end_date"]),  # M1과 같은 상황
        (
            BASE,
            {"start_date": None, "notice_date": None},
            ["start_date", "notice_date"],
        ),
        (BASE, {"termination_cause": "unknown"}, ["termination_cause"]),
        (SESSION, {"used_sessions": None}, ["used_sessions"]),
        (
            SESSION,
            {"notice_date": None},
            ["notice_date"],
        ),  # 유효기간 종료일이 있으면 필수
        (
            SESSION,
            {"refund_basis": None},
            ["refund_basis"],
        ),  # 요가·필라테스 None = 누락
        (
            BASE,
            {"add_on_value": 10_000, "add_on_returned": True},
            ["returned_add_on_value"],
        ),
        (
            SESSION,
            {"refund_basis": "unknown", "start_date": None},
            ["start_date"],
        ),  # unknown이면 기간 기준 입력도 요구
    ],
)
def test_missing_fields(
    base: dict[str, Any], changes: dict[str, Any], missing: list[str]
) -> None:
    result = scope(base, **changes)
    assert result.stop_code == F.MISSING_REQUIRED
    assert result.missing == missing


def test_session_without_end_date_needs_no_notice() -> None:
    """유효기간 종료일이 없으면 횟수 기준의 도달일은 필수가 아니다 (S3)."""
    result = scope(SESSION, start_date=None, end_date=None, notice_date=None)
    assert result.stop_code is None
    assert result.contract_days is None
    assert result.period_class == "unknown"


@pytest.mark.parametrize(
    ("base", "changes"),
    [
        (BASE, {"total_contract_amount": 0, "paid_amount": 0}),
        (BASE, {"paid_amount": -1}),
        (BASE, {"list_price": -1}),
        (BASE, {"contract_penalty": -1}),
        (BASE, {"provider_offer": -1}),
        (BASE, {"deposit": -1}),
        (BASE, {"add_on_value": -1}),
        (BASE, {"paid_amount": 600_001}),
        (SESSION, {"total_sessions": 0, "used_sessions": 0}),
        (SESSION, {"used_sessions": 21}),
        (SESSION, {"used_sessions": -1}),
        (
            BASE,
            {"add_on_value": 1, "add_on_returned": True, "returned_add_on_value": -1},
        ),
    ],
)
def test_invalid_inputs(base: dict[str, Any], changes: dict[str, Any]) -> None:
    assert scope(base, **changes).stop_code == F.INVALID_INPUT


@pytest.mark.parametrize(
    ("industry", "contract_type", "refund_basis", "expected"),
    [
        ("fitness", "period", None, "period"),
        ("fitness", "session", "period", "session"),  # 헬스는 입력과 상관없이 계약 유형
        ("yoga_pilates", "period", "session", "session"),
        ("yoga_pilates", "session", "unknown", "unknown"),
        ("yoga_pilates", "session", None, "unknown"),
    ],
)
def test_resolve_basis(
    industry: str, contract_type: str, refund_basis: str | None, expected: str
) -> None:
    inp = GymInput(
        **{
            **BASE,
            "industry": industry,
            "contract_type": contract_type,
            "refund_basis": refund_basis,
        }
    )
    assert resolve_basis(inp) == expected


def test_bases_for_unknown() -> None:
    result = scope(SESSION, refund_basis="unknown")
    assert result.bases == [Basis.PERIOD, Basis.SESSION]
