# CONTRIBUTING — Git 규칙

혼자 진행하는 프로젝트이지만, 6주 뒤 이력을 설명할 수 있어야 하므로 아래 규칙을 지킨다. Claude Code도 같은 규칙을 따른다.

## 브랜치

- `main`: 항상 실행·테스트가 통과하는 상태. 직접 커밋하지 않는다.
- 작업 브랜치: `main`에서 분기하고 `type/짧은-설명` 형식으로 이름 짓는다.
  - `feat/gym-refund-rule`, `fix/penalty-cap`, `docs/mvp-spec`, `test/laundry-cases`, `chore/ci`
- 브랜치 하나는 하나의 논리적 목표만 다룬다. 수명은 가급적 하루~이틀.

## 커밋 메시지 (Conventional Commits)

```text
<type>(<scope>): <제목, 50자 안팎, 명령형, 마침표 없음>
```

- 커밋 메시지는 제목 한 줄만 쓴다 (`-m` 하나, 본문 없음). 왜 바꿨는지는 PR 설명에 적는다.
- type: `feat` `fix` `docs` `test` `refactor` `chore` `data`
- scope: `api` `llm` `rag` `rules` `data` `web` `eval` `docs`
- 제목은 한국어 또는 영어, 한 저장소 안에서 섞지 않고 **한국어**로 통일한다.
- `data` 타입은 `backend/data/rules/` 변경 전용이다. **출처 이름·URL·확인 날짜**는 커밋이 아니라 PR 본문에 반드시 적는다.
- 예: `data(rules): 헬스장 위약금 상한 규칙 추가` / `test(rules): 중도 해지 환급액 케이스 5건 추가`

## Pull Request

- `main`으로 합치는 모든 변경은 PR을 거친다 (혼자여도 자기 PR). 머지는 **Squash merge**.
- PR 설명에 ① 무엇을 ② 왜 ③ 어떻게 확인했는지(실행한 테스트) ④ 남은 위험 ⑤ `data` 변경이면 출처 이름·URL·확인일을 적는다.
- 머지 전 체크: `pytest` 통과, 프론트 변경 시 `npm run build` 통과, `.env`·키 미포함.

## 커밋하면 안 되는 것

`.env`, API 키, 개인정보가 담긴 사례, `.venv/`, `node_modules/`, 벡터 DB 산출물(`chroma/`), 대용량 원문 PDF. `.gitignore`를 우선 확인한다.

## 마일스톤 태그

최종 마감(2026-11-29)에 `main`에 `v0.1.0` 태그 하나만 단다. 중간 마일스톤 태그(`m1-data` ~ `m5-rag-freeze`)는 두지 않는다 (2026-11-06 결정, 구현 순서는 `docs/MVP_SPEC.md` 8.1 수직 슬라이스 계획).

## Claude Code용 Git 규칙

1. 사용자가 요청하지 않으면 commit, push, merge, 브랜치 삭제를 하지 않는다.
2. 커밋 전 `git status`와 `git diff --staged`로 의도하지 않은 파일(`.env` 등)이 없는지 확인한다.
3. `--force`, `--no-verify`, `reset --hard`, `clean -fd`는 사용하지 않는다.
4. 한 커밋에는 한 가지 변경만 담는다. 규칙 데이터와 화면 변경을 섞지 않는다.
5. 커밋 메시지는 위 형식을 따른다. 커밋 메시지와 PR 설명에 Claude·AI 표기(Co-Authored-By, Generated with Claude Code 등)를 넣지 않는다.
