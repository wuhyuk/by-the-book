"""승패·법적 효력 질문 감지 테스트 (CLAUDE.md 절대 규칙 4, MVP_SPEC 7절 '승패·법적 효력 질문 5건')."""

import pytest

from llm.guardrail import detect_judgment_request

JUDGMENT = [
    "업체가 환불을 안 해 주는데 소송하면 이길 수 있을까요?",
    "계약서 위약금 조항이 무효 아닌가요?",
    "환불 안 해 주는 거 불법인가요?",
    "이 계약서 효력이 있는 건가요",
    "내용증명 써 주세요",
    "소장 작성 도와줄 수 있어요?",
    "법적으로 문제 없나요?",
    "승소 가능성이 있을까요",
    "소송하면 돈 받을 수 있나요?",
    "내용증명 작성해 주세요",
    "위약금 30%는 불법 아닌가요?",
]

NOT_JUDGMENT = [
    "헬스장 1년권 120만원 냈는데 3개월 다니고 해지하면 얼마 돌려받나요?",
    "유효기간이 지났나요?",
    "법적으로 얼마 받을 수 있나요?",  # 금액 질문은 계산 대상이다
    "업체가 불법이라고 했어요. 환불은 얼마인가요?",
    "필라테스 20회 중 5회 썼어요",
    # 리뷰에서 찾은 오탐 (남의 말 옮김, 호칭, 이미 한 일, 다른 낱말)
    "소장님이 대신 해지 신청해 줬어요. 환불 얼마인가요?",
    "센터장이 위약금은 효력 없다고 했는데 얼마 돌려받나요?",
    "업체가 위약금 30%는 합법이라던데 환불 얼마인가요?",
    "민사로 가면 시간 걸리니 기준 금액만 알고 싶어요",
    "내용증명 작성해서 보냈는데 환불 얼마인가요",
    "재판매하면 어떻게 되나요?",
]


@pytest.mark.parametrize("text", JUDGMENT)
def test_detects_judgment(text: str) -> None:
    assert detect_judgment_request(text)


@pytest.mark.parametrize("text", NOT_JUDGMENT)
def test_ignores_non_judgment(text: str) -> None:
    assert not detect_judgment_request(text)
