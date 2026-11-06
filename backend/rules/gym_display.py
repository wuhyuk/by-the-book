"""헬스장 계산 결과의 화면 표시 정보 (MVP_SPEC 5.4·5.5·5.7, 8.1 VS2 기본값).

순수 함수만 둔다. LLM을 호출하지 않고 숫자를 새로 만들지 않는다.
사유·안내 코드를 화면 문구로 바꾸고, 인용 ID를 규칙 JSON의 조문 원문으로 연결한다.
문구는 MVP_SPEC 5.4·5.5 초안 그대로다. 스펙에 문구가 없는 항목(❔ 사유 한 줄, 고지,
상담 창구 안내)은 초안이며 docs/sources/vs2_pending_approval.md에서 승인받는다.
"""

from pydantic import BaseModel, ConfigDict

from rules.badge import (
    NO_CALC_CODES,
    Badge,
    FlagCode,
    NoticeCode,
    order_flags,
)
from rules.gym import GymResult
from rules.loader import GymRule

F = FlagCode
N = NoticeCode

# ---- 사유 코드 화면 한 줄 ----

# ❔ 판단 불가 (5.2 순서 1~8): 스펙에 화면 문구가 없어 초안이다 (승인 대기 보고서).
# UNSUPPORTED_INDUSTRY만 10절 문구를 그대로 쓴다.
_UNDETERMINABLE_TEXTS: dict[FlagCode, str] = {
    F.JUDGMENT_REQUESTED: (
        "승패나 법적 효력에 대한 판단은 이 서비스에서 하지 않습니다. "
        "아래 상담 창구에 문의해 주세요."
    ),
    F.UNSUPPORTED_INDUSTRY: "아직 지원하지 않는 업종입니다. 1372에 문의하세요",
    F.ACADEMY_LAW: (
        "학원법 시행령이 적용되는 계약은 이 기준(고시)의 적용 대상에서 빠져 있어 "
        "계산하지 않았습니다."
    ),
    F.WITHDRAWAL: (
        "청약철회로 해지하는 경우에는 이 기준(고시)이 적용되지 않아 계산하지 않았습니다."
    ),
    F.BUSINESS_FAULT: (
        "사업자 사정으로 해지하는 경우는 아직 지원하지 않습니다 (다음 확장 예정)."
    ),
    F.FORCE_MAJEURE: "천재지변 등 불가항력으로 해지하는 경우는 아직 지원하지 않습니다.",
    F.PERIOD_UNDER_28_DAYS: (
        "계약 기간이 1개월보다 짧아 이 기준(계속거래)의 적용 대상인지 확인할 수 없어 "
        "계산하지 않았습니다."
    ),
    F.NO_REFUND_LIMIT_CLAUSE: (
        "계약서에 중도 해지 시 환급 제한이나 위약금 조항이 없다고 답해 "
        "이 기준(계속거래)의 적용 대상인지 확인할 수 없어 계산하지 않았습니다."
    ),
}

# 🔍·⚠️ 사유: MVP_SPEC 5.4 표의 화면 한 줄 그대로 (초안, 사용자 검토 대상).
_SPEC_FLAG_TEXTS: dict[FlagCode, str] = {
    F.MISSING_REQUIRED: (
        "계산에 필요한 정보가 빠져 있어 계산하지 않았습니다. 빠진 항목을 입력해 주세요."
    ),
    F.INVALID_INPUT: "입력한 값끼리 맞지 않아 계산하지 않았습니다. 다시 확인해 주세요.",
    F.NOTICE_AFTER_VALIDITY: (
        "해지 의사가 유효기간이 끝난 뒤에 전달되어 이 서비스에서는 계산하지 않습니다. "
        "1372 등 상담 창구에 문의해 주세요."
    ),
    F.OFFER_BELOW_B: "업체 제시액이 정상가 기준으로 계산한 기준 금액보다도 적습니다.",
    F.PENALTY_ABOVE_CAP: (
        "계약서상 위약금이 고시의 위약금 상한(총계약대금의 10%)보다 큽니다. "
        "계산에는 상한을 공제했습니다."
    ),
    F.SCOPE_UNCERTAIN_PT_ONLY: (
        "PT만 계약한 경우 이 기준이 적용되는지 확실하지 않아, "
        "헬스·피트니스 기준으로 계산했습니다."
    ),
    F.PERIOD_ONE_MONTH_BOUNDARY: (
        "계약 기간이 1개월 경계에 있어(날짜를 세는 방식에 따라 28~31일) "
        "이 기준이 적용되는지 확인이 필요합니다."
    ),
    F.REFUND_LIMIT_CLAUSE_UNKNOWN: (
        "계약서에 중도 해지 시 환급 제한이나 위약금 조항이 있는지 확인이 필요합니다."
    ),
    F.WITHDRAWAL_STATUS_UNCONFIRMED: (
        "청약철회 대상이 아니거나 철회 기간이 지났는지 확인되지 않았습니다."
    ),
    F.SESSION_VALIDITY_MISSING: (
        "횟수제 이용권의 유효기간을 입력하지 않아 이 기준의 적용 여부를 "
        "확인하지 못했습니다."
    ),
    F.REFUND_BASIS_UNKNOWN: (
        "계약할 때 정한 환급 기준(기간 또는 횟수)을 알 수 없어 "
        "두 기준으로 모두 계산했습니다."
    ),
    F.RULE_UNVERIFIED: "계산에 쓴 기준 값 중 원문 확인이 끝나지 않은 값이 있습니다.",
    F.LIST_PRICE_NOT_USABLE: (
        "정상가(할인 전 가격)를 쓸 수 없어 정상가 기준 계산을 하지 못했습니다."
    ),
    F.INTERPRETATION_DEPENDENT: (
        "고시에 이용분 계산 방식이 정해져 있지 않아 금액이 해석에 따라 "
        "달라질 수 있습니다."
    ),
    F.USAGE_STARTED: "이용을 시작한 뒤 해지해 이용분 공제가 들어갑니다.",
    F.POSTPONEMENT: "이용 연기 기간이 있어 결과가 달라질 수 있습니다.",
}

FLAG_TEXTS: dict[FlagCode, str] = {**_UNDETERMINABLE_TEXTS, **_SPEC_FLAG_TEXTS}
DRAFT_FLAG_CODES = frozenset(_UNDETERMINABLE_TEXTS) - {F.UNSUPPORTED_INDUSTRY}

# ---- 안내 코드 문구 (5.5, 결과 화면용) ----

NOTICE_TEXTS: dict[NoticeCode, str] = {
    N.NO_LIST_PRICE: (
        "업체가 정상가(할인 전 가격) 기준으로 이용분을 계산하면 "
        "환급액이 이보다 적을 수 있습니다."
    ),
    N.LIST_PRICE_BELOW_TOTAL: "정상가를 다시 확인해 주세요.",
    N.OFFER_BETWEEN_A_AND_B: (
        "업체 제시액은 두 계산 방식(실제 부담액 기준 A, 정상가 기준 B)의 "
        "결과 사이에 있습니다."
    ),
    N.PENALTY_INPUT_MISSING: (
        "계약서상 위약금을 입력하지 않아 위약금 상한을 공제했습니다. "
        "실제 위약금이 이보다 낮으면 환급액은 더 커집니다."
    ),
    N.STANDARD_TERMS_PENALTY: (
        "표준약관을 사용한 계약이라면 위약금이 이용료의 1/10로 정해져 있어 "
        "이 최소 환급액과 실제 환급액이 같거나 가까울 수 있습니다. "
        "계약서의 위약금 조항을 확인해 보세요."
    ),
    N.NEGATIVE_REFUND_ZEROED: (
        "공제 항목의 합계가 지급한 금액보다 커서 기준상 환급액은 0원으로 계산됩니다. "
        "추가로 내야 하는 금액이 있는지는 이 서비스에서 판단하지 않습니다. "
        "1372에 문의해 주세요."
    ),
    N.POSTPONEMENT_INPUT: "연기 기간이 있으면 결과가 달라질 수 있습니다.",
    N.PERIOD_CHECK: "계약서의 이용기간과 연기 내역을 확인해 주세요.",
    N.WITHDRAWAL_INFO: (
        "계약서를 받은 뒤 짧은 기간(방문판매·전화권유판매 14일, 할부계약·통신판매 7일 등) "
        "안이라면 청약철회가 가능할 수 있고, 그 경우에는 이 기준이 적용되지 않습니다."
    ),
    N.PT_ONLY_QUESTION: "PT만 계약하셨나요?",  # 입력 단계 질문. 엔진은 내지 않는다.
}

# 청약철회 ❔ 안내 문구 (5.2, WITHDRAWAL)
WITHDRAWAL_GUIDE = (
    "계약서를 받은 뒤 짧은 기간(방문판매·전화권유판매는 14일, 할부계약·통신판매는 7일 등) "
    "안에 청약을 철회하는 경우에는 이 기준(고시)이 적용되지 않습니다 (고시 제3조 ②). "
    "철회 가능 여부는 1372에 문의해 주세요."
)

# ---- 고지·상담 창구 (초안, 승인 대기 보고서) ----

# 고시 제2019-9호(제1조~제8조)와 근거 조항 방문판매법 제32조 ④ 원문에 구속력 여부를 정한
# 문구가 없어 "참고 결과이며 법적 판단이 아님" 취지로 쓴다 (2026-11-06 Q1, 승인 대기 보고서).
DISCLAIMER = (
    "공정거래위원회 고시 기준으로 계산한 참고 결과이며 법적 판단이 아닙니다. "
    "기준상 이렇게 정해져 있다는 뜻이며, 실제 환급 여부나 금액을 확정하지 않습니다."
)

CONSULT_NO_CALC_CODES = frozenset(NO_CALC_CODES - {F.MISSING_REQUIRED, F.INVALID_INPUT})

CONSULT_MESSAGE = "이 결과는 아래 상담 창구에 문의해 주세요."
CONSULT_CHANNELS: tuple[str, ...] = (
    "1372",
    "한국소비자원 피해구제",
    "대한법률구조공단 ☎132",
)


# ---- 출력 모델 ----


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DisplayLine(_Model):
    code: str
    text: str


class SourceInfo(_Model):
    name: str
    url: str
    retrieved_at: str


class CitationCard(_Model):
    id: str
    label: str
    text: str
    source: SourceInfo


class RuleSource(_Model):
    name: str
    notice_number: str
    url: str
    effective_date: str
    last_amended: str
    retrieved_at: str


class ConsultInfo(_Model):
    message: str
    channels: list[str]


class GymDisplay(_Model):
    """결과 화면 표시 정보. 배지·금액은 GymResult에서 그대로 가져오고 새로 만들지 않는다."""

    badge: Badge
    screen_line: DisplayLine | None
    other_flags: list[DisplayLine]
    notices: list[DisplayLine]
    citations: list[CitationCard]
    rule_source: RuleSource
    disclaimer: str
    consult: ConsultInfo | None
    withdrawal_guide: str | None


# ---- 함수 ----


def _flag_line(code: FlagCode) -> DisplayLine:
    return DisplayLine(code=code.value, text=FLAG_TEXTS[code])


def citation_cards(ids: list[str], rule: GymRule) -> list[CitationCard]:
    """인용 ID를 규칙 JSON의 조문 원문·출처로 바꾼다. 없는 ID는 오류."""
    notice_source = SourceInfo(
        name=rule.source.name,
        url=rule.source.url,
        retrieved_at=rule.source.retrieved_at,
    )
    clauses = {c.id: c for c in rule.clauses}
    related = {c.id: c for c in rule.related_clauses}
    cards: list[CitationCard] = []
    for cid in ids:
        if cid in clauses:
            c = clauses[cid]
            cards.append(
                CitationCard(id=c.id, label=c.label, text=c.text, source=notice_source)
            )
        elif cid in related:
            r = related[cid]
            cards.append(
                CitationCard(
                    id=r.id,
                    label=r.label,
                    text=r.text,
                    source=SourceInfo(
                        name=r.source.name,
                        url=r.source.url,
                        retrieved_at=r.source.retrieved_at,
                    ),
                )
            )
        else:
            raise ValueError(f"규칙 JSON에 없는 조항 ID: {cid}")
    return cards


def build_display(result: GymResult, rule: GymRule) -> GymDisplay:
    """GymResult → 화면 표시 정보 (5.4 화면 한 줄 1개 + 나머지 접기)."""
    ordered = order_flags(result.flags)
    lines = [_flag_line(code) for code in ordered]
    # 상담 창구: ❔와 계산하지 않은 🔍 중 CONSULT_NO_CALC_CODES (5.5 부여 규칙, 2026-11-06 Q2).
    # MISSING_REQUIRED·INVALID_INPUT은 다시 입력하면 되므로 붙이지 않는다.
    needs_consult = result.badge == Badge.UNDETERMINABLE or (
        not result.calculated and any(code in CONSULT_NO_CALC_CODES for code in ordered)
    )
    s = rule.source
    return GymDisplay(
        badge=result.badge,
        screen_line=lines[0] if lines else None,
        other_flags=lines[1:],
        notices=[
            DisplayLine(code=n.value, text=NOTICE_TEXTS[n]) for n in result.notices
        ],
        citations=citation_cards(result.citations, rule),
        rule_source=RuleSource(
            name=s.name,
            notice_number=s.notice_number,
            url=s.url,
            effective_date=s.effective_date,
            last_amended=s.last_amended,
            retrieved_at=s.retrieved_at,
        ),
        disclaimer=DISCLAIMER,
        consult=(
            ConsultInfo(message=CONSULT_MESSAGE, channels=list(CONSULT_CHANNELS))
            if needs_consult
            else None
        ),
        withdrawal_guide=WITHDRAWAL_GUIDE if F.WITHDRAWAL in ordered else None,
    )
