"""세탁 계산 결과의 화면 표시 정보 (MVP_SPEC 12.4·12.5·12.7·12.8).

순수 함수만 둔다. LLM을 호출하지 않고 숫자를 새로 만들지 않는다.
DECISION_SENSITIVE 문구의 숫자는 엔진 결과 필드(ratio_percent, sensitivity_ratio_alt,
sensitivity_min, sensitivity_max)에서만 채운다 (CLAUDE.md 절대 규칙 1).
문구는 12절 표 그대로이며 [기본값 2026-11-10] 문구는 docs/sources/vs4_report.md에서 승인받는다.
"""

from pydantic import BaseModel, ConfigDict

from rules.badge import Badge
from rules.gym_display import (
    CONSULT_CHANNELS,
    CONSULT_MESSAGE,
    CitationCard,
    ConsultInfo,
    DisplayLine,
    SourceInfo,
)
from rules.gym_display import (
    FLAG_TEXTS as GYM_FLAG_TEXTS,
)
from rules.laundry import LaundryInput, LaundryResult
from rules.laundry_codes import (
    CommonFlag,
    LaundryCode,
    LaundryFlag,
    LaundryNotice,
    order_laundry_flags,
)
from rules.laundry_rule import Band, LaundryRule

C = CommonFlag
L = LaundryFlag
N = LaundryNotice

_COMMON_TEXTS: dict[LaundryCode, str] = {
    code: GYM_FLAG_TEXTS[next(f for f in GYM_FLAG_TEXTS if f.value == code.value)]
    for code in CommonFlag
}

FLAG_TEXTS: dict[LaundryCode, str] = {
    **_COMMON_TEXTS,
    L.UNSUPPORTED_SERVICE: (
        "무인세탁소(셀프빨래방) 등 세탁소에 맡기지 않은 경우는 이 서비스에서 지원하지 "
        "않습니다. 1372에 문의해 주세요."
    ),
    L.UNSUPPORTED_DAMAGE: (
        "세탁 지연 등 하자·분실이 아닌 피해는 기준표에 배상액 계산 방식이 없어 "
        "계산하지 않습니다. 1372에 문의해 주세요."
    ),
    L.MANUFACTURING_CAUSE: (
        "의복류 등 다른 품목 기준의 대상일 수 있습니다. 1372에 문의해 주세요."
    ),
    L.SET_PARTIAL_UNSUPPORTED: (
        "세트 의류의 일부만 손상·분실된 경우는 소비자분쟁해결기준의 기준표에 배상액 배분 "
        "규정이 있으나, 이번 버전에서는 지원하지 않습니다. 1372 또는 한국소비자원에 "
        "문의해 주세요."
    ),
    L.ATTACHMENT_UNSUPPORTED: (
        "탈부착 부속물(털, 칼라, 모자 등)이 손상된 경우는 소비자분쟁해결기준의 기준표에 "
        "규정이 있으나, 이번 버전에서는 지원하지 않습니다. 1372 또는 한국소비자원에 "
        "문의해 주세요."
    ),
    L.ITEM_NOT_IN_TABLE: (
        "이 세탁물은 고시의 품목별 평균 내용연수표에 없어 이 서비스에서는 계산하지 "
        "않습니다. 1372에 문의해 주세요."
    ),
    L.OFFER_BELOW_STANDARD_MIN: (
        "업체 제시액이 고시 기준으로 계산한 가장 작은 기준 금액보다도 적습니다."
    ),
    L.EXEMPTION_CLAIMED: (
        "확인서 교부나 장기 미회수에 해당하면 기준상 세탁업자의 책임이 면제될 수 있습니다."
    ),
    L.SPECIAL_AGREEMENT: "배상에 관한 특약이 있으면 기준상 특약을 따르게 되어 있습니다.",
    L.PARTIAL_FAULT_CLAIMED: (
        "고객에게도 일부 책임이 있으면 그만큼 공제하도록 되어 있어, 금액이 줄어들 수 있습니다."
    ),
    L.DAMAGED_ITEM_RETURN: (
        "손상된 세탁물을 돌려받으면 배상액 일부를 감액할 수 있도록 되어 있습니다."
    ),
    # DECISION_SENSITIVE는 결과 숫자로 채운다 (sensitivity_text)
}

NOTICE_TEXTS: dict[LaundryNotice, str] = {
    N.RESTORE_FIRST: (
        "기준상 하자가 생기면 세탁업자 비용으로 원상회복을 먼저 하고, 불가능할 때 "
        "손해배상을 합니다."
    ),
    N.UNPROVEN_FALLBACK: (
        "품명·구입가격·구입일을 입증하기 어려운 경우 기준상 세탁요금의 20배로 정해져 있습니다."
    ),
    N.RECEIPT_BASIS: (
        "기준상 배상액은 인수증에 적힌 품명·구입가격·구입일을 기준으로 정합니다. "
        "인수증이 없거나 빠진 내용이 있으면 고객이 입증하는 내용을 기준으로 합니다."
    ),
    N.NO_RECEIPT_LOSS: "인수증을 받지 못했다면 기준상 분실 책임은 세탁업소에 있습니다.",
    N.LAUNDRY_FEE_TERMS: (
        "세탁 표준약관을 사용한 계약이라면 세탁업자 책임으로 손상·분실된 세탁물의 "
        "세탁요금은 청구하지 않도록 되어 있습니다."
    ),
    N.CLAIM_PERIOD_TERMS: (
        "세탁 표준약관을 사용한 계약이라면 세탁물을 받은 날부터 6개월 안에 손해배상 등을 "
        "청구하도록 되어 있습니다."
    ),
}

DISCLAIMER = (
    "소비자분쟁해결기준(공정거래위원회 고시)으로 계산한 참고 결과이며 법적 판단이 아닙니다. "
    "이 기준은 분쟁 당사자 사이에 다른 의사표시가 없을 때 합의 또는 권고의 기준이 되며, "
    "기준상 이렇게 정해져 있다는 뜻입니다."
)


def _won(n: int) -> str:
    return f"{n:,}"


def sensitivity_text(result: LaundryResult) -> str:
    """DECISION_SENSITIVE 화면 한 줄 (12.4 형식). 숫자는 엔진 결과 필드에서만 가져온다."""
    lo, hi = result.sensitivity_min, result.sensitivity_max
    assert lo is not None and hi is not None
    causes = set(result.sensitivity_causes)
    rng = f"{_won(lo)}원~{_won(hi)}원"
    if causes == {"use_days"}:
        return (
            "고시에 정해져 있지 않은 사용일수 산입 방식(구입일을 세는지)에 따라 배상비율이 "
            f"{result.ratio_percent}%에서 {result.sensitivity_ratio_alt}%로 바뀌어, "
            f"기준 금액이 {rng}으로 달라질 수 있습니다."
        )
    if causes == {"rounding"}:
        # half up과 내림의 차이는 항상 1원이다 (12.4). 표시 단계에서 숫자를 계산하지 않는다.
        assert hi - lo == 1
        return (
            "고시에 정해져 있지 않은 원 미만 처리(내림·반올림)에 따른 "
            f"1원 차이가 있습니다 ({rng})."
        )
    return (
        "고시에 정해져 있지 않은 사용일수 산입 방식과 원 미만 처리에 따라 "
        f"기준 금액이 {rng}으로 달라질 수 있습니다."
    )


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LaundryRuleSource(_Model):
    name: str
    notice_number: str
    annex: str
    url: str
    effective_date: str
    last_amended: str
    retrieved_at: str


class LaundryDisplay(_Model):
    """세탁 결과 화면 표시 정보. 배지·금액은 LaundryResult에서 그대로 가져온다."""

    badge: Badge
    screen_line: DisplayLine | None
    other_flags: list[DisplayLine]
    notices: list[DisplayLine]
    citations: list[CitationCard]
    rule_source: LaundryRuleSource
    disclaimer: str
    consult: ConsultInfo | None


def flag_line(code: LaundryCode, result: LaundryResult) -> DisplayLine:
    if code == L.DECISION_SENSITIVE:
        return DisplayLine(code=code.value, text=sensitivity_text(result))
    return DisplayLine(code=code.value, text=FLAG_TEXTS[code])


def citation_cards(ids: list[str], rule: LaundryRule) -> list[CitationCard]:
    """인용 ID → 조문 원문·출처. 없는 ID는 오류."""
    notice = SourceInfo(
        name=f"{rule.source.name} ({rule.source.notice_number}) {rule.source.annex}",
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


RATIO_TABLE_ID = "laundry_ratio_table"
LIFESPAN_TABLE_ID = "laundry_lifespan_table"


def _days(n: int) -> str:
    return f"{n:,}일"


def _band_text(band: Band) -> str:
    """원문 표 칸의 사용일수 구간 (규칙 JSON 값 그대로)."""
    if band.max_days is None:
        return f"사용일수 {_days(band.min_days)} 이상"
    return f"사용일수 {band.min_days:,}~{_days(band.max_days)}"


def applied_ratio_text(result: LaundryResult, rule: LaundryRule) -> str | None:
    """배상비율표에서 이번 계산에 적용한 칸 (2026-11-12). 숫자는 엔진 결과와 규칙 JSON 값만 쓴다.

    사용일수 산입 방식이 원인인 결정 민감(🔍)이면 대안으로 조회한 칸도 같이 적는다.
    대안 칸은 같은 내용연수 행에서 엔진이 낸 대안 비율(sensitivity_ratio_alt)의 칸이다.
    """
    life, ratio, days = result.life_years, result.ratio_percent, result.use_days
    if result.method != "ratio" or life is None or ratio is None or days is None:
        return None
    row = next(r for r in rule.ratio_table.rows if r.life_years == life)
    band = rule.ratio_table.band(life, days)
    assert band.ratio_percent == ratio  # 엔진 결과와 표 값이 같아야 한다
    text = (
        f"적용한 칸: 내용연수 {life}년 행, {_band_text(band)} 칸 "
        f"(이번 사용일수 {_days(days)}) → 배상비율 {ratio}%"
    )
    alt = result.sensitivity_ratio_alt
    if "use_days" in result.sensitivity_causes and alt is not None:
        alt_band = next(b for b in row.bands if b.ratio_percent == alt)
        text += (
            "\n사용일수 산입 방식(구입일을 세는지)에 따라 갈리는 칸: "
            f"내용연수 {life}년 행, {_band_text(alt_band)} 칸 → 배상비율 {alt}%"
        )
    return text


def applied_item_text(
    inp: LaundryInput, result: LaundryResult, rule: LaundryRule
) -> str | None:
    """평균 내용연수표에서 이번 계산에 적용한 품목 행 (2026-11-12). 이름·연수는 규칙 JSON 값 그대로."""
    if result.method != "ratio" or result.life_years is None or inp.item_key is None:
        return None
    row = next((r for r in rule.lifespan_table.rows if r.id == inp.item_key), None)
    if row is None:
        return None
    name = row.item or row.category
    variant = row.variant(inp.variant_key) if inp.variant_key and row.variants else None
    years = variant.years if variant is not None else row.years
    assert years == result.life_years  # 엔진 결과와 표 값이 같아야 한다
    label = f"{name} ({variant.label})" if variant is not None else name
    return f"적용한 품목: {label} → 내용연수 {years}년"


def _with_applied(
    cards: list[CitationCard],
    result: LaundryResult,
    rule: LaundryRule,
    inp: LaundryInput | None,
) -> list[CitationCard]:
    """표 인용 카드에 이번 계산에 적용한 칸을 덧붙인다 (원문 한 줄은 그대로 둔다)."""
    extra = {RATIO_TABLE_ID: applied_ratio_text(result, rule)}
    if inp is not None:
        extra[LIFESPAN_TABLE_ID] = applied_item_text(inp, result, rule)
    out: list[CitationCard] = []
    for card in cards:
        add = extra.get(card.id)
        text = f"{card.text}\n{add}" if add else card.text
        out.append(card.model_copy(update={"text": text}))
    return out


def build_laundry_display(
    result: LaundryResult, rule: LaundryRule, inp: LaundryInput | None = None
) -> LaundryDisplay:
    """LaundryResult → 화면 표시 정보 (화면 한 줄 1개 + 나머지 접기, 12.4).

    inp를 넘기면 평균 내용연수표 카드에 적용한 품목 행을 덧붙인다 (API·문안은 항상 넘긴다).
    """
    lines = [flag_line(c, result) for c in order_laundry_flags(result.flags)]
    s = rule.source
    return LaundryDisplay(
        badge=result.badge,
        screen_line=lines[0] if lines else None,
        other_flags=lines[1:],
        notices=[
            DisplayLine(code=n.value, text=NOTICE_TEXTS[n]) for n in result.notices
        ],
        citations=_with_applied(
            citation_cards(result.citations, rule), result, rule, inp
        ),
        rule_source=LaundryRuleSource(
            name=s.name,
            notice_number=s.notice_number,
            annex=s.annex,
            url=s.url,
            effective_date=s.effective_date,
            last_amended=s.last_amended,
            retrieved_at=s.retrieved_at,
        ),
        disclaimer=DISCLAIMER,
        # ❔에만 상담 창구 (MISSING_REQUIRED·INVALID_INPUT은 다시 입력하면 된다, 12.5)
        consult=ConsultInfo(message=CONSULT_MESSAGE, channels=list(CONSULT_CHANNELS))
        if result.badge == Badge.UNDETERMINABLE
        else None,
    )


class LaundryItemOption(_Model):
    """화면 품목 선택지 (표 행의 ID·이름 그대로)."""

    key: str
    label: str
    examples: str | None
    variant_by: str | None
    variants: list[DisplayLine]


def item_options(rule: LaundryRule) -> list[LaundryItemOption]:
    """평균 내용연수표 행 → 선택지. 내용연수 숫자는 넣지 않는다 (엔진만 조회)."""
    return [
        LaundryItemOption(
            key=r.id,
            label=r.label,
            examples=r.examples,
            variant_by=r.variant_by,
            variants=[DisplayLine(code=v.key, text=v.label) for v in r.variants or []],
        )
        for r in rule.lifespan_table.rows
    ]
