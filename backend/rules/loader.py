"""규칙 JSON 로더 (MVP_SPEC 4절, 5.8).

json.loads(parse_float=Decimal)로 읽고 Pydantic v2로 검증한다.
엔진이 전제로 삼는 문자열 규칙 값은 Literal로 고정해, 예상 밖 값이면 로드 시점에 오류를 낸다.
"""

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

RULES_DIR = Path(__file__).resolve().parent.parent / "data" / "rules"
_RULE_ID = re.compile(r"[a-z][a-z0-9_]*")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class NoticeSource(_Model):
    name: str
    notice_number: str
    url: str
    effective_date: str
    last_amended: str
    retrieved_at: str


class RelatedSource(_Model):
    name: str
    url: str
    retrieved_at: str
    law_number: str | None = None
    terms_number: str | None = None
    effective_date: str | None = None
    revised: str | None = None
    enacted: str | None = None


class Verification(_Model):
    method: str
    user_checked: bool
    checked_at: str


class PenaltyRule(_Model):
    type: Literal["ratio_of_total"]
    ratio: Decimal
    applies_as: Literal["upper_limit"]
    basis: str
    verified: bool
    verification: Verification


class Industry(_Model):
    id: str
    name: str
    scope_basis: str
    penalty_rule: PenaltyRule


class Rounding(_Model):
    used_amount: Literal["half_up_won"]
    order: Literal["multiply_then_divide_round_once"]
    penalty: Literal["floor_won"]
    in_source: bool
    basis: str


class DayCount(_Model):
    contract_days: Literal["end_date - start_date + 1"]
    elapsed_days: Literal[
        "notice_date - start_date + 1, 0 이상 contract_days 이하로 제한"
    ]
    in_source: bool
    basis: str


class RefundBasisRule(_Model):
    fitness: Literal["contract_type"]
    yoga_pilates: Literal["agreed"]
    agreed_values: list[Literal["period", "session", "unknown"]]
    in_source: bool
    basis: str


class PeriodThresholds(_Model):
    out_of_scope_below: int
    needs_review_max: int
    in_source: bool
    basis: str


class LawSource(_Model):
    name: str
    law_number: str
    url: str
    effective_date: str
    retrieved_at: str


class ContinuousTransactionCriteria(_Model):
    source: LawSource
    text: str
    requirements: list[str]
    verified: bool
    period_thresholds_days: PeriodThresholds


class Params(_Model):
    unit_options: list[str]
    unused_but_available_counts_as_supplied: Literal[True]
    deposit_excluded_from_total: Literal[True]
    deposit_refund: Literal["full_unless_agreed"]
    returned_add_on_value_added_to_refund: Literal[True]
    unit_price_method: None
    list_price_deduction_allowed: None
    rounding: Rounding
    day_count: DayCount
    refund_basis: RefundBasisRule
    continuous_transaction_criteria: ContinuousTransactionCriteria


class ScenarioA(_Model):
    name: str
    used_amount_base: Literal["total_contract_amount"]
    formula: str
    requires: list[str]
    in_source: bool
    basis: str


class ScenarioB(_Model):
    name: str
    used_amount_base: Literal["list_price"]
    formula: str
    requires: list[str]
    in_source: bool
    basis: str


class Scenarios(_Model):
    A: ScenarioA
    B: ScenarioB


class Clause(_Model):
    id: str
    label: str
    text: str


class RelatedClause(_Model):
    id: str
    label: str
    source: RelatedSource
    text: str


class GymRule(_Model):
    id: str
    title: str
    source: NoticeSource
    verified: bool
    industries: list[Industry]
    params: Params
    scenarios: Scenarios
    notes: list[str]
    clauses: list[Clause]
    related_clauses: list[RelatedClause]

    def industry(self, industry_id: str) -> Industry | None:
        """업종 ID로 업종 블록을 찾는다. 없으면 None."""
        return next((i for i in self.industries if i.id == industry_id), None)

    @property
    def clause_ids(self) -> set[str]:
        """인용 가능한 조항 ID 전체 (clauses + related_clauses)."""
        return {c.id for c in self.clauses} | {c.id for c in self.related_clauses}


def load_rule(rule_id: str) -> GymRule:
    """backend/data/rules/{rule_id}.json을 읽어 검증한 GymRule을 돌려준다."""
    if not _RULE_ID.fullmatch(rule_id):
        raise ValueError(f"규칙 ID 형식이 아닙니다: {rule_id!r}")
    path = RULES_DIR / f"{rule_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    return GymRule.model_validate(data)
