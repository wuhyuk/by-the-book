"""판단 보류율 평가 (규칙 가드레일만, 2026-11-16). 표준 라이브러리만 쓴다 (새 의존성 없음).

사용 (저장소 루트에서):
    python eval/run_guardrail_eval.py
    python eval/run_guardrail_eval.py --set docs/sources/guardrail_eval_set.md

docs/sources/guardrail_eval_set.md의 표(ID | 영역 | 문장 | 기대 라벨 | 상태)를 읽어
backend/llm/guardrail.py의 detect_judgment_request를 직접 부른다. 입력은 실제 흐름
(backend/api/analyze.py)과 같게 마스킹한 문장이다 (backend/llm/masking.py).
보류 재현율(기대 라벨 '보류' 중 잡은 수), 오탐률(기대 라벨 '정상' 중 막은 수), 놓친·오탐 문장을 출력한다.
LLM·네트워크를 부르지 않는다. 문장·라벨이 '승인 대기'면 결과는 승인 전 임시값으로 표시한다.
pytest 임계값으로 쓰지 않는다.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from llm.guardrail import detect_judgment_request
from llm.masking import mask_pii

DEFAULT_SET = ROOT / "docs" / "sources" / "guardrail_eval_set.md"
LABELS = ("보류", "정상")


@dataclass(frozen=True)
class Row:
    id: str
    area: str
    text: str
    label: str
    state: str


def parse(path: Path) -> list[Row]:
    rows: list[Row] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[3] not in LABELS:
            continue
        rows.append(Row(*cells))
    return rows


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="판단 보류율 평가 (규칙 가드레일)")
    parser.add_argument("--set", type=Path, default=DEFAULT_SET)
    args = parser.parse_args()

    rows = parse(args.set)
    if len({r.id for r in rows}) != len(rows):
        raise SystemExit("중복된 ID가 있습니다")
    blocked = {r.id: detect_judgment_request(mask_pii(r.text)) for r in rows}
    judgment = [r for r in rows if r.label == "보류"]
    normal = [r for r in rows if r.label == "정상"]
    caught = [r for r in judgment if blocked[r.id]]
    missed = [r for r in judgment if not blocked[r.id]]
    false_pos = [r for r in normal if blocked[r.id]]
    pending = sum(r.state != "승인" for r in rows)

    print(
        f"평가 문장 {len(rows)}건 (보류 대상 {len(judgment)}, 정상 {len(normal)}, 승인 대기 {pending}건)"
    )
    if pending:
        print("※ 문장·기대 라벨 승인 전 임시값입니다.")

    def ratio(n: int, d: int) -> str:
        return f"{n}/{d} ({n / d:.0%})" if d else "0/0"

    print("\n| 지표 | 값 |")
    print("|---|---|")
    print(f"| 보류 재현율 (보류 대상 중 잡음) | {ratio(len(caught), len(judgment))} |")
    print(f"| 오탐률 (정상 중 막음) | {ratio(len(false_pos), len(normal))} |")

    print("\n놓친 보류 대상 문장:")
    for r in missed:
        print(f"- {r.id} {r.text}")
    if not missed:
        print("- 없음")
    print("\n오탐한 정상 문장:")
    for r in false_pos:
        print(f"- {r.id} {r.text}")
    if not false_pos:
        print("- 없음")


if __name__ == "__main__":
    main()
