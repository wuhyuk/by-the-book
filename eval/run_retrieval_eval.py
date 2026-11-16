"""조항 검색 평가 (MVP_SPEC 15.4, 2026-11-16). 표준 라이브러리만 쓴다 (새 의존성 없음).

사용 (저장소 루트에서):
    python eval/run_retrieval_eval.py
    python eval/run_retrieval_eval.py --set docs/sources/rag_eval_set.md --misses

docs/sources/rag_eval_set.md의 표(ID | 업종 | 문장 | 정답 조항 ID | 상태)를 읽어
BM25 검색(backend/rag/search.py)과 기준선(업종 필터만 쓰고 조항 앞쪽 k개)의 hit@1, hit@3, hit@5를
업종별·전체로 출력한다. 실제 흐름은 후보 5개를 LLM에 넘기므로(MVP_SPEC 15.2, k = 5) hit@5가 핵심
수치다 (2026-11-16 추가). 검색 알고리즘·토큰화·파라미터는 이 스크립트에서 바꾸지 않는다.
검색 입력은 실제 흐름과 같게 마스킹한 문장이다 (backend/llm/masking.py, 표준 라이브러리만 씀).
정답 ID가 '승인 대기'면 결과는 승인 전 임시값으로 표시한다. pytest 임계값으로 쓰지 않는다.
LLM을 부르지 않는다.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from llm.masking import mask_pii
from rag.search import baseline, domain_clauses, search

DEFAULT_SET = ROOT / "docs" / "sources" / "rag_eval_set.md"
DOMAINS = ("gym", "laundry", "appliance")
KS = (1, 3, 5)


@dataclass(frozen=True)
class Row:
    id: str
    domain: str
    text: str
    gold: tuple[str, ...]
    state: str


def parse(path: Path) -> list[Row]:
    rows: list[Row] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[1] not in DOMAINS:
            continue
        gold = tuple(g.strip() for g in cells[3].split(",") if g.strip())
        rows.append(Row(cells[0], cells[1], cells[2], gold, cells[4]))
    return rows


def check(rows: list[Row]) -> None:
    """정답 ID가 그 업종 조항에 있는지 (오타 방지)."""
    for r in rows:
        ids = {c.clause_id for c in domain_clauses(r.domain)}
        bad = [g for g in r.gold if g not in ids]
        if bad:
            raise SystemExit(f"{r.id}: 업종 {r.domain}에 없는 정답 ID {bad}")


def hit(ranked: list[str], gold: tuple[str, ...], k: int) -> bool:
    return any(g in ranked[:k] for g in gold)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="조항 검색 평가")
    parser.add_argument("--set", type=Path, default=DEFAULT_SET)
    parser.add_argument(
        "--misses", action="store_true", help="hit@5·hit@3을 놓친 문장 출력"
    )
    args = parser.parse_args()

    rows = parse(args.set)
    check(rows)
    pending = sum(r.state != "승인" for r in rows)
    kmax = max(KS)
    bm: dict[str, list[str]] = {
        r.id: [c.clause_id for c in search(mask_pii(r.text), r.domain, kmax)]
        for r in rows
    }
    base: dict[str, list[str]] = {r.id: baseline(r.domain, kmax) for r in rows}

    print(f"평가 문장 {len(rows)}건 (정답 승인 대기 {pending}건)")
    if pending:
        print("※ 정답 ID 승인 전 임시값입니다.")
    names = [f"{label} hit@{k}" for label in ("BM25", "기준선") for k in KS]
    print("\n| 업종 | 문장 수 | " + " | ".join(names) + " |")
    print("|---|---|" + "---|" * len(names))
    for name in (*DOMAINS, "전체"):
        sel = [r for r in rows if name == "전체" or r.domain == name]
        if not sel:
            continue
        cells = []
        for table in (bm, base):
            for k in KS:
                n = sum(hit(table[r.id], r.gold, k) for r in sel)
                cells.append(f"{n}/{len(sel)} ({n / len(sel):.0%})")
        print(f"| {name} | {len(sel)} | " + " | ".join(cells) + " |")

    if args.misses:
        for k in (5, 3):
            print(f"\nBM25 hit@{k}을 놓친 문장:")
            missed = [r for r in rows if not hit(bm[r.id], r.gold, k)]
            for r in missed:
                print(f"- {r.id} 정답 {list(r.gold)} / 상위 {kmax} {bm[r.id]}")
            if not missed:
                print("- 없음")


if __name__ == "__main__":
    main()
