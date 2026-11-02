"""기준 계산기(reference oracle)와 불변식 테스트.

oracle()은 엔진(rules/gym.py)을 보기 전에 MVP_SPEC 5.3 계산식을 식 그대로 옮긴 단순 구현이다.
함수를 나누지 않고 Fraction으로만 계산한다. 고정 시드 난수 입력에서 엔진과 비교한다.
새 의존성 없이 random 모듈만 쓴다.
"""

import math
import random
from datetime import date, timedelta
from fractions import Fraction
from typing import Any

import pytest

from rules.badge import FlagCode as F
from rules.gym import Basis, GymInput, calculate_refund
from rules.loader import load_rule

RULE = load_rule("gym_refund")
SEED = 20261026
N = 600


def oracle(inp: GymInput) -> dict[str, Any]:
    """MVP_SPEC 5.3을 식 그대로 계산한다. 반환: 계산 여부, 위약금, 기준별 (경과, 단위, A, B)."""
    ratio = Fraction(str(RULE.industry(inp.industry).penalty_rule.ratio))
    if inp.industry == "fitness":
        basis = inp.contract_type
    else:
        basis = inp.refund_basis
    bases = ["period", "session"] if basis == "unknown" else [basis]
    if (
        "session" in bases
        and inp.end_date is not None
        and inp.notice_date is not None
        and inp.notice_date > inp.end_date
    ):
        return {"calculated": False}
    cap = math.floor(Fraction(inp.total_contract_amount) * ratio)
    if inp.contract_penalty is None or inp.contract_penalty > cap:
        pen = cap
    else:
        pen = inp.contract_penalty
    out: dict[str, Any] = {"calculated": True, "cap": cap, "penalty": pen}
    for b in bases:
        if b == "period":
            cd = (inp.end_date - inp.start_date).days + 1
            e = min(max((inp.notice_date - inp.start_date).days + 1, 0), cd)
            u = cd
        else:
            e, u = inp.used_sessions, inp.total_sessions
        row = []
        for base in (inp.total_contract_amount, inp.list_price):
            if base is None or base < inp.total_contract_amount:
                row.append(None)
                continue
            used = math.floor(Fraction(base * e, u) + Fraction(1, 2))
            raw = (
                inp.paid_amount
                - used
                - inp.add_on_value
                - pen
                + (inp.returned_add_on_value if inp.add_on_returned else 0)
            )
            row.append((used, raw, max(raw, 0)))
        if row[0] is None:  # A는 항상 있어야 한다
            raise AssertionError("A missing")
        out[b] = (e, u, row[0], row[1])
    return out


def random_input(rng: random.Random) -> GymInput:
    """범위 판정 순서 1~10을 통과하는 입력 (순서 11은 일부러 섞는다)."""
    industry = rng.choice(["fitness", "yoga_pilates"])
    contract_type = rng.choice(["period", "session"])
    refund_basis = (
        rng.choice(["period", "session", "unknown"])
        if industry == "yoga_pilates"
        else None
    )
    basis = contract_type if industry == "fitness" else refund_basis
    total = rng.randint(1, 3_000_000)
    paid = rng.randint(0, total)
    start = date(2026, 1, 1) + timedelta(days=rng.randint(0, 400))
    days = rng.randint(28, 800)
    end = start + timedelta(days=days - 1)
    notice = start + timedelta(days=rng.randint(-40, days + 40))
    with_dates = basis != "session" or rng.random() < 0.8
    total_s = rng.randint(1, 120)
    add_on = rng.choice([0, 0, rng.randint(0, 300_000)])
    returned = add_on > 0 and rng.random() < 0.5
    return GymInput(
        judgment_requested=False,
        industry=industry,
        termination_cause="consumer",
        contract_type=contract_type,
        refund_basis=refund_basis,
        total_contract_amount=total,
        paid_amount=paid,
        start_date=start if with_dates else None,
        end_date=end if with_dates else None,
        notice_date=notice if with_dates else None,
        total_sessions=total_s,
        used_sessions=rng.randint(0, total_s),
        add_on_value=add_on,
        add_on_returned=returned,
        returned_add_on_value=rng.randint(0, add_on) if returned else None,
        deposit=rng.choice([0, rng.randint(0, 500_000)]),
        has_refund_limit_clause=rng.choice([True, None]),
        list_price=rng.choice(
            [None, rng.randint(0, 4_000_000), total, total + rng.randint(1, 900_000)]
        ),
        contract_penalty=rng.choice([None, rng.randint(0, total // 5 + 1)]),
        provider_offer=rng.choice([None, rng.randint(0, total)]),
        withdrawal_cleared=rng.choice([True, False, None]),
        had_postponement=rng.choice([True, False, None]),
        is_pt_only=rng.choice([True, False, None]),
    )


INPUTS = [random_input(random.Random(SEED + i)) for i in range(N)]


def test_oracle_matches_engine() -> None:
    """고정 시드 난수 입력 N건에서 기준 계산기와 엔진의 금액이 모두 같다."""
    mismatches = []
    calculated = 0
    for i, inp in enumerate(INPUTS):
        exp = oracle(inp)
        got = calculate_refund(inp, RULE)
        if got.calculated != exp["calculated"]:
            mismatches.append(
                (i, "calculated", exp["calculated"], got.calculated, got.flags)
            )
            continue
        if not got.calculated:
            assert got.flags == [F.NOTICE_AFTER_VALIDITY]
            continue
        calculated += 1
        if (got.penalty_cap, got.penalty) != (exp["cap"], exp["penalty"]):
            mismatches.append(
                (i, "penalty", exp["cap"], exp["penalty"], got.penalty_cap, got.penalty)
            )
        for b, (e, u, a, bb) in (
            (k, v) for k, v in exp.items() if k in ("period", "session")
        ):
            r = got.results[Basis(b)]
            if (r.elapsed, r.units) != (e, u):
                mismatches.append((i, b, "units", (e, u), (r.elapsed, r.units)))
            if (r.A.used_amount, r.A.raw_refund, r.A.refund) != a:
                mismatches.append((i, b, "A", a, r.A))
            got_b = (r.B.used_amount, r.B.raw_refund, r.B.refund) if r.B else None
            if got_b != bb:
                mismatches.append((i, b, "B", bb, got_b))
        if set(got.results) != {Basis(k) for k in exp if k in ("period", "session")}:
            mismatches.append((i, "bases", list(exp), list(got.results)))
    assert mismatches == []
    assert calculated > N // 2  # 대부분은 계산 경로를 탄다


@pytest.mark.parametrize("inp", INPUTS[:300], ids=lambda _: "")
def test_invariants(inp: GymInput) -> None:
    """환급액 ≥ 0, 공제 위약금 ≤ 상한, A ≥ B, 경과 0이면 이용분 0, 공제 항등식."""
    got = calculate_refund(inp, RULE)
    if not got.calculated:
        return
    assert got.penalty is not None and got.penalty_cap is not None
    assert 0 <= got.penalty <= got.penalty_cap
    assert got.deposit_refund == inp.deposit
    ret = inp.returned_add_on_value if inp.add_on_returned else 0
    for r in got.results.values():
        assert 0 <= r.elapsed <= r.units
        for s in (r.A, r.B):
            if s is None:
                continue
            assert s.refund >= 0
            assert s.refund == max(s.raw_refund, 0)
            assert (
                s.used_amount + inp.add_on_value + got.penalty - ret + s.raw_refund
                == inp.paid_amount
            )
            if r.elapsed == 0:
                assert s.used_amount == 0
        if r.B is not None:
            assert (
                inp.list_price is not None
                and inp.list_price >= inp.total_contract_amount
            )
            assert r.A.refund >= r.B.refund
        elif inp.list_price is not None and inp.list_price >= inp.total_contract_amount:
            raise AssertionError("B가 있어야 한다")


def test_monotonic_in_elapsed_days() -> None:
    """도달일이 늦어질수록(경과 일수가 늘수록) 환급액은 늘지 않는다 (기간 기준)."""
    rng = random.Random(SEED)
    for _ in range(40):
        total = rng.randint(100_000, 2_000_000)
        start = date(2026, 1, 1)
        end = start + timedelta(days=rng.randint(31, 400))
        base = {
            "judgment_requested": False,
            "industry": "fitness",
            "termination_cause": "consumer",
            "contract_type": "period",
            "total_contract_amount": total,
            "paid_amount": total,
            "start_date": start,
            "end_date": end,
            "has_refund_limit_clause": True,
            "list_price": total + rng.randint(0, 500_000),
        }
        prev_a = prev_b = None
        for offset in range(-3, (end - start).days + 5):
            got = calculate_refund(
                GymInput(**base, notice_date=start + timedelta(days=offset)), RULE
            )
            r = got.results[Basis.PERIOD]
            if prev_a is not None:
                assert r.A.refund <= prev_a
                assert r.B is not None and r.B.refund <= prev_b
            prev_a, prev_b = r.A.refund, r.B.refund if r.B else None


def test_monotonic_in_used_sessions() -> None:
    """이용 횟수가 늘수록 환급액은 늘지 않는다 (횟수 기준)."""
    base = {
        "judgment_requested": False,
        "industry": "yoga_pilates",
        "termination_cause": "consumer",
        "contract_type": "session",
        "refund_basis": "session",
        "total_contract_amount": 999_999,
        "paid_amount": 999_999,
        "start_date": date(2026, 3, 1),
        "end_date": date(2026, 8, 31),
        "notice_date": date(2026, 4, 1),
        "total_sessions": 17,
        "has_refund_limit_clause": True,
    }
    refunds = [
        calculate_refund(GymInput(**base, used_sessions=k), RULE)
        .results[Basis.SESSION]
        .A.refund
        for k in range(18)
    ]
    assert refunds == sorted(refunds, reverse=True)


@pytest.mark.parametrize(
    ("offset", "elapsed"),
    [(-1, 0), (0, 1), (183, 184), (184, 184), (1000, 184)],
)
def test_day_boundaries(offset: int, elapsed: int) -> None:
    """일수 경계: 시작 전 0, 시작일 1, 종료일 계약 일수, 초과 입력은 계약 일수."""
    start = date(2026, 3, 1)
    inp = GymInput(
        judgment_requested=False,
        industry="fitness",
        termination_cause="consumer",
        contract_type="period",
        total_contract_amount=600_000,
        paid_amount=600_000,
        start_date=start,
        end_date=date(2026, 8, 31),
        notice_date=start + timedelta(days=offset),
        has_refund_limit_clause=True,
    )
    r = calculate_refund(inp, RULE).results[Basis.PERIOD]
    assert (r.elapsed, r.units) == (elapsed, 184)
