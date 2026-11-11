"""설명·업체용 문안 공통 부분 (MVP_SPEC 6절 /api/guide, 2026-11-11 결정: LLM 없이 템플릿).

순수 함수만 둔다. llm 패키지를 import하지 않는다. 숫자는 규칙 엔진 결과 필드에서만 가져오고
여기서 새로 계산하지 않는다 (CLAUDE.md 절대 규칙 1). 화면 문구·인용은 rules/*_display.py를 그대로 쓴다.

문안 원칙 (CLAUDE.md 2절 업체용 요약 문안 가이드):
- 모든 문안에 "참고용이며 법률 자문이 아닙니다" 한 줄을 넣는다.
- "기준상 이렇게 정해져 있다" 표현을 쓰고, 단정 표현(FORBIDDEN_TERMS)을 쓰지 않는다.
- 업체용 문안은 사실·기준 요약이다. 소송·법적 조치, 기한을 정한 최고, 수신/발신/제목 서식,
  법조문을 근거로 한 의무 주장을 넣지 않는다. 사용자가 입력하지 않은 사실을 만들지 않는다.
"""

from pydantic import BaseModel, ConfigDict

from rules.gym_display import CitationCard, DisplayLine

DISCLAIMER_LINE = "참고용이며 법률 자문이 아닙니다."
CONSULT_1372_LINE = "1372 소비자상담센터(국번 없이 1372)에 상담해 보세요."
REVIEW_HEADER = "아래 사항에 따라 금액이 달라질 수 있어 확인이 필요합니다."
NO_CALC_LINE = "계산하지 않았으므로 기준 금액과 업체용 문안은 만들지 않았습니다."
COMPANY_CLOSING = "위 기준을 참고해 금액을 다시 확인해 주시면 감사하겠습니다."
COMPANY_REVIEW_NOTE = (
    "다만 고시에 정해져 있지 않은 부분이나 확인이 필요한 사정이 있어 "
    "금액은 달라질 수 있습니다."
)

# 문안에 쓰지 않는 단정·법적 효력·법률 절차 표현 (테스트가 모든 출력에서 확인한다)
FORBIDDEN_TERMS: tuple[str, ...] = (
    "위법",
    "불법",
    "승소",
    "패소",
    "반드시",
    "무효",
    "효력이 없",
    "소송",
    "법적 조치",
    "내용증명",
    "까지 지급",
    "수신:",
    "발신:",
    "제목:",
)

# 템플릿에 직접 쓴 고정 문구 (숫자 출처 검사에서 고정 숫자로 인정하는 범위)
FIXED_TEXTS: tuple[str, ...] = (
    DISCLAIMER_LINE,
    CONSULT_1372_LINE,
    REVIEW_HEADER,
    NO_CALC_LINE,
    COMPANY_CLOSING,
    COMPANY_REVIEW_NOTE,
)


class Guide(BaseModel):
    """설명 문장, 업체용 문안(❔·계산 안 함이면 None), 근거 조항 카드."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    explanation: list[str]
    company_message: str | None
    citations: list[CitationCard]


def won(n: int) -> str:
    """금액 표시 (천 단위 쉼표 + 원). 숫자는 호출한 쪽이 결과 필드에서 가져온다."""
    return f"{n:,}원"


def amount_or_range(lo: int, hi: int) -> str:
    """같으면 한 금액, 다르면 범위."""
    return won(lo) if lo == hi else f"{won(lo)}~{won(hi)}"


def basis_line(citations: list[CitationCard]) -> str | None:
    """근거 조항 이름 한 줄. 인용이 없으면 None."""
    if not citations:
        return None
    return "근거: " + ", ".join(c.label for c in citations)


def review_lines(lines: list[DisplayLine]) -> list[str]:
    """확인 사항 머리말 + 사유 문구 (화면 문구 그대로)."""
    if not lines:
        return []
    return [REVIEW_HEADER, *(f"- {line.text}" for line in lines)]


def undeterminable_guide(
    screen_line: DisplayLine | None, citations: list[CitationCard]
) -> Guide:
    """❔ 판단 불가: 금액 없음, 업체용 문안 없음, 1372 안내만."""
    explanation = [screen_line.text] if screen_line else []
    explanation += [CONSULT_1372_LINE, DISCLAIMER_LINE]
    return Guide(explanation=explanation, company_message=None, citations=citations)


def not_calculated_guide(
    screen_line: DisplayLine | None,
    citations: list[CitationCard],
    *,
    consult: bool,
) -> Guide:
    """🔍 계산 안 함 (누락·입력 오류·유효기간 이후 도달): 금액 없음, 업체용 문안 없음."""
    explanation = [screen_line.text] if screen_line else []
    explanation.append(NO_CALC_LINE)
    if consult:
        explanation.append(CONSULT_1372_LINE)
    explanation.append(DISCLAIMER_LINE)
    return Guide(explanation=explanation, company_message=None, citations=citations)
