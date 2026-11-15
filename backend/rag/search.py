"""조항 검색 (기능 플래그 rag, MVP_SPEC 15.1, 2026-11-16). 표준 라이브러리만 쓴다.

- 대상: backend/data/rules/*.json의 clauses와 related_clauses (새 데이터 파일 없음). 문서 본문 = 라벨 + 원문.
- 업종(domain) 필터를 먼저 적용한다: gym → gym_refund.json, laundry → laundry_damage.json,
  appliance → appliance_warranty.json. 같은 ID가 두 파일에 있으면(소비자기본법 조문) 두 업종 모두에 든다.
  domain이 None이면 전체에서 찾는다. 업종마다 색인을 따로 만든다 (idf도 그 업종 문서로 계산).
- 색인은 처음 부를 때 한 번 만든다 (서버 시작 때 warm_index로 미리 만든다).
- 개인정보: 입력은 호출하는 쪽이 마스킹한 문장이다. 이 모듈은 입력을 저장·로그하지 않는다.
- 결과는 금액 계산에 쓰지 않는다. 조항 ID·제목·저장된 본문 앞부분·점수·순위만 돌려준다.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from rag.bm25 import BM25Index

RULES_DIR = Path(__file__).resolve().parent.parent / "data" / "rules"
DOMAIN_FILES: dict[str, str] = {
    "gym": "gym_refund",
    "laundry": "laundry_damage",
    "appliance": "appliance_warranty",
}
EXCERPT_CHARS = 120
DEFAULT_K = 5
MAX_K = 20


@dataclass(frozen=True)
class Clause:
    clause_id: str
    title: str
    text: str
    domains: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    clause_id: str
    title: str
    excerpt: str
    score: float
    rank: int


def excerpt(text: str, limit: int = EXCERPT_CHARS) -> str:
    """저장된 본문의 앞부분 (줄바꿈은 공백으로). 길면 자르고 '…'를 붙인다."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit].rstrip() + "…"


@cache
def corpus() -> tuple[Clause, ...]:
    """세 규칙 JSON의 조항 (파일 순서, 파일 안 순서). 같은 ID는 한 번만 두고 업종을 합친다."""
    found: dict[str, Clause] = {}
    for domain, rule_id in DOMAIN_FILES.items():
        raw = json.loads((RULES_DIR / f"{rule_id}.json").read_text(encoding="utf-8"))
        for entry in [*raw.get("clauses", []), *raw.get("related_clauses", [])]:
            cid = entry["id"]
            if cid in found:
                prev = found[cid]
                found[cid] = Clause(cid, prev.title, prev.text, (*prev.domains, domain))
            else:
                found[cid] = Clause(cid, entry["label"], entry["text"], (domain,))
    return tuple(found.values())


def domain_clauses(domain: str | None) -> tuple[Clause, ...]:
    """업종 필터. None이면 전체. 모르는 업종이면 ValueError."""
    if domain is not None and domain not in DOMAIN_FILES:
        raise ValueError("모르는 업종입니다.")
    return tuple(c for c in corpus() if domain is None or domain in c.domains)


@cache
def index(domain: str | None) -> BM25Index:
    return BM25Index(
        [(c.clause_id, f"{c.title}\n{c.text}") for c in domain_clauses(domain)]
    )


def warm_index() -> None:
    """서버 시작 때 색인을 미리 만든다."""
    for domain in (*DOMAIN_FILES, None):
        index(domain)


def search(masked_text: str, domain: str | None, k: int = DEFAULT_K) -> list[Candidate]:
    """마스킹된 문장 → 상위 k개 후보 (점수 > 0만, 점수 내림차순·ID 오름차순, 1 ≤ k ≤ 20)."""
    if not 1 <= k <= MAX_K:
        raise ValueError("k는 1 이상 20 이하입니다.")
    by_id = {c.clause_id: c for c in domain_clauses(domain)}
    hits = index(domain).score(masked_text)[:k]
    return [
        Candidate(
            clause_id=h.doc_id,
            title=by_id[h.doc_id].title,
            excerpt=excerpt(by_id[h.doc_id].text),
            score=round(h.score, 6),
            rank=i + 1,
        )
        for i, h in enumerate(hits)
    ]


def baseline(domain: str | None, k: int = DEFAULT_K) -> list[str]:
    """평가용 기준선: 업종 필터만 쓰고 조항 앞쪽 k개 (파일 순서)."""
    return [c.clause_id for c in domain_clauses(domain)[:k]]
