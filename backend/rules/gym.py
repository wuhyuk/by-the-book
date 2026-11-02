"""헬스·피트니스, 요가·필라테스 중도 해지 환급 규칙 엔진 (MVP_SPEC 5절).

순수 함수만 둔다. LLM을 호출하지 않는다. 금액은 int, 비율은 Decimal이다.
규칙 값(위약금 비율, 계속거래 기간 경계)은 규칙 JSON(GymRule)에서 읽는다.
"""

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from rules.badge import (
    NO_CALC_CODES,
    ROBUST_CODES,
    UNDETERMINABLE_CODES,
    Badge,
    FlagCode,
    NoticeCode,
    decide_badge,
    order_flags,
)
from rules.loader import GymRule
from rules.money import div_round_half_up, penalty_cap

F = FlagCode
N = NoticeCode

FITNESS = "fitness"
YOGA_PILATES = "yoga_pilates"

FIRST_STEP_TEXT = (
    "고시에는 단위대금 산정 방식이 정해져 있지 않아, "
    "실제 부담액 기준(A)과 정상가 기준(B)으로 나누어 계산했습니다."
)
ROUND_NOTE = "원 단위 반올림(고시에 규정 없음)"
FLOOR_NOTE = "원 미만 내림(고시에 규정 없음)"

PeriodClass = Literal["out_of_scope", "needs_review", "ok", "unknown"]


class Basis(StrEnum):
    """환급 기준."""

    PERIOD = "period"
    SESSION = "session"


class RefundKind(StrEnum):
    """결과 표시. minimum = 최소 환급액, computed = 환급액."""

    MINIMUM = "minimum"
    COMPUTED = "computed"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class GymInput(_Model):
    """입력 스키마 (MVP_SPEC 5.1). 필드명은 5.1 그대로다."""

    judgment_requested: bool
    industry: str
    academy_law_applies: bool = False
    is_withdrawal: bool = False
    withdrawal_cleared: bool | None = None
    termination_cause: Literal["consumer", "business", "force_majeure", "unknown"]
    contract_type: Literal["period", "session"]
    refund_basis: Literal["period", "session", "unknown"] | None = None
    total_contract_amount: int
    paid_amount: int
    start_date: date | None = None
    end_date: date | None = None
    notice_date: date | None = None
    total_sessions: int | None = None
    used_sessions: int | None = None
    add_on_value: int = 0
    add_on_returned: bool = False
    returned_add_on_value: int | None = None
    deposit: int = 0
    has_refund_limit_clause: bool | None = None
    list_price: int | None = None
    contract_penalty: int | None = None
    provider_offer: int | None = None
    had_postponement: bool | None = None
    is_pt_only: bool | None = None


class ScopeResult(_Model):
    """범위 판정 결과 (5.2). stop_code가 있으면 계산하지 않는다."""

    stop_code: FlagCode | None
    missing: list[str]
    period_class: PeriodClass
    contract_days: int | None
    bases: list[Basis]


class ScenarioResult(_Model):
    used_amount: int
    raw_refund: int
    refund: int


class BasisResult(_Model):
    elapsed: int
    units: int
    A: ScenarioResult
    B: ScenarioResult | None


class OfferComparison(_Model):
    robust: bool
    notice: NoticeCode | None


class Step(_Model):
    label: str
    formula: str
    amount: int | None


class GymResult(_Model):
    """출력 (MVP_SPEC 5.6)."""

    badge: Badge
    calculated: bool
    results: dict[Basis, BasisResult]
    penalty: int | None
    penalty_cap: int | None
    refund_kind: RefundKind | None
    deposit_refund: int
    contract_days: int | None
    steps: list[Step]
    flags: list[FlagCode]
    missing: list[str]
    notices: list[NoticeCode]
    citations: list[str]


# ---- 일수 ----


def contract_days(start: date, end: date) -> int:
    """계약 일수 = 종료일 − 시작일 + 1."""
    return (end - start).days + 1


def elapsed_days(start: date, notice: date, total_days: int) -> int:
    """경과 일수 = clamp(도달일 − 시작일 + 1, 0, 계약 일수)."""
    return min(max((notice - start).days + 1, 0), total_days)


def classify_period(days: int | None, rule: GymRule) -> PeriodClass:
    """계약 일수 판정 (5.2). 경계는 규칙 JSON의 period_thresholds_days에서 읽는다."""
    if days is None:
        return "unknown"
    t = rule.params.continuous_transaction_criteria.period_thresholds_days
    if days < t.out_of_scope_below:
        return "out_of_scope"
    if days <= t.needs_review_max:
        return "needs_review"
    return "ok"


def _valid_contract_days(inp: GymInput) -> int | None:
    """시작일·종료일이 모두 있고 역전되지 않았을 때의 계약 일수."""
    if inp.start_date is None or inp.end_date is None or inp.end_date < inp.start_date:
        return None
    return contract_days(inp.start_date, inp.end_date)


# ---- 기준 ----


def resolve_basis(inp: GymInput) -> Literal["period", "session", "unknown"]:
    """헬스·피트니스는 계약 유형, 요가·필라테스는 합의한 환급 기준 (없으면 unknown)."""
    if inp.industry == YOGA_PILATES:
        return inp.refund_basis or "unknown"
    return inp.contract_type


def _bases(inp: GymInput) -> list[Basis]:
    basis = resolve_basis(inp)
    if basis == "unknown":
        return [Basis.PERIOD, Basis.SESSION]
    return [Basis(basis)]


# ---- 범위 판정 ----


def _missing(inp: GymInput, bases: list[Basis]) -> list[str]:
    missing: set[str] = set()
    if inp.termination_cause == "unknown":
        missing.add("termination_cause")
    if inp.add_on_returned and inp.returned_add_on_value is None:
        missing.add("returned_add_on_value")
    if inp.industry == YOGA_PILATES and inp.refund_basis is None:
        # 기준을 모르면 기준별 필수 입력은 판정하지 않는다
        missing.add("refund_basis")
    else:
        if Basis.PERIOD in bases:
            for name in ("start_date", "end_date", "notice_date"):
                if getattr(inp, name) is None:
                    missing.add(name)
        if Basis.SESSION in bases:
            for name in ("total_sessions", "used_sessions"):
                if getattr(inp, name) is None:
                    missing.add(name)
            if inp.end_date is not None and inp.notice_date is None:
                missing.add("notice_date")
    order = list(GymInput.model_fields)
    return sorted(missing, key=order.index)


def _invalid(inp: GymInput) -> bool:
    amounts = (
        inp.total_contract_amount,
        inp.paid_amount,
        inp.add_on_value,
        inp.returned_add_on_value,
        inp.deposit,
        inp.list_price,
        inp.contract_penalty,
        inp.provider_offer,
    )
    if any(a is not None and a < 0 for a in amounts):
        return True
    if inp.total_contract_amount <= 0 or inp.paid_amount > inp.total_contract_amount:
        return True
    if inp.start_date and inp.end_date and inp.end_date < inp.start_date:
        return True
    if inp.total_sessions is not None and inp.total_sessions <= 0:
        return True
    if inp.used_sessions is not None:
        if inp.used_sessions < 0:
            return True
        if inp.total_sessions is not None and inp.used_sessions > inp.total_sessions:
            return True
    return False


def check_scope(inp: GymInput, rule: GymRule) -> ScopeResult:
    """MVP_SPEC 5.2 판정 순서 1~11. 먼저 걸리는 것이 이긴다."""
    bases = _bases(inp)
    days = _valid_contract_days(inp)
    period_class = classify_period(days, rule)

    def stop(code: FlagCode | None, missing: list[str] | None = None) -> ScopeResult:
        return ScopeResult(
            stop_code=code,
            missing=missing or [],
            period_class=period_class,
            contract_days=days,
            bases=bases,
        )

    if inp.judgment_requested:
        return stop(F.JUDGMENT_REQUESTED)
    if rule.industry(inp.industry) is None:
        return stop(F.UNSUPPORTED_INDUSTRY)
    if inp.academy_law_applies:
        return stop(F.ACADEMY_LAW)
    if inp.is_withdrawal:
        return stop(F.WITHDRAWAL)
    if inp.termination_cause == "business":
        return stop(F.BUSINESS_FAULT)
    if inp.termination_cause == "force_majeure":
        return stop(F.FORCE_MAJEURE)
    if period_class == "out_of_scope":
        return stop(F.PERIOD_UNDER_28_DAYS)
    if inp.has_refund_limit_clause is False:
        return stop(F.NO_REFUND_LIMIT_CLAUSE)
    missing = _missing(inp, bases)
    if missing:
        return stop(F.MISSING_REQUIRED, missing)
    if _invalid(inp):
        return stop(F.INVALID_INPUT)
    if (
        Basis.SESSION in bases
        and inp.end_date is not None
        and inp.notice_date is not None
        and inp.notice_date > inp.end_date
    ):
        return stop(F.NOTICE_AFTER_VALIDITY)
    return stop(None)


# ---- 계산 ----


def calc_penalty(
    total: int, cap: int, contract_penalty: int | None
) -> tuple[int, RefundKind]:
    """계약서상 위약금 ≤ 상한이면 그대로(환급액), 없거나 상한보다 크면 상한(최소 환급액)."""
    if contract_penalty is not None and contract_penalty <= cap:
        return contract_penalty, RefundKind.COMPUTED
    return cap, RefundKind.MINIMUM


def _units(inp: GymInput, basis: Basis) -> tuple[int, int]:
    if basis == Basis.PERIOD:
        assert inp.start_date and inp.end_date and inp.notice_date
        total_days = contract_days(inp.start_date, inp.end_date)
        return elapsed_days(inp.start_date, inp.notice_date, total_days), total_days
    assert inp.used_sessions is not None and inp.total_sessions is not None
    return inp.used_sessions, inp.total_sessions


def _scenario(
    inp: GymInput, base: int, elapsed: int, units: int, penalty: int
) -> ScenarioResult:
    used = div_round_half_up(base * elapsed, units)
    returned = inp.returned_add_on_value if inp.add_on_returned else 0
    assert returned is not None
    raw = inp.paid_amount - used - inp.add_on_value - penalty + returned
    return ScenarioResult(used_amount=used, raw_refund=raw, refund=max(raw, 0))


def calc_basis(inp: GymInput, basis: Basis, penalty: int) -> BasisResult:
    """기준 하나의 시나리오 A(총계약대금)·B(정상가, 정상가 ≥ 총계약대금일 때만)."""
    elapsed, units = _units(inp, basis)
    total = inp.total_contract_amount
    a = _scenario(inp, total, elapsed, units, penalty)
    b = None
    if inp.list_price is not None and inp.list_price >= total:
        b = _scenario(inp, inp.list_price, elapsed, units, penalty)
    return BasisResult(elapsed=elapsed, units=units, A=a, B=b)


def compare_offer(
    offer: int | None, results: dict[Basis, BasisResult]
) -> OfferComparison:
    """제시액 위치 (5.4). B 최솟값 미만이면 강건한 ⚠️, B 최솟값 이상 A 최댓값 미만이면 안내."""
    b_refunds = [r.B.refund for r in results.values() if r.B is not None]
    if offer is None or not b_refunds:
        return OfferComparison(robust=False, notice=None)
    if offer < min(b_refunds):
        return OfferComparison(robust=True, notice=None)
    if offer < max(r.A.refund for r in results.values()):
        return OfferComparison(robust=False, notice=N.OFFER_BETWEEN_A_AND_B)
    return OfferComparison(robust=False, notice=None)


def _used_amounts(results: dict[Basis, BasisResult]) -> list[int]:
    return [
        s.used_amount for r in results.values() for s in (r.A, r.B) if s is not None
    ]


def _notice_before_start(inp: GymInput) -> bool:
    return (
        inp.start_date is not None
        and inp.notice_date is not None
        and inp.notice_date < inp.start_date
    )


def _pre_start(inp: GymInput, results: dict[Basis, BasisResult]) -> bool:
    """시작 전 해지: 도달일 < 시작일이고 모든 기준의 이용분이 0."""
    return _notice_before_start(inp) and all(u == 0 for u in _used_amounts(results))


def _blocks_verified(inp: GymInput, rule: GymRule) -> bool:
    industry = rule.industry(inp.industry)
    assert industry is not None
    return (
        industry.penalty_rule.verified
        and rule.params.continuous_transaction_criteria.verified
    )


def collect_review_flags(
    inp: GymInput, rule: GymRule, results: dict[Basis, BasisResult]
) -> list[FlagCode]:
    """🔍 사유 (계산함, 5.4)."""
    flags: list[FlagCode] = []
    bases = list(results)
    pre_start = _pre_start(inp, results)
    if inp.is_pt_only is True:
        flags.append(F.SCOPE_UNCERTAIN_PT_ONLY)
    if classify_period(_valid_contract_days(inp), rule) == "needs_review":
        flags.append(F.PERIOD_28_TO_31_DAYS)
    if inp.has_refund_limit_clause is None:
        flags.append(F.REFUND_LIMIT_CLAUSE_UNKNOWN)
    if inp.withdrawal_cleared is not True:
        flags.append(F.WITHDRAWAL_STATUS_UNCONFIRMED)
    if Basis.SESSION in bases and (inp.start_date is None or inp.end_date is None):
        flags.append(F.SESSION_VALIDITY_MISSING)
    if inp.industry == YOGA_PILATES and resolve_basis(inp) == "unknown":
        flags.append(F.REFUND_BASIS_UNKNOWN)
    if not _blocks_verified(inp, rule):
        flags.append(F.RULE_UNVERIFIED)
    if inp.list_price is None:
        if not pre_start:
            flags.append(F.LIST_PRICE_NOT_USABLE)
    elif inp.list_price < inp.total_contract_amount:
        flags.append(F.LIST_PRICE_NOT_USABLE)
    if any(u > 0 for u in _used_amounts(results)):
        flags.append(F.INTERPRETATION_DEPENDENT)
    if not _notice_before_start(inp):
        flags.append(F.USAGE_STARTED)
    if inp.had_postponement is True and not pre_start:
        flags.append(F.POSTPONEMENT)
    return order_flags(flags)


def _notices(
    inp: GymInput,
    results: dict[Basis, BasisResult],
    offer: OfferComparison,
) -> list[NoticeCode]:
    """안내 코드 (5.5), 표 순서대로. 계산한 결과에만 붙인다."""
    notices: list[NoticeCode] = []
    if inp.list_price is None and not _pre_start(inp, results):
        notices.append(N.NO_LIST_PRICE)
    if inp.list_price is not None and inp.list_price < inp.total_contract_amount:
        notices.append(N.LIST_PRICE_BELOW_TOTAL)
    if offer.notice is not None:
        notices.append(offer.notice)
    if inp.contract_penalty is None:
        notices += [N.PENALTY_INPUT_MISSING, N.STANDARD_TERMS_PENALTY]
    if any(s.raw_refund < 0 for r in results.values() for s in (r.A, r.B) if s):
        notices.append(N.NEGATIVE_REFUND_ZEROED)
    if inp.had_postponement is True:
        notices.append(N.POSTPONEMENT_INPUT)
    else:
        notices.append(N.PERIOD_CHECK)
    if inp.withdrawal_cleared is not True:
        notices.append(N.WITHDRAWAL_INFO)
    return notices


_BASE_CITATIONS = (
    "art2_2",
    "art2_3",
    "art2_4",
    "art3_1",
    "art4_1",
    "annex_penalty",
    "art5_1",
    "law32_1",
)
_STANDARD_TERMS_CITATION = {
    FITNESS: "gym_terms_art8_2_def",
    YOGA_PILATES: "yoga_terms_art9_1_def",
}


def _citations(
    inp: GymInput,
    rule: GymRule,
    flags: list[FlagCode],
    notices: list[NoticeCode],
    calculated: bool,
) -> list[str]:
    """근거 조항 ID (5.7 부여 규칙)."""
    ids: list[str] = []
    if calculated:
        ids += _BASE_CITATIONS
        if inp.deposit > 0:
            ids.append("art5_2")
        if inp.add_on_returned:
            ids.append("art6_1")
        if N.STANDARD_TERMS_PENALTY in notices:
            ids.append(_STANDARD_TERMS_CITATION[inp.industry])
        if inp.industry == YOGA_PILATES:
            ids.append("yoga_terms_art9_1_def")
        if F.PERIOD_28_TO_31_DAYS in flags or F.REFUND_LIMIT_CLAUSE_UNKNOWN in flags:
            ids.append("law2_10")
    else:
        if F.WITHDRAWAL in flags:
            ids.append("art3_2")
        if F.PERIOD_UNDER_28_DAYS in flags or F.NO_REFUND_LIMIT_CLAUSE in flags:
            ids.append("law2_10")
        if F.NOTICE_AFTER_VALIDITY in flags and inp.industry == YOGA_PILATES:
            ids.append("yoga_terms_art5_2")
    unique = list(dict.fromkeys(ids))
    unknown = set(unique) - rule.clause_ids
    if unknown:
        raise ValueError(f"규칙 JSON에 없는 조항 ID: {sorted(unknown)}")
    return unique


_BASIS_LABEL = {Basis.PERIOD: "일수 기준", Basis.SESSION: "횟수 기준"}


def _won(n: int) -> str:
    return f"{n:,}"


def _steps(
    inp: GymInput,
    results: dict[Basis, BasisResult],
    ratio_text: str,
    cap: int,
    penalty: int,
) -> list[Step]:
    """계산 과정 (5.3). 첫 줄은 항상 단위대금 해석 고지."""
    steps = [Step(label="단위대금 해석", formula=FIRST_STEP_TEXT, amount=None)]
    for basis, r in results.items():
        for name, s, base in (
            ("A", r.A, inp.total_contract_amount),
            ("B", r.B, inp.list_price),
        ):
            if s is None or base is None:
                continue
            steps.append(
                Step(
                    label=f"이용분 ({_BASIS_LABEL[basis]}, {name})",
                    formula=f"{_won(base)} × {r.elapsed} ÷ {r.units}, {ROUND_NOTE}",
                    amount=s.used_amount,
                )
            )
    steps.append(
        Step(
            label="위약금 상한",
            formula=f"{_won(inp.total_contract_amount)} × {ratio_text}, {FLOOR_NOTE}",
            amount=cap,
        )
    )
    steps.append(
        Step(
            label="공제 위약금",
            formula="계약서상 위약금과 상한 중 적용한 값",
            amount=penalty,
        )
    )
    returned = inp.returned_add_on_value if inp.add_on_returned else 0
    for basis, r in results.items():
        for name, s in (("A", r.A), ("B", r.B)):
            if s is None:
                continue
            formula = (
                f"{_won(inp.paid_amount)} − {_won(s.used_amount)} − {_won(inp.add_on_value)}"
                f" − {_won(penalty)} + {_won(returned or 0)} = {_won(s.raw_refund)}"
            )
            if s.raw_refund < 0:
                formula += " → 0"
            steps.append(
                Step(
                    label=f"환급액 ({_BASIS_LABEL[basis]}, {name})",
                    formula=formula,
                    amount=s.refund,
                )
            )
    if inp.deposit > 0:
        steps.append(
            Step(
                label="보증금 환급",
                formula="별도 약정이 없으면 전액",
                amount=inp.deposit,
            )
        )
    return steps


def calculate_refund(inp: GymInput, rule: GymRule) -> GymResult:
    """범위 판정 → 계산 → 제시액 비교 → 배지 (MVP_SPEC 5.2~5.7)."""
    scope = check_scope(inp, rule)
    if scope.stop_code is not None:
        flags = [scope.stop_code]
        return GymResult(
            badge=decide_badge(
                judgment_requested=inp.judgment_requested,
                out_of_scope=scope.stop_code in UNDETERMINABLE_CODES,
                missing_or_invalid=scope.stop_code in NO_CALC_CODES,
                robust_warnings=[],
                review_flags=[],
            ),
            calculated=False,
            results={},
            penalty=None,
            penalty_cap=None,
            refund_kind=None,
            deposit_refund=inp.deposit,
            contract_days=scope.contract_days,
            steps=[],
            flags=flags,
            missing=scope.missing,
            notices=[],
            citations=_citations(inp, rule, flags, [], calculated=False),
        )

    industry = rule.industry(inp.industry)
    assert industry is not None
    ratio = industry.penalty_rule.ratio
    cap = penalty_cap(inp.total_contract_amount, ratio)
    penalty, kind = calc_penalty(inp.total_contract_amount, cap, inp.contract_penalty)
    results = {b: calc_basis(inp, b, penalty) for b in scope.bases}
    offer = compare_offer(inp.provider_offer, results)

    robust: list[FlagCode] = []
    if offer.robust:
        robust.append(F.OFFER_BELOW_B)
    if inp.contract_penalty is not None and inp.contract_penalty > cap:
        robust.append(F.PENALTY_ABOVE_CAP)
    if not _blocks_verified(inp, rule):
        robust = []  # 미검증 블록에서는 ⚠️를 켜지 않는다 (RULE_UNVERIFIED만 남김)
    assert set(robust) <= ROBUST_CODES
    review = collect_review_flags(inp, rule, results)
    flags = order_flags(robust + review)
    notices = _notices(inp, results, offer)
    return GymResult(
        badge=decide_badge(
            judgment_requested=inp.judgment_requested,
            out_of_scope=False,
            missing_or_invalid=False,
            robust_warnings=robust,
            review_flags=review,
        ),
        calculated=True,
        results=results,
        penalty=penalty,
        penalty_cap=cap,
        refund_kind=kind,
        deposit_refund=inp.deposit,
        contract_days=scope.contract_days,
        steps=_steps(inp, results, str(ratio), cap, penalty),
        flags=flags,
        missing=[],
        notices=notices,
        citations=_citations(inp, rule, flags, notices, calculated=True),
    )
