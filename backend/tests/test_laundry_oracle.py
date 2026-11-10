"""세탁 엔진 ↔ 구조가 다른 기준 계산기 (고정 시드 난수) + 불변식 (MVP_SPEC 12.3·12.4).

기준 계산기는 규칙 JSON을 읽지 않고 고시 원문 표(test_laundry_rule_data의 SOURCE_*)로 계산한다.
날짜는 toordinal 정수 차, 원 미만 처리는 Decimal, 칸 조회는 하한 목록을 뒤에서부터 훑는다.
케이스 기대값을 쓰지 않는다 (명세 규칙과 원문 표에서 나온 값만 비교).
"""

import random
from datetime import date, timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

import pytest
from test_laundry_rule_data import RATIOS, SOURCE_UPPER, SOURCE_YEARS

from rules.badge import Badge
from rules.laundry import LaundryInput, calculate_damage
from rules.laundry_codes import CommonFlag, LaundryFlag
from rules.laundry_rule import load_laundry_rule

C = CommonFlag
L = LaundryFlag
SEED = 20261110
N_CASES = 3000


def _ratio(life: int, days: int) -> tuple[int, int]:
    """(칸 번호, 비율). 하한 목록을 뒤에서부터 훑는다."""
    lowers = [0] + [u + 1 for u in SOURCE_UPPER[life]]
    for idx in range(len(lowers) - 1, -1, -1):
        if days >= lowers[idx]:
            return idx, RATIOS[idx]
    raise AssertionError


def _money(price: int, pct: int, mode: str) -> int:
    value = Decimal(price) * Decimal(pct) / Decimal(100)
    rounding = ROUND_FLOOR if mode == "floor" else ROUND_HALF_UP
    return int(value.quantize(Decimal(1), rounding=rounding))


def oracle(
    item: str, vidx: int, price: int, purchase: date, request: date
) -> tuple[int, int, int, set[str]]:
    """(결과 값, 최솟값, 최댓값, 원인 집합)."""
    life = SOURCE_YEARS[item][vidx]
    d0 = request.toordinal() - purchase.toordinal()
    res = {}
    for extra in (0, 1):
        for mode in ("floor", "half_up"):
            band, pct = _ratio(life, d0 + extra)
            res[(extra, mode)] = (band, _money(price, pct, mode))
    base = res[(0, "floor")]
    causes = set()
    if res[(1, "floor")] != base:
        causes.add("use_days")
    if res[(0, "half_up")] != base:
        causes.add("rounding")
    if not causes and res[(1, "half_up")] != base:
        causes = {"use_days", "rounding"}
    amounts = [a for _, a in res.values()]
    return base[1], min(amounts), max(amounts), causes


def _random_cases() -> list[dict]:
    rng = random.Random(SEED)
    rule = load_laundry_rule()
    rows = {r.id: r for r in rule.lifespan_table.rows}
    out = []
    for _ in range(N_CASES):
        item = rng.choice(list(SOURCE_YEARS))
        vidx = rng.randrange(len(SOURCE_YEARS[item]))
        row = rows[item]
        variant = row.variants[vidx].key if row.variants else None
        purchase = date(2015, 1, 1) + timedelta(days=rng.randrange(4000))
        days = rng.choice([rng.randrange(4000), rng.randrange(120)])
        claims = {
            name: rng.random() < 0.08
            for name in (
                "special_agreement",
                "customer_partial_fault",
                "wants_damaged_item",
                "no_issue_confirmation",
                "uncollected",
            )
        }
        out.append(
            {
                "item": item,
                "vidx": vidx,
                "variant": variant,
                "price": rng.choice(
                    [rng.randrange(1, 3_000_000), rng.randrange(1, 300) * 1000]
                ),
                "purchase": purchase,
                "request": purchase + timedelta(days=days),
                "offer": rng.choice([None, rng.randrange(0, 2_000_000)]),
                "claims": claims,
            }
        )
    return out


CASES = _random_cases()


@pytest.mark.parametrize("chunk", range(10))
def test_engine_matches_oracle(chunk: int) -> None:
    rule = load_laundry_rule()
    for c in CASES[chunk::10]:
        inp = LaundryInput(
            judgment_requested=False,
            service_type="laundry_shop",
            damage_type="defect",
            item_key=c["item"],
            variant_key=c["variant"],
            purchase_price=c["price"],
            purchase_date=c["purchase"],
            request_date=c["request"],
            proof_available=True,
            provider_offer=c["offer"],
            **c["claims"],
        )
        r = calculate_damage(inp, rule)
        amount, lo, hi, causes = oracle(
            c["item"], c["vidx"], c["price"], c["purchase"], c["request"]
        )
        assert (r.amount, r.sensitivity_min, r.sensitivity_max) == (amount, lo, hi)
        assert set(r.sensitivity_causes) == causes
        claimed = any(c["claims"].values())
        offer_low = c["offer"] is not None and c["offer"] < lo and not claimed
        assert (L.OFFER_BELOW_STANDARD_MIN in r.flags) == offer_low
        assert (L.DECISION_SENSITIVE in r.flags) == bool(causes)
        if offer_low:
            assert r.badge == Badge.WARNING
        elif causes or claimed:
            assert r.badge == Badge.NEEDS_REVIEW
        else:
            assert r.badge == Badge.CONFIRMED
        # 불변식
        assert lo <= r.amount <= hi
        assert r.calculated and r.method == "ratio"
        if causes == {"rounding"}:
            assert hi - lo == 1


def test_fallback_never_sensitive() -> None:
    rule = load_laundry_rule()
    rng = random.Random(SEED)
    for _ in range(200):
        fee = rng.randrange(1, 100_000)
        r = calculate_damage(
            LaundryInput(
                judgment_requested=False,
                service_type="laundry_shop",
                damage_type=rng.choice(["defect", "loss"]),
                proof_available=False,
                laundry_fee=fee,
            ),
            rule,
        )
        assert r.amount == r.fallback_amount == fee * 20
        assert r.sensitivity_causes == [] and r.badge == Badge.CONFIRMED
