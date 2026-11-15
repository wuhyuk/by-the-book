"""제시액 차액(offer_gap)·다음 행동(next_steps)·조항 조회(/api/sources) 테스트 (MVP_SPEC 14절, 2026-11-16).

차액 기대값: 기존 승인 케이스 중 업체 제시액이 있는 9건(헬스장 S3·N1·N2, 세탁 L8·L22, R2-35,
가전 A-27·A-28·A-32)에 대해 승인된 금액·범위와 입력 제시액의 정수 뺄셈으로 도출한 값이다
(사용자 승인 2026-11-16 허용 규칙, 표는 docs/sources/offer_gap_cases.md 1절).
A-32는 RULE_UNVERIFIED라 offer_gap이 없어야 한다.
꺼짐 상태: 결과·표시·문안 JSON에 새 키가 나오지 않는다 (기존 승인 케이스 테스트는 손대지 않음).
"""

import json
import random
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_appliance_cases import CASES as APPLIANCE_CASES
from test_appliance_cases import inp as appliance_inp
from test_appliance_cases import rule_for as appliance_rule_for
from test_guide import FORBIDDEN_TERMS, numbers, unexplained_numbers
from test_gym_calc import CASES as GYM_CASES
from test_laundry_cases import BASE as LAUNDRY_BASE
from test_laundry_cases import CASES as LAUNDRY_CASES
from test_laundry_r2_cases import CASES as R2_CASES

from api.settings import (
    KNOWN_FEATURES,
    AppSettings,
    get_app_settings,
    load_app_settings,
)
from guide.appliance import build_appliance_guide
from guide.common import CONSULT_1372_LINE, Guide, with_next_steps
from guide.gym import build_gym_guide
from guide.laundry import build_laundry_guide
from guide.next_steps import CHANNELS, CHECKLISTS, NEXT_STEPS_DISCLAIMER
from main import app
from rules.appliance import calculate_appliance
from rules.appliance_rule import load_appliance_rule
from rules.badge import Badge
from rules.gym import GymInput, calculate_refund
from rules.laundry import LaundryInput, calculate_damage
from rules.laundry_rule import load_laundry_rule
from rules.loader import load_rule
from rules.offer_gap import OfferGap, compute_offer_gap, offer_gap_text
from rules.sources import RULE_FILES, clause_index

client = TestClient(app)
GYM_RULE = load_rule("gym_refund")
LAUNDRY_RULE = load_laundry_rule()
APPLIANCE_RULE = load_appliance_rule()
ON = frozenset({"offer_gap", "next_steps", "set_partial"})

# (케이스, 제시액, 승인 기준 금액 최솟값, 최댓값) → 정수 뺄셈으로 도출 (offer_gap_cases.md 1절)
GAP_EXPECTED: dict[str, tuple[int, int, int, int, int, str]] = {
    # id: (offer, min, max, gap_to_min, gap_to_max, direction)
    "S3": (600_000, 750_000, 750_000, 150_000, -150_000, "below_min"),
    "N1": (700_000, 636_164, 784_110, -63_836, -84_110, "within"),
    "N2": (200_000, 240_000, 340_000, 40_000, -140_000, "below_min"),
    "L8": (100_000, 160_000, 160_000, 60_000, -60_000, "below_min"),
    "L22": (160_000, 160_000, 160_000, 0, 0, "equal"),
    "R2-35": (130_000, 136_500, 210_000, 6_500, -80_000, "below_min"),
    "A-27": (500_000, 920_000, 920_000, 420_000, -420_000, "below_min"),
    "A-28": (680_000, 674_000, 684_000, -6_000, -4_000, "within"),
}
OFFER_CASE_IDS = [*GAP_EXPECTED, "A-32"]


def gap_of(e: tuple[int, int, int, int, int, str]) -> OfferGap:
    offer, lo, hi, to_min, to_max, direction = e
    return OfferGap(
        offer=offer,
        reference_min=lo,
        reference_max=hi,
        gap_to_min=to_min,
        gap_to_max=to_max,
        direction=direction,  # type: ignore[arg-type]
    )


def gym_input(cid: str) -> GymInput:
    return next(c for c in GYM_CASES if c.id == cid).inp


def laundry_input(cid: str) -> LaundryInput:
    if cid.startswith("R2-"):
        return LaundryInput.model_validate_json(json.dumps(R2_CASES[cid]["input"]))
    case = next(c for c in LAUNDRY_CASES if c.id == cid)
    return LaundryInput(**{**LAUNDRY_BASE, **case.inp})


def run(cid: str, features: frozenset[str]) -> tuple[Any, Guide, Any, int | None]:
    """승인 케이스 하나를 엔진·문안으로 돌린다 → (결과, 문안, 규칙, 제시액)."""
    if cid.startswith("A-"):
        case = APPLIANCE_CASES[cid]
        ai = appliance_inp(case["input"])
        arule = appliance_rule_for(case)
        ar = calculate_appliance(ai, arule, features)
        return ar, build_appliance_guide(ai, ar, arule), arule, ai.provider_offer
    if cid.startswith(("L", "R2-")):
        li = laundry_input(cid)
        lr = calculate_damage(li, LAUNDRY_RULE, features)
        return (
            lr,
            build_laundry_guide(li, lr, LAUNDRY_RULE),
            LAUNDRY_RULE,
            li.provider_offer,
        )
    gi = gym_input(cid)
    gr = calculate_refund(gi, GYM_RULE, features)
    return gr, build_gym_guide(gi, gr, GYM_RULE), GYM_RULE, gi.provider_offer


@pytest.fixture
def features() -> Iterator[Callable[..., None]]:
    def _set(*names: str) -> None:
        app.dependency_overrides[get_app_settings] = lambda: AppSettings(
            enabled_features=names
        )

    yield _set
    app.dependency_overrides.pop(get_app_settings, None)


# ---- 설정 ----


def test_known_features() -> None:
    assert KNOWN_FEATURES == (
        "set_partial",
        "appliance",
        "offer_gap",
        "next_steps",
        "rag",
    )
    s = load_app_settings(
        {"ENABLED_FEATURES": "rag, next_steps,offer_gap"}, env_file=None
    )
    assert s.enabled_features == ("offer_gap", "next_steps", "rag")


def test_config_lists_new_features(features: Callable[..., None]) -> None:
    features("offer_gap", "next_steps")
    assert client.get("/api/config").json()["enabled_features"] == [
        "offer_gap",
        "next_steps",
    ]


# ---- 차액: 승인 케이스 ----


@pytest.mark.parametrize("cid", list(GAP_EXPECTED))
def test_offer_gap_from_approved_cases(cid: str) -> None:
    result, _, _, _ = run(cid, ON)
    assert result.offer_gap == gap_of(GAP_EXPECTED[cid])


def test_offer_gap_absent_when_rule_unverified() -> None:
    result, guide, _, _ = run("A-32", ON)
    assert "RULE_UNVERIFIED" in [f.value for f in result.flags]
    assert result.offer_gap is None
    assert not any("업체 제시액" in line for line in guide.explanation)


@pytest.mark.parametrize("cid", OFFER_CASE_IDS)
def test_offer_gap_does_not_change_badge_flags_or_company_message(cid: str) -> None:
    off_result, off_guide, _, _ = run(cid, frozenset({"set_partial"}))
    on_result, on_guide, _, _ = run(cid, ON)
    assert on_result.badge == off_result.badge
    assert on_result.flags == off_result.flags
    assert on_result.notices == off_result.notices
    assert on_guide.company_message == off_guide.company_message
    assert on_result.model_dump(exclude={"offer_gap"}) == off_result.model_dump()


@pytest.mark.parametrize("cid", OFFER_CASE_IDS)
def test_offer_gap_absent_when_flag_off(cid: str) -> None:
    result, guide, _, _ = run(cid, frozenset({"set_partial"}))
    assert result.offer_gap is None
    assert "offer_gap" not in result.model_dump()
    assert "offer_gap" not in json.loads(result.model_dump_json())
    assert "next_steps" not in json.loads(guide.model_dump_json())


@pytest.mark.parametrize("cid", list(GAP_EXPECTED))
def test_offer_gap_line_in_explanation_with_numbers_from_result(cid: str) -> None:
    result, guide, rule, offer = run(cid, ON)
    line = offer_gap_text(result.offer_gap)
    assert line in guide.explanation
    # 기존 R2 Set 배분 줄은 입력 구입가격을 옮긴다 (guide/laundry.py _set_line) → 그 값만 더 인정한다
    extra = {laundry_input(cid).purchase_price} if cid.startswith("R2-") else set()
    assert not unexplained_numbers(result, guide, rule, offer) - extra


def test_no_offer_no_gap() -> None:
    result, _, _, _ = run("C1", ON)
    assert result.calculated and result.offer_gap is None


def test_undeterminable_has_no_gap() -> None:
    gi = gym_input("B1").model_copy(update={"provider_offer": 100_000})
    result = calculate_refund(gi, GYM_RULE, ON)
    assert result.badge == Badge.UNDETERMINABLE and result.offer_gap is None


def test_not_calculated_has_no_gap() -> None:
    gi = gym_input("M1").model_copy(update={"provider_offer": 100_000})
    result = calculate_refund(gi, GYM_RULE, ON)
    assert not result.calculated and result.offer_gap is None


# ---- 차액: 순수 함수 성질 (고정 시드 난수) ----


def test_compute_offer_gap_properties() -> None:
    rng = random.Random(20261116)
    for _ in range(3000):
        lo = rng.randint(0, 2_000_000)
        hi = lo + rng.choice([0, rng.randint(1, 500_000)])
        offer = rng.choice([lo, hi, rng.randint(0, 3_000_000)])
        g = compute_offer_gap(offer, lo, hi)
        assert g.gap_to_min + offer == lo
        assert offer - g.gap_to_max == hi
        if offer < lo:
            assert g.direction == "below_min" and g.gap_to_min > 0
        elif offer > hi:
            assert g.direction == "above_max" and g.gap_to_max > 0
        elif lo == hi:
            assert g.direction == "equal" and g.gap_to_min == g.gap_to_max == 0
        else:
            assert g.direction == "within"
            assert g.gap_to_min <= 0 and g.gap_to_max <= 0


def test_compute_offer_gap_rejects_reversed_range() -> None:
    with pytest.raises(ValueError):
        compute_offer_gap(1, 10, 5)


@pytest.mark.parametrize(
    ("offer", "lo", "hi", "start"),
    [
        (1, 5, 5, "업체 제시액 1원은 기준 금액 5원보다 4원 적습니다."),
        (
            1,
            5,
            9,
            "업체 제시액 1원은 기준 금액 범위(5원~9원)의 최솟값보다 4원 적습니다.",
        ),
        (6, 5, 9, "업체 제시액 6원은 기준 금액 범위(5원~9원) 안에 있습니다."),
        (8, 5, 5, "업체 제시액 8원은 기준 금액보다 3원 많습니다."),
        (
            12,
            5,
            9,
            "업체 제시액 12원은 기준 금액 범위(5원~9원)의 최댓값보다 3원 많습니다.",
        ),
        (5, 5, 5, "업체 제시액은 기준 금액과 같습니다."),
    ],
)
def test_offer_gap_text_forms(offer: int, lo: int, hi: int, start: str) -> None:
    assert offer_gap_text(compute_offer_gap(offer, lo, hi)) == start


def test_offer_gap_text_terms_and_numbers() -> None:
    banned = (*FORBIDDEN_TERMS, "사기", "부당", "받을 수 있", "승패", "효력")
    rng = random.Random(7)
    for _ in range(500):
        lo = rng.randint(0, 900_000)
        hi = lo + rng.choice([0, rng.randint(1, 90_000)])
        offer = rng.randint(0, 1_100_000)
        g = compute_offer_gap(offer, lo, hi)
        text = offer_gap_text(g)
        assert not any(t in text for t in banned)
        assert numbers(text) <= {offer, lo, hi, abs(g.gap_to_min), abs(g.gap_to_max)}


# ---- 차액: API ----

GYM_N2 = json.loads(gym_input("N2").model_dump_json())
APPLIANCE_A27 = APPLIANCE_CASES["A-27"]["input"]


def test_api_calculate_flag_off_has_no_new_keys(features: Callable[..., None]) -> None:
    features()
    body = client.post("/api/calculate", json=GYM_N2).json()
    assert "offer_gap" not in body["result"]
    assert "offer_gap_text" not in body["display"]
    guide = client.post("/api/guide", json=GYM_N2).json()
    assert set(guide) == {"explanation", "company_message", "citations"}


def test_api_calculate_flag_on_gym(features: Callable[..., None]) -> None:
    features("offer_gap")
    body = client.post("/api/calculate", json=GYM_N2).json()
    assert body["result"]["offer_gap"] == gap_of(GAP_EXPECTED["N2"]).model_dump()
    assert body["display"]["offer_gap_text"] == (
        "업체 제시액 200,000원은 기준 금액 범위(240,000원~340,000원)의 최솟값보다 40,000원 적습니다."
    )
    assert body["result"]["badge"] == Badge.WARNING.value


def test_api_calculate_flag_on_laundry_r2(features: Callable[..., None]) -> None:
    features("offer_gap", "set_partial")
    data = R2_CASES["R2-35"]["input"]
    body = client.post("/api/calculate?item=laundry", json=data).json()
    assert body["result"]["offer_gap"] == gap_of(GAP_EXPECTED["R2-35"]).model_dump()
    assert body["display"]["offer_gap_text"] == (
        "업체 제시액 130,000원은 기준 금액 범위(136,500원~210,000원)의 최솟값보다 6,500원 적습니다."
    )
    guide = client.post("/api/guide?item=laundry", json=data).json()
    assert body["display"]["offer_gap_text"] in guide["explanation"]


@pytest.mark.parametrize("cid", ["A-27", "A-28"])
def test_api_calculate_flag_on_appliance(
    features: Callable[..., None], cid: str
) -> None:
    features("offer_gap", "appliance")
    data = APPLIANCE_CASES[cid]["input"]
    body = client.post("/api/calculate?item=appliance", json=data).json()
    assert body["result"]["offer_gap"] == gap_of(GAP_EXPECTED[cid]).model_dump()
    assert body["result"]["badge"] == APPLIANCE_CASES[cid]["expected"]["badge"]


# ---- 다음 행동 ----


def guide_on(cid: str) -> tuple[Any, Guide]:
    result, guide, _, _ = run(cid, ON)
    item = (
        "appliance"
        if cid.startswith("A-")
        else ("laundry" if cid.startswith(("L", "R2-")) else "gym")
    )
    return result, with_next_steps(
        guide, item, calculated=result.calculated, flags=result.flags, features=ON
    )


@pytest.mark.parametrize("cid", ["C1", "N2", "P1", "L1", "L8", "L14", "A-27", "A-28"])
def test_next_steps_full_for_calculated(cid: str) -> None:
    result, guide = guide_on(cid)
    assert result.calculated
    ns = guide.next_steps
    assert ns is not None and ns.checklist and len(ns.channels) == 3
    assert ns.disclaimer == NEXT_STEPS_DISCLAIMER


@pytest.mark.parametrize("cid", ["B1", "H1", "M1", "V1", "L9", "L7", "L19", "A-32"])
def test_next_steps_channels_only(cid: str) -> None:
    result, guide = guide_on(cid)
    assert (not result.calculated) or "RULE_UNVERIFIED" in [
        f.value for f in result.flags
    ]
    ns = guide.next_steps
    assert ns is not None
    assert ns.checklist == [] and ns.checklist_note is None
    assert [c.id for c in ns.channels] == ["ccn_1372", "kca_relief", "klac_132"]


@pytest.mark.parametrize("cid", ["B1", "H1", "L9", "V1"])
def test_next_steps_removes_duplicate_1372_line(cid: str) -> None:
    _, off = run(cid, frozenset())[:2]
    _, on = guide_on(cid)
    assert CONSULT_1372_LINE not in on.explanation
    assert [x for x in off.explanation if x != CONSULT_1372_LINE] == on.explanation


def test_next_steps_checklists_and_channels_rules() -> None:
    banned = (*FORBIDDEN_TERMS, "사기", "부당", "받을 수 있", "무효")
    texts = [i.text for items in CHECKLISTS.values() for i in items]
    for t in texts:
        assert not numbers(t)
        assert not any(b in t for b in banned)
    for item in CHECKLISTS.values():
        for i in item:
            assert (
                i.basis_label
                == {"official": "공식 안내", "general": "일반 안내"}[i.basis]
            )
            assert (i.source_url is not None) == (i.basis == "official")
    for c in CHANNELS:
        assert not any(b in (c.how or "") for b in banned)
        if c.status == "confirmed":
            assert (
                c.url
                and c.url.startswith("https://")
                and c.checked_on
                and c.source_urls
            )
        else:
            assert c.url is None and c.how is None
    phones = {c.id: c.phone for c in CHANNELS}
    assert phones == {"ccn_1372": "1372", "kca_relief": None, "klac_132": "132"}


def test_api_guide_next_steps(features: Callable[..., None]) -> None:
    features("next_steps")
    body = client.post("/api/guide", json=GYM_N2).json()
    assert body["next_steps"]["checklist"]
    assert [c["id"] for c in body["next_steps"]["channels"]] == [
        "ccn_1372",
        "kca_relief",
        "klac_132",
    ]
    calc = client.post("/api/calculate", json=GYM_N2).json()
    assert "offer_gap" not in calc["result"]  # next_steps만 켜면 차액은 없다


def test_api_guide_next_steps_undeterminable(features: Callable[..., None]) -> None:
    features("next_steps")
    data = json.loads(gym_input("B1").model_dump_json())
    body = client.post("/api/guide", json=data).json()
    assert body["next_steps"]["checklist"] == []
    assert CONSULT_1372_LINE not in body["explanation"]


# ---- 조항 조회 ----


def test_sources_known_clause() -> None:
    r = client.get("/api/sources/art5_1")
    assert r.status_code == 200
    body = r.json()
    rule_clause = next(c for c in GYM_RULE.clauses if c.id == "art5_1")
    assert body["text"] == rule_clause.text and body["label"] == rule_clause.label
    assert body["source"]["name"] == GYM_RULE.source.name
    assert body["retrieved_at"] == GYM_RULE.source.retrieved_at
    assert body["verified"] is True and body["user_checked"] is None
    assert body["rule_ids"] == ["gym_refund"]


def test_sources_table_clause_uses_block_verification() -> None:
    body = client.get("/api/sources/laundry_ratio_table").json()
    assert body["verified"] is LAUNDRY_RULE.ratio_table.verified
    assert body["user_checked"] is True


def test_sources_shared_clause_lists_rule_ids() -> None:
    body = client.get("/api/sources/cpa16_3").json()
    assert body["rule_ids"] == ["laundry_damage", "appliance_warranty"]


def test_sources_not_found_and_invalid() -> None:
    r = client.get("/api/sources/no_such_clause")
    assert r.status_code == 404
    assert r.json() == {"message": "해당 조항 ID를 찾을 수 없습니다."}
    for bad in ["ART5_1", "art5-1", "a" * 65, "%E2%91%A0"]:
        assert client.get(f"/api/sources/{bad}").status_code == 422


def test_sources_cover_every_clause() -> None:
    raw_ids: set[str] = set()
    for rule_id in RULE_FILES:
        data = json.loads(
            (
                __import__("pathlib").Path(__file__).resolve().parent.parent
                / "data"
                / "rules"
                / f"{rule_id}.json"
            ).read_text(encoding="utf-8")
        )
        raw_ids |= {c["id"] for c in [*data["clauses"], *data["related_clauses"]]}
    assert set(clause_index()) == raw_ids
