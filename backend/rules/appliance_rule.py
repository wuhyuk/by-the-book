"""가전 규칙 JSON 로더 (MVP_SPEC 13절 P2, backend/data/rules/appliance_warranty.json).

세탁 로더(rules/laundry_rule.py)와 같은 방식: json.loads(parse_float=Decimal) + Pydantic v2 strict.
이 파일은 사전 조사 초안 블록(3)·4)의 가산 후보, 수리 횟수 등)을 함께 담고 있어, 엔진이 쓰는 키만 모델로 검증하고
나머지 키는 무시한다 (extra="ignore"). 엔진이 전제로 삼는 결정 문자열은 Literal로 고정해 예상 밖 값이면 로드 시점에 오류를 낸다.
"""

import json
from decimal import Decimal
from functools import cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from rules.loader import RULES_DIR, Verification

RULE_ID = "appliance_warranty"


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class ApplianceSource(_Model):
    name: str
    notice_number: str
    url: str
    effective_date: str
    last_amended: str
    retrieved_at: str
    annex: str


class ItemRow(_Model):
    id: str
    annex3_label: str
    members: list[str] | None
    warranty_months: int
    parts_years: int


class Items(_Model):
    rows: list[ItemRow]
    verified: bool
    verification: Verification

    def row(self, row_id: str) -> ItemRow | None:
        return next((r for r in self.rows if r.id == row_id), None)


class Block(_Model):
    verified: bool
    verification: Verification


class LifespanRule(Block):
    text: str
    years_to_months: Literal[12]


class UsedMonths(_Model):
    start: Literal["purchase_or_delivery_date"]
    end: Literal["received_date"]
    count: Literal["same_day_or_month_end"]
    partial_month: Literal["ceil"]
    partial_month_alternative: Literal["floor"]
    in_source: Literal[False]


class Rounding(_Model):
    amount: Literal["floor_won"]
    alternative: Literal["half_up_won"]
    in_source: Literal[False]


class CapDecision(_Model):
    selected: Literal["purchase_price"]
    alternative: Literal["none"]
    in_source: Literal[False]


class NoPartsAddOn(_Model):
    text: str
    rule: Literal["residual_plus_10pct_of_price"]
    cap_decision: CapDecision


class AddOn(_Model):
    no_parts_after_warranty: NoPartsAddOn
    add_on_percent: int


class Depreciation(Block):
    method: Literal["straight_line"]
    monthly: Literal[True]
    depreciation_text: str
    residual_text: str
    add_on: AddOn
    used_months: UsedMonths
    rounding: Rounding


class SupportedItem(_Model):
    key: str
    label: str
    row: str
    member: str


class P2Params(_Model):
    supported_items: list[SupportedItem]


class Params(_Model):
    p2: P2Params


class ApplianceClause(_Model):
    id: str
    label: str
    text: str


class RelatedSource(_Model):
    name: str
    url: str
    retrieved_at: str


class RelatedClause(_Model):
    id: str
    label: str
    source: RelatedSource
    text: str


class ApplianceRule(_Model):
    id: Literal["appliance_warranty"]
    source: ApplianceSource
    verified: bool
    items: Items
    resolution_table: Block
    lifespan_rule: LifespanRule
    depreciation: Depreciation
    params: Params
    clauses: list[ApplianceClause]
    related_clauses: list[RelatedClause]

    @model_validator(mode="after")
    def _supported_rows(self) -> "ApplianceRule":
        """지원 품목은 별표 Ⅲ 행의 품목 칸(annex3_label, 원문 그대로)에 그 이름이 있어야 한다."""
        keys = [s.key for s in self.params.p2.supported_items]
        if len(keys) != len(set(keys)):
            raise ValueError("지원 품목 키가 중복됨")
        for s in self.params.p2.supported_items:
            row = self.items.row(s.row)
            if row is None or s.member not in row.annex3_label:
                raise ValueError(f"지원 품목 {s.key}의 별표 Ⅲ 행이 맞지 않음")
        return self

    @property
    def clause_ids(self) -> set[str]:
        return {c.id for c in self.clauses} | {c.id for c in self.related_clauses}

    def supported(self, key: str) -> SupportedItem | None:
        return next((s for s in self.params.p2.supported_items if s.key == key), None)


@cache
def load_appliance_rule() -> ApplianceRule:
    """backend/data/rules/appliance_warranty.json을 읽어 검증한 ApplianceRule (불변 모델이라 캐시한다)."""
    path = RULES_DIR / f"{RULE_ID}.json"
    data = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    return ApplianceRule.model_validate(data)
