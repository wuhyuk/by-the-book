"""조항 조회 (GET /api/sources/{id}, MVP_SPEC 14.3, 2026-11-16).

규칙 JSON(backend/data/rules/*.json)의 clauses·related_clauses를 조항 ID로 찾는다. 순수 조회만 한다.
조항 원문·라벨·출처는 근거 카드와 같게 각 품목의 citation_cards로 만든다 (화면 카드와 같은 출처 표기).

verified·user_checked 규칙 [제안 2026-11-16]:
- table_ref가 있는 조항(표 카드): 그 표 블록의 verified와 verification.user_checked.
- verified_paths가 있는 고시 밖 원문(세탁 표준약관): verified_paths ≥ 2이면 verified (MVP_SPEC 12.7과 같은 기준).
- 그 밖의 조항: clauses·related_clauses에는 원문을 확인한 조문만 넣는다는 규칙(MVP_SPEC 4절·5.7·10절)에 따라
  verified true. 조항 단위 사용자 대조 기록이 없으므로 user_checked는 null(기록 없음)이다.
같은 ID가 여러 규칙 파일에 있으면(소비자기본법 조문 등, 본문·출처가 같음) 처음 찾은 것을 쓰고 rule_ids에 모두 적는다.
"""

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from rules.appliance_display import citation_cards as appliance_cards
from rules.appliance_rule import load_appliance_rule
from rules.gym_display import CitationCard, SourceInfo
from rules.gym_display import citation_cards as gym_cards
from rules.laundry_display import citation_cards as laundry_cards
from rules.laundry_rule import load_laundry_rule
from rules.loader import load_rule

RULES_DIR = Path(__file__).resolve().parent.parent / "data" / "rules"
RULE_FILES = ("gym_refund", "laundry_damage", "appliance_warranty")
CLAUSE_ID_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")
NOT_FOUND_TEXT = "해당 조항 ID를 찾을 수 없습니다."


class ClauseSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    text: str
    source: SourceInfo
    retrieved_at: str
    verified: bool
    user_checked: bool | None
    rule_ids: list[str]


def _raw(rule_id: str) -> dict[str, Any]:
    path = RULES_DIR / f"{rule_id}.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _card(rule_id: str, clause_id: str) -> CitationCard:
    if rule_id == "gym_refund":
        return gym_cards([clause_id], load_rule(rule_id))[0]
    if rule_id == "laundry_damage":
        return laundry_cards([clause_id], load_laundry_rule())[0]
    return appliance_cards([clause_id], load_appliance_rule())[0]


def _verification(
    raw: dict[str, Any], entry: dict[str, Any]
) -> tuple[bool, bool | None]:
    table = entry.get("table_ref")
    if table:
        block = raw[table]
        checked = (block.get("verification") or {}).get("user_checked")
        return bool(block.get("verified")), checked if isinstance(
            checked, bool
        ) else None
    paths = (entry.get("source") or {}).get("verified_paths")
    if paths is not None:
        return paths >= 2, None
    return True, None


@cache
def clause_index() -> dict[str, ClauseSource]:
    """서버 시작 뒤 처음 부를 때 한 번 만든다 (조항 수 수십 개)."""
    index: dict[str, ClauseSource] = {}
    for rule_id in RULE_FILES:
        raw = _raw(rule_id)
        for entry in [*raw.get("clauses", []), *raw.get("related_clauses", [])]:
            cid = entry["id"]
            if cid in index:
                prev = index[cid]
                index[cid] = prev.model_copy(
                    update={"rule_ids": [*prev.rule_ids, rule_id]}
                )
                continue
            card = _card(rule_id, cid)
            verified, user_checked = _verification(raw, entry)
            index[cid] = ClauseSource(
                id=cid,
                label=card.label,
                text=card.text,
                source=card.source,
                retrieved_at=card.source.retrieved_at,
                verified=verified,
                user_checked=user_checked,
                rule_ids=[rule_id],
            )
    return index


def valid_clause_id(clause_id: str) -> bool:
    return CLAUSE_ID_PATTERN.fullmatch(clause_id) is not None


def find_clause(clause_id: str) -> ClauseSource | None:
    """허용 문자(영문 소문자·숫자·밑줄, 64자 이하)가 아니거나 없는 ID는 None."""
    if not valid_clause_id(clause_id):
        return None
    return clause_index().get(clause_id)
