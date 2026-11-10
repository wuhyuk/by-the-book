"""세탁 규칙 JSON 로더 (MVP_SPEC 12절, backend/data/rules/laundry_damage.json).

헬스장 로더(rules/loader.py)와 같은 방식이다: json.loads(parse_float=Decimal) + Pydantic v2 strict.
모델은 JSON 키 이름 그대로 두고, 엔진이 전제로 삼는 규칙 문자열은 Literal로 고정한다.
표 구조(내용연수 1~6년, 구간이 0부터 빈틈·겹침 없이 이어짐, 품목 ID 중복 없음)는 로드 시점에 확인한다.
"""

import json
from decimal import Decimal
from functools import cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from rules.loader import RULES_DIR, Verification

RULE_ID = "laundry_damage"
LIFE_YEARS = range(1, 7)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class AnnexFiles(_Model):
    hwpx_flSeq: str
    pdf_flSeq: str
    pdf_pages: str


class LaundrySource(_Model):
    name: str
    notice_number: str
    url: str
    permalink: str
    effective_date: str
    last_amended: str
    retrieved_at: str
    annex: str
    annex_files: AnnexFiles


class Band(_Model):
    min_days: int
    max_days: int | None
    ratio_percent: int


class RatioRow(_Model):
    life_years: int
    bands: list[Band]

    @model_validator(mode="after")
    def _contiguous(self) -> "RatioRow":
        if not self.bands or self.bands[0].min_days != 0:
            raise ValueError("배상비율표 행은 0일부터 시작해야 합니다.")
        for prev, nxt in zip(self.bands, self.bands[1:], strict=False):
            if prev.max_days is None or nxt.min_days != prev.max_days + 1:
                raise ValueError("배상비율표 구간에 빈틈이나 겹침이 있습니다.")
        if self.bands[-1].max_days is not None:
            raise ValueError("배상비율표 마지막 칸은 상한이 없어야 합니다.")
        return self


class RatioTable(_Model):
    basis: str
    use_days_definition: str
    rows: list[RatioRow]
    verified: bool
    verification: Verification

    @model_validator(mode="after")
    def _years(self) -> "RatioTable":
        if [r.life_years for r in self.rows] != list(LIFE_YEARS):
            raise ValueError("배상비율표 행은 내용연수 1~6년이어야 합니다.")
        return self

    def band(self, life_years: int, days: int) -> Band:
        """내용연수 행에서 사용일수가 속한 칸."""
        row = next(r for r in self.rows if r.life_years == life_years)
        return next(
            b
            for b in row.bands
            if b.min_days <= days and (b.max_days is None or days <= b.max_days)
        )


class Variant(_Model):
    key: str
    label: str
    years: int


class YearsScopeCheck(_Model):
    method: str
    limit: str
    checked_at: str
    user_checked: bool


class LifespanRow(_Model):
    id: str
    category: str
    item: str | None
    material_text: str | None = None
    use_text: str | None = None
    examples: str | None = None
    years: int | None = None
    variant_by: Literal["use", "material"] | None = None
    variants: list[Variant] | None = None
    footnote: str | None = None
    source_note: str | None = None
    years_applies_to_all_materials: bool | None = None
    years_applies_to_all_materials_in_source: bool | None = None
    years_alternative: None = None
    years_alternative_note: str | None = None
    years_scope_check: YearsScopeCheck | None = None

    @model_validator(mode="after")
    def _one_value_kind(self) -> "LifespanRow":
        if (self.years is None) == (self.variants is None):
            raise ValueError(f"{self.id}: years와 variants 중 하나만 있어야 합니다.")
        if (self.variants is None) != (self.variant_by is None):
            raise ValueError(f"{self.id}: variants와 variant_by는 함께 있어야 합니다.")
        values = [self.years] if self.years is not None else []
        values += [v.years for v in self.variants or []]
        if any(v not in LIFE_YEARS for v in values):
            raise ValueError(f"{self.id}: 내용연수는 1~6년이어야 합니다.")
        keys = [v.key for v in self.variants or []]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{self.id}: 소재·용도 키가 중복됩니다.")
        return self

    @property
    def label(self) -> str:
        """화면용 품목 이름 (분류 + 품목, 원문 그대로)."""
        return self.category if self.item is None else f"{self.category} > {self.item}"

    def variant(self, key: str) -> Variant | None:
        return next((v for v in self.variants or [] if v.key == key), None)


class LifespanTable(_Model):
    basis: str
    rows: list[LifespanRow]
    verified: bool
    verification: Verification

    @model_validator(mode="after")
    def _unique_ids(self) -> "LifespanTable":
        ids = [r.id for r in self.rows]
        if len(ids) != len(set(ids)):
            raise ValueError("내용연수표 품목 ID가 중복됩니다.")
        return self

    def row(self, item_key: str) -> LifespanRow | None:
        return next((r for r in self.rows if r.id == item_key), None)


class UnsupportedCodes(_Model):
    set_partial: Literal["SET_PARTIAL_UNSUPPORTED"]
    attachment: Literal["ATTACHMENT_UNSUPPORTED"]
    badge: Literal["out_of_scope"]
    code_status: str
    accepted_at: str
    note: str


class SetAllocation(_Model):
    basis: str
    shares_percent: dict[str, dict[str, int]]
    hanbok_scope_text: str
    individual_price_overrides: bool
    scope_status: Literal["restore_candidate"]
    scope_note: str
    unsupported_codes: UnsupportedCodes
    verified: bool
    verification: Verification


class UnprovenFallback(_Model):
    basis: str
    laundry_fee_multiplier: int
    verified: bool
    verification: Verification


class UseDaysCandidates(_Model):
    D0: Literal["request_date - purchase_date"]
    D1: Literal["request_date - purchase_date + 1"]


class UseDaysParam(_Model):
    candidates: UseDaysCandidates
    selected: Literal["D0"]
    alternative: Literal["D1"]
    in_source: Literal[False]
    basis: str


class RoundingParam(_Model):
    amount: Literal["floor_won"]
    alternative: Literal["half_up_won"]
    in_source: Literal[False]
    basis: str


class SetPartialParam(_Model):
    selected: Literal["allocate"]
    alternative: Literal["whole_set"]
    scope_status: Literal["restore_candidate"]
    in_source: Literal[False]
    basis: str


class SimilarItemParam(_Model):
    auto: Literal[False]
    unlisted_item_result: Literal["out_of_scope"]
    unlisted_item_code: Literal["ITEM_NOT_IN_TABLE"]
    unlisted_item_code_status: str
    in_source: bool
    basis: str


class DecisionSensitivityParam(_Model):
    applies_to: list[Literal["use_days", "rounding", "set_partial_damage"]]
    applies_to_note: str
    rule: str
    code_status: str
    limit: str
    in_source: Literal[False]
    basis: str


class LaundryParams(_Model):
    use_days: UseDaysParam
    rounding: RoundingParam
    set_partial_damage: SetPartialParam
    similar_item_application: SimilarItemParam
    decision_sensitivity: DecisionSensitivityParam
    deductions_computed: Literal[False]
    deductions_basis: str


class LaundryClause(_Model):
    id: str
    label: str
    text: str
    table_ref: str | None = None


class LaundryRelatedSource(_Model):
    name: str
    url: str
    retrieved_at: str
    law_number: str | None = None
    terms_number: str | None = None
    effective_date: str | None = None
    enacted: str | None = None
    verified_paths: int | None = None
    usage: Literal["notice_only"] | None = None


class LaundryRelatedClause(_Model):
    id: str
    label: str
    source: LaundryRelatedSource
    text: str


class LaundryRule(_Model):
    id: Literal["laundry_damage"]
    title: str
    status: str
    source: LaundrySource
    verified: bool
    ratio_table: RatioTable
    lifespan_table: LifespanTable
    set_allocation: SetAllocation
    unproven_fallback: UnprovenFallback
    params: LaundryParams
    notes: list[str]
    clauses: list[LaundryClause]
    related_clauses: list[LaundryRelatedClause]

    @property
    def clause_ids(self) -> set[str]:
        """인용 가능한 조항 ID 전체 (clauses + related_clauses)."""
        return {c.id for c in self.clauses} | {c.id for c in self.related_clauses}


@cache
def load_laundry_rule() -> LaundryRule:
    """backend/data/rules/laundry_damage.json을 읽어 검증한 LaundryRule (불변 모델이라 캐시한다)."""
    path = RULES_DIR / f"{RULE_ID}.json"
    data = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    return LaundryRule.model_validate(data)
