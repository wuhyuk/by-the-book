"""예/아니오 추출값의 뜻 확인 테스트 (2026-11-08 D1 승인).

근거 구절이 문장에 있기만 하면 통과하던 구멍(VS3 비교 Q12, is_withdrawal 불일치)을 막는다.
- 필드마다 단서 낱말(llm/grounding.py BOOL_CUE_RULES)이 근거 구절에 있어야 채택한다.
- 단서가 없거나 뜻이 맞지 않으면 채택하지 않고 unverified(되묻기)로 보낸다. 조용히 버리지 않는다.
- 계산을 멈추게 하는(❔) 값은 채택해도 confirm(확인 안내)에 넣는다.
기대값은 문장에 쓰인 낱말과 MVP_SPEC 5.2 범위 판정 조건에서만 가져온다.
"""

from typing import Any

import pytest
from test_llm_extraction import raw

from llm.extraction import BOOL_FIELDS, RawExtraction, check_extraction
from llm.grounding import (
    BOOL_CUE_RULES,
    JUDGMENT_CUES,
    NEGATION_CUES,
    bool_grounded,
    judgment_grounded,
)


def check(values: dict[str, tuple[Any, str | None]], text: str, **kw: Any):
    return check_extraction(RawExtraction.model_validate(raw(values, **kw)), text)


# ---- Q12 재현 (먼저 쓴 테스트) ----

Q12_TEXT = (
    "헬스 6개월권을 정상가 그대로 60만원에 결제했어요. 이용 기간은 2026-03-01~2026-08-31인데 "
    "시작 전인 2026-02-20에 개인 사정으로 해지하겠다고 했어요. 계약서 받은 지 한 달이 넘어 청약철회 "
    "기간은 지났어요. 위약금 조항 있어요."
)


@pytest.mark.parametrize("value", [True, False])
def test_q12_is_withdrawal_not_adopted(value: bool) -> None:
    """Q12: 모델이 '청약철회 기간은 지났어요'를 근거로 is_withdrawal을 채워도 받지 않고 되묻는다."""
    r = check({"is_withdrawal": (value, "청약철회 기간은 지났어요")}, Q12_TEXT)
    assert "is_withdrawal" not in r.fields
    assert "is_withdrawal" in r.unverified


def test_q12_withdrawal_cleared_still_adopted() -> None:
    """같은 구절은 withdrawal_cleared=True(기간이 지났음 확인)의 근거로는 맞다."""
    r = check({"withdrawal_cleared": (True, "청약철회 기간은 지났어요")}, Q12_TEXT)
    assert r.fields["withdrawal_cleared"] is True


# ---- 단서 목록 고정 ----


def test_rules_cover_every_bool_field() -> None:
    assert set(BOOL_CUE_RULES) == set(BOOL_FIELDS)


def test_cue_constants_fixed() -> None:
    """단서 목록을 바꾸면 이 테스트와 보고서(vs3_report.md 4.6)를 같이 고친다."""
    assert BOOL_CUE_RULES["is_withdrawal"].cues == ("철회",)
    assert BOOL_CUE_RULES["academy_law_applies"].cues == ("학원",)
    assert BOOL_CUE_RULES["withdrawal_cleared"].cues == ("철회",)
    assert "위약금" in BOOL_CUE_RULES["has_refund_limit_clause"].cues
    assert "연기" in BOOL_CUE_RULES["had_postponement"].cues
    assert "PT" in BOOL_CUE_RULES["is_pt_only"].cues
    assert "돌려" in BOOL_CUE_RULES["add_on_returned"].cues
    assert {"없", "않", "아니", "못"} <= set(NEGATION_CUES)
    assert {"소송", "무효", "판정", "내용증명"} <= set(JUDGMENT_CUES)


# ---- 필드별: 채택 / 되묻기 ----

ACCEPT = [
    ("is_withdrawal", True, "계약 일주일 만에 청약철회하려고 해요"),
    ("academy_law_applies", True, "학원법이 적용되는 계약이에요"),
    ("withdrawal_cleared", True, "청약철회 기간은 지났어요"),
    ("withdrawal_cleared", False, "아직 청약철회 기간이 안 지났어요"),
    ("has_refund_limit_clause", True, "계약서에 위약금 조항이 있어요"),
    ("has_refund_limit_clause", False, "계약서에 위약금 조항은 없었어요"),
    ("had_postponement", True, "한 달 연기했어요"),
    ("had_postponement", False, "연기한 적은 없어요"),
    ("is_pt_only", True, "PT만 30회 끊었어요"),
    ("is_pt_only", False, "헬스장 이용권에 PT 10회가 포함돼 있어요"),
    ("add_on_returned", True, "운동복은 돌려줬어요"),
    ("add_on_returned", False, "운동복은 돌려주지 않았어요"),
]

ASK = [
    # 단서 낱말 없음
    ("is_withdrawal", True, "그만두려고요"),
    ("academy_law_applies", True, "계약서에 적혀 있어요"),
    ("withdrawal_cleared", True, "계약한 지 한 달 넘었어요"),
    ("has_refund_limit_clause", True, "계약서 받았어요"),
    ("had_postponement", True, "한 달 쉬었어요"),
    ("is_pt_only", True, "30회 끊었어요"),
    ("add_on_returned", True, "운동복 받았어요"),
    # 단서는 있으나 뜻이 반대 (부정 표현)
    ("is_withdrawal", True, "청약철회는 안 했어요"),
    ("academy_law_applies", True, "학원은 아니에요"),
    ("withdrawal_cleared", True, "아직 청약철회 기간이 안 지났어요"),
    ("has_refund_limit_clause", True, "위약금 조항은 없었어요"),
    ("has_refund_limit_clause", False, "계약서에 위약금 조항이 있어요"),
    ("had_postponement", True, "연기한 적은 없어요"),
    ("had_postponement", False, "한 달 연기했어요"),
    (
        "is_pt_only",
        True,
        "PT 30회 150만원에 계약했어요",
    ),  # '만원'의 '만'은 단서가 아니다
    ("is_pt_only", False, "PT 30회 끊었어요"),  # 같이 쓰는 이용권이라는 단서 없음
    ("add_on_returned", True, "운동복은 돌려주지 않았어요"),
    ("add_on_returned", False, "운동복은 돌려줬어요"),
    # 기본값과 같은 false는 정보가 없어 받지 않고 되묻는다 (계산을 멈추는 확인 항목)
    ("is_withdrawal", False, "청약철회 기간은 지났어요"),
    ("academy_law_applies", False, "학원법 적용 계약은 아니에요"),
]


@pytest.mark.parametrize(("name", "value", "evidence"), ACCEPT)
def test_bool_accepted(name: str, value: bool, evidence: str) -> None:
    assert bool_grounded(name, value, evidence)
    r = check({name: (value, evidence)}, evidence)
    assert r.fields[name] is value
    assert name not in r.unverified


@pytest.mark.parametrize(("name", "value", "evidence"), ASK)
def test_bool_asked_not_dropped(name: str, value: bool, evidence: str) -> None:
    assert not bool_grounded(name, value, evidence)
    r = check({name: (value, evidence)}, evidence)
    assert name not in r.fields
    assert name in r.unverified  # 조용히 버리지 않고 되묻는다


# ---- 계산을 멈추는 값은 채택해도 확인 안내 ----


@pytest.mark.parametrize(
    ("name", "value", "evidence"),
    [
        ("is_withdrawal", True, "계약 일주일 만에 청약철회하려고 해요"),
        ("academy_law_applies", True, "학원법이 적용되는 계약이에요"),
        ("has_refund_limit_clause", False, "계약서에 위약금 조항은 없었어요"),
        ("termination_cause", "business", "헬스장이 폐업했어요"),
        ("termination_cause", "force_majeure", "지진으로 문을 닫았어요"),
        ("industry", "other", "수영장 3개월권"),
    ],
)
def test_stop_values_need_confirmation(name: str, value: Any, evidence: str) -> None:
    r = check({name: (value, evidence)}, evidence)
    assert r.fields[name] == value
    assert name in r.confirm


def test_ordinary_values_no_confirmation() -> None:
    r = check(
        {
            "termination_cause": ("consumer", "이사 때문에"),
            "industry": ("fitness", "헬스장"),
            "has_refund_limit_clause": (True, "위약금 조항이 있어요"),
        },
        "헬스장 이사 때문에 위약금 조항이 있어요",
    )
    assert r.confirm == []


# ---- 판단 질문 플래그 ----


def test_judgment_needs_cue() -> None:
    text = "업체가 환불을 안 해 줘요. 업체 주장이 맞는 건지 판정해 주세요"
    assert judgment_grounded("업체 주장이 맞는 건지 판정해 주세요", text)
    assert not judgment_grounded("업체가 환불을 안 해 줘요", text)  # 단서 없음
    assert check(
        {}, text, judgment="업체 주장이 맞는 건지 판정해 주세요"
    ).judgment_requested
    assert not check({}, text, judgment="업체가 환불을 안 해 줘요").judgment_requested
