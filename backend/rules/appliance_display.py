"""가전 P2 결과의 화면 표시 정보 (MVP_SPEC 13절, docs/sources/appliance_cases.md 3.5·3.6, 승인 2026-11-15).

순수 함수만 둔다. LLM을 호출하지 않고 숫자를 새로 만들지 않는다. 숫자는 엔진 결과 필드와 규칙 JSON 표 값에서만 쓴다.
"""

from pydantic import BaseModel, ConfigDict

from rules.appliance import CAUSE_NAMES, ApplianceInput, ApplianceResult
from rules.appliance_codes import (
    ApplianceCode,
    ApplianceFlag,
    ApplianceNotice,
    order_appliance_flags,
)
from rules.appliance_rule import ApplianceRule
from rules.badge import Badge
from rules.gym_display import (
    CONSULT_CHANNELS,
    CONSULT_MESSAGE,
    CitationCard,
    ConsultInfo,
    DisplayLine,
    SourceInfo,
)
from rules.laundry_codes import CommonFlag
from rules.laundry_display import DISCLAIMER as LAUNDRY_DISCLAIMER
from rules.laundry_display import FLAG_TEXTS as LAUNDRY_FLAG_TEXTS
from rules.offer_gap import offer_gap_text, optional_field

A = ApplianceFlag
N = ApplianceNotice

# 보고서 3.6 [제안] 승인 문구 (2026-11-15 Q7). 공통 코드와 ⚠️는 세탁 문구 그대로.
FLAG_TEXTS: dict[ApplianceCode, str] = {
    **{c: LAUNDRY_FLAG_TEXTS[c] for c in CommonFlag},
    A.APPLIANCE_ITEM_NOT_SUPPORTED: (
        "이 서비스는 가전 중 TV·냉장고·세탁기·전기청소기·노트북만 계산합니다. "
        "그 밖의 품목은 1372에 문의해 주세요."
    ),
    A.PARTS_AVAILABLE: (
        "수리용 부품이 있어 수리할 수 있는 경우는 이 서비스가 계산하는 기준(부품이 없어 생긴 피해)의 "
        "대상이 아닙니다. 1372에 문의해 주세요."
    ),
    A.WITHIN_WARRANTY: (
        "수리 접수일이 품질보증기간 안이라 이 서비스가 계산하는 기준(품질보증기간 경과 후)과 다른 기준이 "
        "적용됩니다. 1372에 문의해 주세요."
    ),
    A.OUTSIDE_PARTS_PERIOD: (
        "수리 접수일이 부품보유기간이 지난 뒤로 보여 이 기준(부품보유기간 이내)의 대상이 아닐 수 있어 "
        "계산하지 않습니다. 1372에 문의해 주세요."
    ),
    A.OFFER_BELOW_STANDARD_MIN: LAUNDRY_FLAG_TEXTS[A.OFFER_BELOW_STANDARD_MIN.value],  # type: ignore[index]
    A.PERIOD_BOUNDARY: (
        "수리 접수일이 품질보증기간 또는 부품보유기간이 끝나는 날과 겹쳐, 날짜를 세는 방식에 따라 "
        "이 기준의 대상인지가 달라질 수 있습니다."
    ),
    A.PARTS_PERIOD_UNCONFIRMED: (
        "제조일을 입력하지 않아 부품보유기간(제조일부터 계산) 안에 접수되었는지 확인하지 못했습니다."
    ),
    A.CERTIFICATE_UNCONFIRMED: (
        "품질보증서의 품질보증기간·부품보유기간을 확인하지 않아 고시 표의 기간으로 계산했습니다. "
        "보증서에 더 긴 기간이 적혀 있으면 결과가 달라질 수 있습니다."
    ),
    # DECISION_SENSITIVE는 결과 숫자로 채운다 (sensitivity_text)
}

NOTICE_TEXTS: dict[ApplianceNotice, str] = {
    N.RECEIVED_DATE_BASIS: (
        "기준상 품질보증기간이 지났는지는 수리를 사업자에게 접수한 날을 기준으로 판단합니다."
    ),
    # [제안] 2026-11-15 사용자 지시 (D-2·D-3·D-5 가정을 드러냄)
    N.USED_MONTHS_BASIS: "사용 개월은 구입일(인도일)부터 수리 접수일까지 월 단위로 센 값입니다.",
}

DISCLAIMER = LAUNDRY_DISCLAIMER  # 보고서 3.6: 세탁 고지(12.8)와 같은 문장


def _won(n: int) -> str:
    return f"{n:,}"


def sensitivity_text(result: ApplianceResult) -> str:
    lo, hi = result.sensitivity_min, result.sensitivity_max
    assert lo is not None and hi is not None
    rng = f"{_won(lo)}원~{_won(hi)}원"
    if result.sensitivity_causes == ["rounding"]:
        return (
            "고시에 정해져 있지 않은 원 미만 처리(내림·반올림)에 따른 "
            f"1원 차이가 있습니다 ({rng})."
        )
    names = "·".join(CAUSE_NAMES[c] for c in result.sensitivity_causes)
    return f"고시에 정해져 있지 않은 {names}에 따라 기준 금액이 {rng}으로 달라질 수 있습니다."


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApplianceRuleSource(_Model):
    name: str
    notice_number: str
    annex: str
    url: str
    effective_date: str
    last_amended: str
    retrieved_at: str


class ApplianceDisplay(_Model):
    badge: Badge
    screen_line: DisplayLine | None
    other_flags: list[DisplayLine]
    notices: list[DisplayLine]
    citations: list[CitationCard]
    rule_source: ApplianceRuleSource
    disclaimer: str
    consult: ConsultInfo | None
    # 제시액 차액 한 줄 (기능 플래그 offer_gap, MVP_SPEC 14.1). 없으면 응답에서 빠진다.
    offer_gap_text: str | None = optional_field()


def flag_line(code: ApplianceCode, result: ApplianceResult) -> DisplayLine:
    if code == A.DECISION_SENSITIVE:
        return DisplayLine(code=code.value, text=sensitivity_text(result))
    return DisplayLine(code=code.value, text=FLAG_TEXTS[code])


def citation_cards(ids: list[str], rule: ApplianceRule) -> list[CitationCard]:
    notice = SourceInfo(
        name=f"{rule.source.name} ({rule.source.notice_number})",
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
                CitationCard(id=c.id, label=c.label, text=c.text, source=notice)
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


def applied_texts(
    inp: ApplianceInput, result: ApplianceResult, rule: ApplianceRule
) -> dict[str, str]:
    """표 카드에 덧붙이는 "적용한 칸" (품목 행, 내용연수, 사용 개월). 숫자는 결과 필드와 JSON 표 값만."""
    if not result.calculated or inp.item_key is None or result.row_id is None:
        return {}
    item = rule.supported(inp.item_key)
    row = rule.items.row(result.row_id)
    assert item is not None and row is not None
    assert result.life_months is not None and result.used_months is not None
    return {
        "annex3_items": (
            f"적용한 칸: {item.label} → '{row.annex3_label}' 행, 품질보증기간 {row.warranty_months}개월, "
            f"부품보유기간 제조일로부터 {row.parts_years}년"
        ),
        "annex4": (
            f"적용한 값: 내용연수 {result.life_months}개월 (부품보유기간, 월할계산), "
            f"이번 사용 개월 {result.used_months}개월"
        ),
    }


def build_appliance_display(
    result: ApplianceResult, rule: ApplianceRule, inp: ApplianceInput | None = None
) -> ApplianceDisplay:
    lines = [flag_line(c, result) for c in order_appliance_flags(result.flags)]
    extra = applied_texts(inp, result, rule) if inp is not None else {}
    cards = [
        c.model_copy(update={"text": f"{c.text}\n{extra[c.id]}"})
        if c.id in extra
        else c
        for c in citation_cards(result.citations, rule)
    ]
    s = rule.source
    return ApplianceDisplay(
        badge=result.badge,
        screen_line=lines[0] if lines else None,
        other_flags=lines[1:],
        notices=[
            DisplayLine(code=n.value, text=NOTICE_TEXTS[n]) for n in result.notices
        ],
        citations=cards,
        rule_source=ApplianceRuleSource(
            name=s.name,
            notice_number=s.notice_number,
            annex=s.annex,
            url=s.url,
            effective_date=s.effective_date,
            last_amended=s.last_amended,
            retrieved_at=s.retrieved_at,
        ),
        disclaimer=DISCLAIMER,
        consult=ConsultInfo(message=CONSULT_MESSAGE, channels=list(CONSULT_CHANNELS))
        if result.badge == Badge.UNDETERMINABLE
        else None,
        offer_gap_text=(
            offer_gap_text(result.offer_gap) if result.offer_gap is not None else None
        ),
    )


class ApplianceItemOption(_Model):
    key: str
    label: str


def item_options(rule: ApplianceRule) -> list[ApplianceItemOption]:
    """지원 품목 선택지 (규칙 JSON params.p2.supported_items 순서). 기간 숫자는 넣지 않는다."""
    return [
        ApplianceItemOption(key=s.key, label=s.label)
        for s in rule.params.p2.supported_items
    ]
