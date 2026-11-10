"""세탁 화면 표시 정보 (MVP_SPEC 12.4·12.5·12.7·12.8). 숫자는 엔진 결과에서만 채운다."""

from datetime import date
from typing import Any

import pytest

from rules.badge import Badge
from rules.gym_display import FLAG_TEXTS as GYM_FLAG_TEXTS
from rules.laundry import LaundryInput, calculate_damage
from rules.laundry_codes import CommonFlag, LaundryFlag, LaundryNotice
from rules.laundry_display import (
    DISCLAIMER,
    FLAG_TEXTS,
    NOTICE_TEXTS,
    build_laundry_display,
    item_options,
    sensitivity_text,
)
from rules.laundry_rule import LaundryRule, load_laundry_rule

L = LaundryFlag
BASE: dict[str, Any] = {
    "judgment_requested": False,
    "service_type": "laundry_shop",
    "damage_type": "defect",
    "item_key": "coat",
    "purchase_price": 100_000,
    "purchase_date": date(2026, 1, 1),
    "request_date": date(2026, 3, 1),
    "proof_available": True,
}


@pytest.fixture(scope="module")
def rule() -> LaundryRule:
    return load_laundry_rule()


def run(rule: LaundryRule, **kw: Any):
    return calculate_damage(LaundryInput(**{**BASE, **kw}), rule)


def test_every_code_has_text() -> None:
    assert set(FLAG_TEXTS) | {L.DECISION_SENSITIVE} == set(LaundryFlag) | set(
        CommonFlag
    )
    assert set(NOTICE_TEXTS) == set(LaundryNotice)


def test_common_texts_same_as_gym() -> None:
    by_value = {k.value: v for k, v in GYM_FLAG_TEXTS.items()}
    for code in CommonFlag:
        assert FLAG_TEXTS[code] == by_value[code.value]


def _find_sensitive(rule: LaundryRule, want: set[str]) -> Any:
    """원하는 원인이 나오는 입력을 찾는다 (명세 규칙대로 엔진이 판정, 금액은 결과에서 읽는다)."""
    for price in (100_000, 123_457, 98_765, 50_001):
        for days in range(400):
            r = run(
                rule,
                item_key="sweater",
                purchase_price=price,
                purchase_date=date(2025, 1, 1),
                request_date=date.fromordinal(date(2025, 1, 1).toordinal() + days),
            )
            if set(r.sensitivity_causes) == want:
                return r
    raise AssertionError(want)


@pytest.mark.parametrize(
    "want", [{"use_days"}, {"rounding"}, {"use_days", "rounding"}], ids=str
)
def test_sensitivity_text_uses_result_numbers(
    rule: LaundryRule, want: set[str]
) -> None:
    r = _find_sensitive(rule, want)
    text = sensitivity_text(r)
    assert f"{r.sensitivity_min:,}원~{r.sensitivity_max:,}원" in text
    if want == {"use_days"}:
        assert f"{r.ratio_percent}%에서 {r.sensitivity_ratio_alt}%로" in text
    if want == {"rounding"}:
        assert "1원 차이" in text
    d = build_laundry_display(r, rule)
    lines = [d.screen_line, *d.other_flags]
    assert any(ln is not None and ln.text == text for ln in lines)


def test_confirmed_display(rule: LaundryRule) -> None:
    r = run(rule)
    d = build_laundry_display(r, rule)
    assert d.badge == r.badge
    assert d.disclaimer == DISCLAIMER
    assert "권고" in DISCLAIMER and "법적 판단이 아닙니다" in DISCLAIMER
    assert d.consult is None
    assert [c.id for c in d.citations] == r.citations
    assert d.rule_source.notice_number == "공정거래위원회고시 제2025-14호"


def test_undeterminable_has_consult(rule: LaundryRule) -> None:
    r = run(rule, attachment_only=True)
    d = build_laundry_display(r, rule)
    assert d.badge == Badge.UNDETERMINABLE and d.consult is not None
    assert d.screen_line is not None and "지원하지 않습니다" in d.screen_line.text
    assert "규정이 있으나" in d.screen_line.text


def test_missing_has_no_consult(rule: LaundryRule) -> None:
    d = build_laundry_display(run(rule, proof_available=None), rule)
    assert d.consult is None


def test_item_options_have_no_years(rule: LaundryRule) -> None:
    opts = item_options(rule)
    assert [o.key for o in opts] == [r.id for r in rule.lifespan_table.rows]
    hanbok = next(o for o in opts if o.key == "hanbok")
    assert hanbok.variants == []
    dumped = str([o.model_dump() for o in opts])
    assert "years" not in dumped
