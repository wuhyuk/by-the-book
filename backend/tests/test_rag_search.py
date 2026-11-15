"""조항 검색(rag)과 /api/analyze 연결 테스트 (MVP_SPEC 15절, 2026-11-16).

검색 성질은 합성 미니 코퍼스로만 확인한다 (평가 문장의 정답 ID는 승인 전이라 기대값으로 쓰지 않는다).
확인: 토큰 규칙, 결정성, 업종 필터, k 상한, 반환 ID가 코퍼스에 있음, 동점은 ID 오름차순,
후보 밖·중복 ID 폐기, 검색 입력이 마스킹된 문장, 꺼짐 상태에서 프롬프트·스키마·응답 불변, 호출 1회.
"""

import json
import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_llm_extraction import raw

import api.analyze as analyze_module
from api.analyze import get_client_provider
from api.settings import AppSettings, get_app_settings
from llm import extraction, laundry_extraction
from llm.clause_selection import (
    CLAUSE_IDS_KEY,
    select_valid,
    split_clause_ids,
    with_clause_ids,
)
from llm.client import LLMError, Turn
from main import app
from rag import search as rag_search
from rag.bm25 import BM25Index, normalize, tokenize
from rag.search import Candidate, baseline, corpus, domain_clauses, excerpt, search
from rules.sources import clause_index

client = TestClient(app)

# ---- 합성 미니 코퍼스 (규칙 JSON과 무관한 가상 문서) ----
MINI = [
    ("d03", "사과 바나나 사과 과일"),
    ("d01", "사과 과일 가게"),
    ("d02", "바나나 우유"),
    ("d04", "자동차 정비 부품"),
    ("d05", "부품 보유 기간"),
]


def test_tokenize_rules() -> None:
    assert normalize("Ａ①, 헬스장!") == "a1  헬스장 "
    assert tokenize("헬스장") == ["헬스", "스장", "헬스장"]
    assert tokenize("가 나") == []  # 한 글자 구간은 2-gram 없음, 한 글자 낱말 제외
    assert tokenize("ab 10% x") == ["ab", "10"]


def test_bm25_deterministic_and_tie_break() -> None:
    idx = BM25Index(MINI)
    first = idx.score("사과 과일")
    for _ in range(5):
        assert BM25Index(list(reversed(MINI))).score("사과 과일") == first
    twin = BM25Index([("b", "같은 문서"), ("a", "같은 문서")])
    hits = twin.score("같은")
    assert [h.doc_id for h in hits] == ["a", "b"]  # 점수 같으면 ID 오름차순
    assert hits[0].score == hits[1].score


def test_bm25_only_positive_scores_and_ids_in_corpus() -> None:
    idx = BM25Index(MINI)
    ids = {d for d, _ in MINI}
    rng = random.Random(1116)
    words = ["사과", "바나나", "부품", "기간", "없는말", "우유", "정비"]
    for _ in range(200):
        q = " ".join(rng.sample(words, rng.randint(1, 4)))
        hits = idx.score(q)
        assert all(h.score > 0 and h.doc_id in ids for h in hits)
        assert hits == sorted(hits, key=lambda h: (-h.score, h.doc_id))
    assert idx.score("전혀없는낱말") == []


def test_bm25_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError):
        BM25Index([("a", "x"), ("a", "y")])


@pytest.fixture
def mini_corpus(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """검색 모듈의 코퍼스를 합성 문서로 바꾼다 (업종 두 개, 공유 문서 하나)."""
    docs = (
        rag_search.Clause("g1", "가 조항", "헬스장 위약금 환급", ("gym",)),
        rag_search.Clause("g2", "나 조항", "헬스장 보증금", ("gym",)),
        rag_search.Clause("s1", "공유 조항", "위약금 기준 권고", ("gym", "laundry")),
        rag_search.Clause("l1", "다 조항", "세탁물 분실 인수증", ("laundry",)),
        rag_search.Clause("l2", "라 조항", "세탁물 손상 위약금", ("laundry",)),
    )
    rag_search.index.cache_clear()
    monkeypatch.setattr(rag_search, "corpus", lambda: docs)
    yield
    rag_search.index.cache_clear()


def test_search_domain_filter_and_k(mini_corpus: None) -> None:
    gym = search("위약금", "gym", k=5)
    assert {c.clause_id for c in gym} <= {"g1", "g2", "s1"}
    assert {c.clause_id for c in gym} == {"g1", "s1"}
    laundry = search("위약금", "laundry", k=5)
    assert {c.clause_id for c in laundry} == {"s1", "l2"}
    assert len(search("위약금", None, k=1)) == 1
    assert [c.rank for c in search("위약금", None, k=5)] == [1, 2, 3]
    for bad in (0, 21):
        with pytest.raises(ValueError):
            search("위약금", "gym", k=bad)
    with pytest.raises(ValueError):
        search("위약금", "unknown_domain")


def test_baseline_is_file_order(mini_corpus: None) -> None:
    assert baseline("gym", 2) == ["g1", "g2"]
    assert baseline("laundry", 5) == ["s1", "l1", "l2"]


def test_real_corpus_shape() -> None:
    """실제 규칙 JSON: 60개 ID, 조항 조회 색인과 같은 ID, 업종별 개수 (평가가 아니라 적재 확인)."""
    ids = {c.clause_id for c in corpus()}
    assert len(ids) == 60 and ids == set(clause_index())
    assert {d: len(domain_clauses(d)) for d in ("gym", "laundry", "appliance")} == {
        "gym": 15,
        "laundry": 16,
        "appliance": 31,
    }
    for c in search("수리 부품 환급 세탁 헬스장 위약금", None, k=20):
        assert c.clause_id in ids
        assert c.excerpt == excerpt(
            next(x.text for x in corpus() if x.clause_id == c.clause_id)
        )


def test_excerpt_cuts_stored_text() -> None:
    assert excerpt("가\n나") == "가 나"
    long = "가" * 200
    assert excerpt(long) == "가" * 120 + "…"


# ---- clause_ids 검증 ----

CANDS = [
    Candidate("art5_1", "제5조 ①", "본문", 3.0, 1),
    Candidate("art4_1", "제4조 ①", "본문", 2.0, 2),
]


def test_select_valid_drops_unknown_and_duplicates() -> None:
    assert select_valid(["art4_1", "x", "art4_1", "art5_1"], CANDS) == [
        "art4_1",
        "art5_1",
    ]
    assert select_valid(["x", "y"], CANDS) == []


def test_split_clause_ids_tolerates_bad_shapes() -> None:
    body, ids = split_clause_ids(json.dumps({"a": 1, CLAUSE_IDS_KEY: ["art5_1", 3]}))
    assert json.loads(body) == {"a": 1} and ids == ["art5_1"]
    assert split_clause_ids(json.dumps({"a": 1, CLAUSE_IDS_KEY: "art5_1"}))[1] == []
    assert split_clause_ids(json.dumps({"a": 1}))[1] == []
    with pytest.raises(LLMError):
        split_clause_ids("not json")


def test_with_clause_ids_does_not_touch_original() -> None:
    schema = extraction.response_schema()
    before = json.dumps(schema, sort_keys=True)
    out = with_clause_ids(schema, CANDS)
    assert json.dumps(schema, sort_keys=True) == before
    assert out["properties"][CLAUSE_IDS_KEY]["items"]["enum"] == ["art5_1", "art4_1"]
    assert CLAUSE_IDS_KEY in out["required"]


# ---- /api/analyze 연결 ----

PHONE = "010-2468-1357"
TEXT = f"헬스장 1년권 120만원 결제했는데 위약금을 너무 많이 떼요. 연락처 {PHONE}"


@dataclass
class SpyClient:
    extra: dict[str, Any] = field(default_factory=dict)
    model: str = "fake-model"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        self.calls.append(
            {"system": system, "schema": response_schema, "text": turns[-1].text}
        )
        if "service_type" in response_schema["properties"]["fields"]["properties"]:
            names = laundry_extraction.FIELD_NAMES  # 세탁 스키마: 값 없는 응답
            out = {
                "judgment_requested": False,
                "judgment_evidence": None,
                "fields": dict.fromkeys(names),
                "evidence": dict.fromkeys(names),
            }
        else:
            out = raw({"industry": ("fitness", "헬스장 1년권")})
        return json.dumps({**out, **self.extra})


@pytest.fixture
def setup() -> Iterator[Callable[..., SpyClient]]:
    def _setup(extra: dict[str, Any] | None = None, *names: str) -> SpyClient:
        spy = SpyClient(extra or {})
        app.dependency_overrides[get_client_provider] = lambda: lambda: spy
        app.dependency_overrides[get_app_settings] = lambda: AppSettings(
            enabled_features=names
        )
        return spy

    yield _setup
    app.dependency_overrides.clear()


def analyze(text: str = TEXT, item: str = "gym") -> Any:
    q = "" if item == "gym" else f"?item={item}"
    return client.post(f"/api/analyze{q}", json={"text": text})


@pytest.mark.parametrize("item", ["gym", "laundry"])
def test_rag_off_prompt_schema_and_response_unchanged(
    setup: Callable[..., SpyClient], item: str
) -> None:
    spy = setup()
    r = analyze(item=item)
    assert r.status_code == 200
    assert "clauses" not in r.json()
    mod = extraction if item == "gym" else laundry_extraction
    assert spy.calls[0]["system"] == mod.system_prompt()
    assert spy.calls[0]["schema"] == mod.response_schema()
    assert len(spy.calls) == 1


def test_rag_on_one_call_candidates_in_prompt_and_filtered_selection(
    setup: Callable[..., SpyClient],
) -> None:
    spy = setup({CLAUSE_IDS_KEY: ["made_up", "annex_penalty", "annex_penalty"]}, "rag")
    r = analyze()
    assert r.status_code == 200
    data = r.json()
    assert len(spy.calls) == 1  # 호출 횟수는 늘지 않는다
    call = spy.calls[0]
    cands = data["clauses"]["candidates"]
    assert 1 <= len(cands) <= 5
    for c in cands:
        assert f"- {c['clause_id']}: {c['title']}" in call["system"]
    enum = call["schema"]["properties"][CLAUSE_IDS_KEY]["items"]["enum"]
    assert enum == [c["clause_id"] for c in cands]
    selected = [s["clause_id"] for s in data["clauses"]["selected"]]
    assert selected == (["annex_penalty"] if "annex_penalty" in enum else [])
    assert "selected_clause_ids" not in data["extraction"]
    assert data["extraction"]["fields"] == {
        "industry": "fitness"
    }  # 기존 추출 규칙 그대로
    for c in cands:
        stored = clause_index()[c["clause_id"]]
        assert c["source_name"] == stored.source.name
        assert c["retrieved_at"] == stored.retrieved_at
        assert c["verified"] == stored.verified
        assert c["user_checked"] == stored.user_checked


def test_rag_on_all_ids_dropped_gives_empty_selection(
    setup: Callable[..., SpyClient],
) -> None:
    setup({CLAUSE_IDS_KEY: ["nope", "art99"]}, "rag")
    assert analyze().json()["clauses"]["selected"] == []


def test_rag_search_gets_masked_text(
    setup: Callable[..., SpyClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, str | None, int]] = []
    real = analyze_module.search

    def spy_search(text: str, domain: str | None, k: int = 5) -> list[Candidate]:
        seen.append((text, domain, k))
        return real(text, domain, k)

    monkeypatch.setattr(analyze_module, "search", spy_search)
    setup({}, "rag")
    analyze()
    assert len(seen) == 1
    text, domain, k = seen[0]
    assert PHONE not in text and "[전화번호]" in text
    assert (domain, k) == ("gym", 5)


def test_rag_not_called_on_guardrail_or_switch_off(
    setup: Callable[..., SpyClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        analyze_module, "search", lambda *a, **k: calls.append("x") or []
    )
    setup({}, "rag")
    r = analyze("헬스장 환급 소송하면 이길 수 있나요?")
    assert r.json()["status"] == "guardrail" and "clauses" not in r.json()
    app.dependency_overrides[get_app_settings] = lambda: AppSettings(
        analyze_enabled=False, enabled_features=("rag",)
    )
    assert analyze().status_code == 503
    assert calls == []


def test_rag_on_no_candidates_uses_plain_prompt(
    setup: Callable[..., SpyClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(analyze_module, "search", lambda *a, **k: [])
    spy = setup({}, "rag")
    data = analyze().json()
    assert data["clauses"] == {"candidates": [], "selected": []}
    assert spy.calls[0]["system"] == extraction.system_prompt()
    assert spy.calls[0]["schema"] == extraction.response_schema()


def test_rag_on_laundry_searches_laundry_domain(
    setup: Callable[..., SpyClient],
) -> None:
    spy = setup({CLAUSE_IDS_KEY: []}, "rag")
    data = analyze(
        "세탁소에 맡긴 코트를 잃어버렸고 인수증을 못 받았어요", "laundry"
    ).json()
    cands = data["clauses"]["candidates"]
    laundry_ids = {c.clause_id for c in domain_clauses("laundry")}
    assert cands and {c["clause_id"] for c in cands} <= laundry_ids
    assert CLAUSE_IDS_KEY in spy.calls[0]["schema"]["properties"]
    assert data["clauses"]["selected"] == []
