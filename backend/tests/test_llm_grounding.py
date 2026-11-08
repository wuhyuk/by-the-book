"""근거 구절 확인 테스트 (CLAUDE.md 절대 규칙 1). 금액·날짜 값은 입력 표기를 그대로 읽은 값이다."""

from datetime import date

import pytest

from llm.grounding import amounts_in, counts_in, dates_in, evidence_in_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("120만원 결제", {1_200_000}),
        ("120만 원", {1_200_000}),
        ("1,200,000원", {1_200_000}),
        ("1200000원", {1_200_000}),
        ("12만 5천원", {125_000}),
        ("1억 2천만원", {120_000_000}),
        ("5천원", {5_000}),
        ("60만", {600_000}),
        ("150,000, 결제", {150_000}),
        ("정상가 50만원인데 40만원에", {500_000, 400_000}),
        ("2026년 20회 120", set()),  # 단위·원·쉼표가 없는 수는 금액으로 보지 않는다
        ("백이십만원", set()),  # 한글 숫자는 읽지 않는다
    ],
)
def test_amounts(text: str, expected: set[int]) -> None:
    assert amounts_in(text) == expected


def test_counts() -> None:
    assert counts_in("총 20회 중 5회 이용, 3번 더") == {20, 5, 3}
    assert counts_in("120만원") == set()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-01-01부터", {date(2026, 1, 1)}),
        ("2026.4.30", {date(2026, 4, 30)}),
        ("2026/06/28까지", {date(2026, 6, 28)}),
        ("2026년 3월 31일에", {date(2026, 3, 31)}),
        ("3월 31일에", set()),  # 연도 없는 날짜는 읽지 않는다
        ("1년 계약", set()),
        ("2026-02-30", set()),  # 없는 날짜
    ],
)
def test_dates(text: str, expected: set[date]) -> None:
    assert dates_in(text) == expected


def test_evidence_in_text() -> None:
    text = "헬스장   1년 회원권을\n결제했어요"
    assert evidence_in_text("1년 회원권을 결제했어요", text)  # 공백 차이는 무시
    assert not evidence_in_text("2년 회원권", text)
    assert not evidence_in_text("", text)
    assert not evidence_in_text("   ", text)
    assert not evidence_in_text(None, text)
