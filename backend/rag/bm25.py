"""순수 Python BM25 (MVP_SPEC 15.1, 2026-11-16). 표준 라이브러리만 쓴다.

토큰 (tokenize):
1. 정규화: NFKC → 소문자 → 구두점·기호를 공백으로 (한글·영문·숫자·밑줄만 남김).
2. 한글이 이어진 구간마다 글자 2-gram (구간이 한 글자면 만들지 않는다).
3. 공백으로 나눈 낱말 중 길이 2 이상 (한글·영문·숫자 모두).
점수: BM25 (k1=1.2, b=0.75), idf = ln(1 + (N − df + 0.5) / (df + 0.5)) (음수가 되지 않는 형태).
정렬: 점수 내림차순, 같으면 문서 ID 오름차순 (결정적).
"""

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

K1 = 1.2
B = 0.75

_NON_WORD = re.compile(r"[^0-9a-z_가-힣ㄱ-ㆎ\s]+")
_HANGUL_RUN = re.compile(r"[가-힣]+")


def normalize(text: str) -> str:
    """NFKC, 소문자, 구두점·기호 제거(공백으로)."""
    return _NON_WORD.sub(" ", unicodedata.normalize("NFKC", text).lower())


def tokenize(text: str) -> list[str]:
    """한글 구간 글자 2-gram + 길이 2 이상 낱말. 같은 토큰이 여러 번 나오면 그만큼 센다."""
    norm = normalize(text)
    tokens: list[str] = []
    for run in _HANGUL_RUN.findall(norm):
        tokens += [run[i : i + 2] for i in range(len(run) - 1)]
    tokens += [w for w in norm.split() if len(w) >= 2]
    return tokens


@dataclass(frozen=True)
class Hit:
    doc_id: str
    score: float


class BM25Index:
    """문서 (ID, 본문) 목록으로 한 번 만든다. 만든 뒤에는 바꾸지 않는다."""

    def __init__(self, docs: Sequence[tuple[str, str]]) -> None:
        ids = [d for d, _ in docs]
        if len(set(ids)) != len(ids):
            raise ValueError("문서 ID가 겹칩니다.")
        self.doc_ids: tuple[str, ...] = tuple(ids)
        self._tf: list[Counter[str]] = [Counter(tokenize(t)) for _, t in docs]
        self._len: list[int] = [sum(tf.values()) for tf in self._tf]
        n = len(docs)
        self._avg = (sum(self._len) / n) if n else 0.0
        df: Counter[str] = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        self._idf: dict[str, float] = {
            t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()
        }

    @property
    def size(self) -> int:
        return len(self.doc_ids)

    def vocabulary_size(self) -> int:
        return len(self._idf)

    def posting_count(self) -> int:
        """(문서, 토큰) 쌍의 수 (메모리 추정용)."""
        return sum(len(tf) for tf in self._tf)

    def score(self, query: str) -> list[Hit]:
        """점수가 0보다 큰 문서만, 점수 내림차순·ID 오름차순."""
        # 정렬해 더한다: 집합 순서(해시 시드)에 따라 부동소수 합이 달라지지 않게
        q = sorted(set(tokenize(query)))
        hits: list[Hit] = []
        for i, tf in enumerate(self._tf):
            s = 0.0
            norm = K1 * (1 - B + B * self._len[i] / self._avg) if self._avg else K1
            for t in q:
                f = tf.get(t)
                if f:
                    s += self._idf[t] * f * (K1 + 1) / (f + norm)
            if s > 0:
                hits.append(Hit(self.doc_ids[i], s))
        hits.sort(key=lambda h: (-h.score, h.doc_id))
        return hits
