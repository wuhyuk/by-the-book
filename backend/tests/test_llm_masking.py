"""마스킹 테스트 (CLAUDE.md 절대 규칙 6). 사례는 모두 가상 값이다."""

import pytest

from llm.masking import TOKENS, mask_pii


@pytest.mark.parametrize(
    ("text", "secret", "token"),
    [
        ("연락처는 010-1234-5678입니다", "010-1234-5678", "phone"),
        ("01098765432로 전화 주세요", "01098765432", "phone"),
        ("매장 번호 02-123-4567", "02-123-4567", "phone"),
        ("대표번호 1588-1234", "1588-1234", "phone"),
        ("계좌 110-123-456789로 환불", "110-123-456789", "account"),
        ("계좌번호 3333012345678", "3333012345678", "account"),
        ("주민번호 900101-1234567", "900101-1234567", "rrn"),
        ("카드 1234-5678-9012-3456", "1234-5678-9012-3456", "card"),
        ("메일 test.user@example.com", "test.user@example.com", "email"),
        ("제 이름은 홍길동이고 회원입니다", "홍길동", "name"),
        ("성함: 김영희, 연락 바랍니다", "김영희", "name"),
        ("저는 박철수입니다", "박철수", "name"),
        ("이영희씨가 상담했어요", "이영희", "name"),
        ("최민수 님께 말씀드렸어요", "최민수", "name"),
        ("예금주 정하나로 보내 주세요", "정하나", "name"),
        ("신한 110 123 456789로 환불", "110 123 456789", "account"),
        ("연락처 +82-10-1234-5678", "+82-10-1234-5678", "phone"),
    ],
)
def test_masks_pii(text: str, secret: str, token: str) -> None:
    masked = mask_pii(text)
    assert secret not in masked
    assert TOKENS[token] in masked


@pytest.mark.parametrize(
    "text",
    [
        "120만원을 2026-01-01에 결제했어요",
        "총 1,200,000원, 정상가 1500000원",
        "2026년 3월 31일에 해지 요청, 20회 중 5회 이용",
        "2026.04.30부터 2026/06/28까지",
        "12만 5천원, 1억 2천만원",
        "트레이너님, 선생님, 회원님, 강사님, 고객님, 사장님이 그랬어요",
        "저는 회원입니다. 담당자 이름이 기억이 안 나요",
        "총 20 회, 2026 01 01",
    ],
)
def test_keeps_amounts_dates_and_titles(text: str) -> None:
    assert mask_pii(text) == text


def test_mixed_sentence() -> None:
    text = "저는 홍길동입니다. 010-1111-2222로 연락 주시고 120만원은 계좌 110-123-456789로 2026-04-30까지"
    masked = mask_pii(text)
    assert "홍길동" not in masked
    assert "010-1111-2222" not in masked
    assert "110-123-456789" not in masked
    assert "120만원" in masked
    assert "2026-04-30" in masked
