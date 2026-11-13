# DEPLOY — 1차 배포 (Render, Docker)

> 작성 2026-11-12 (PR-B). 일정: 11/14(토) 1차 배포 → 11/14~11/17 버그 수정만 → 11/18까지 만족도 평가 (MVP_SPEC 8.1).
> Render 무료 웹 서비스의 동작(잠듦·깨어남, 월 인스턴스 시간, 파일 시스템 초기화)은 Render 문서 [Deploy for Free](https://render.com/docs/free)로 확인했다 (2026-11-13, 4.3). 그 밖의 Render 화면 이름은 Render 문서로 다시 확인하지 않았다. 대시보드에서 이름이 다르면 같은 뜻의 항목을 쓴다. **[확인 필요]** 표시는 배포 때 Render 화면에서 확인한다.

## 1. 구성

- 컨테이너 한 개. FastAPI(uvicorn)가 API(`/api/*`)와 화면(`frontend/dist`)을 함께 서빙한다 (`backend/api/spa.py`).
  - `/api/*`가 아닌 경로는 파일이 있으면 그 파일, 없으면 `index.html` (SPA 폴백). 없는 `/api/*` 경로는 404 JSON.
- 이미지: 루트 `Dockerfile` (1단계 Node 22 화면 빌드 → 2단계 Python 3.12 런타임). 비루트 사용자 `app`(uid 10001)로 실행.
- 포트: 환경변수 `PORT` (없으면 8000). Render는 `PORT`를 넣어 준다 **[확인 필요: 값은 Render가 정함]**.
- 헬스체크: `GET /healthz` → `{"status": "ok"}` (외부 호출 없음).
- 런타임 의존성은 `backend/requirements.lock`에 버전 고정 (로컬 테스트 환경과 같은 버전).

## 2. Render 배포 단계

1. GitHub 저장소를 Render에 연결한다 (Render 대시보드 → New → Web Service → 저장소 선택).
2. 설정:
   - Runtime(Language): **Docker** **[확인 필요: 무료 인스턴스에서 Docker 런타임을 쓸 수 있는지는 확인하지 못했다. 서비스 생성 화면에서 Docker와 Free를 함께 고를 수 있는지 확인한다]**
   - Branch: `main`
   - Dockerfile 경로: `./Dockerfile`, Docker 빌드 컨텍스트: 저장소 루트 (`.`)
   - Instance type: **Free**
   - Health Check Path: **`/healthz`** (Advanced 또는 Settings의 Health Checks 항목)
3. 환경변수를 3절 표대로 넣는다 (대시보드 Environment 탭). **키는 대시보드에만 입력한다.** 저장소·이미지·채팅·이슈에 붙이지 않는다.
4. Create Web Service → 빌드 로그에서 `npm run build`와 `pip check` 통과, 마지막에 `Uvicorn running on http://0.0.0.0:…` 확인.
5. 배포 주소로 확인 스크립트를 돌린다 (5절).

## 3. 환경변수

| 이름 | 필수 | 기본값 | 값 예·설명 |
|---|---|---|---|
| `LLM_PROVIDER` | 문장 분석을 쓰면 필수 | (없음) | `gemini` |
| `LLM_API_KEY` | 문장 분석을 쓰면 필수 | (없음) | Gemini API 키. **대시보드에만 입력**. 로그·응답·예외 메시지에 나오지 않게 코드가 막는다 |
| `LLM_MODEL` | 문장 분석을 쓰면 필수 | (없음) | `gemini-3.1-flash-lite` (MVP_SPEC 9절 2026-11-08) |
| `LLM_FALLBACK_MODEL` | 선택 | 비움 | `gemini-3.5-flash-lite`. 기본 모델이 재시도 후에도 429일 때 1회 |
| `LLM_TEMPERATURE` | 선택 | `0` | 줄이 없으면 0. 값을 비우면 temperature를 보내지 않음 |
| `LLM_MAX_RPM` | 선택 | `12` | 모델별 분당 호출 상한 (무료 한도 RPM 15보다 낮게) |
| `ANALYZE_ENABLED` | 선택 | `true` | 문장 분석 스위치. 아래 파싱 규칙 |
| `DAILY_ANALYZE_LIMIT` | 선택 | `450` | 하루(한국시간) Gemini 호출 상한. 0 이상의 정수. 아니면 기본값 |
| `SURVEY_URL` | 선택 | 비움 | 만족도 설문 주소 (`https://…`). 비우면 화면에 설문 버튼이 없다. http(s)가 아니면 무시 |

- `ANALYZE_ENABLED` 파싱 (대소문자 무시, 앞뒤 공백 무시): `true`·`1`·`yes`·`on` → 켬, `false`·`0`·`no`·`off` → 끔, **빈 값 → 켬**, **그 밖의 값 → 끔** (오타는 안전하게 끈다. 로그에 설정 이름만 경고).
- LLM 설정 세 개(`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`) 없이 배포하면 `ANALYZE_ENABLED=false`로 둔다. 켜 둔 채 키가 없으면 화면에 문장 입력창이 보이지만 분석 요청은 503("지금은 문장 분석을 쓸 수 없습니다…")으로 끝난다. 폼 계산은 영향 없다.
- 값을 바꾸면 Render가 서비스를 다시 시작한다 **[확인 필요]**. 설정은 프로세스 시작 때 한 번 읽는다.

## 4. 운영 메모

### 4.1 긴급히 문장 분석 끄기

키 유출 의심, 한도 초과, 이상한 응답 등이 있으면:

1. Render 대시보드 → Environment → `ANALYZE_ENABLED`를 `false`로 저장 (재시작됨).
2. 확인: `GET /api/config` → `"analyze_enabled": false`. 화면은 문장 입력창 대신 폼 안내를 보여 준다.
3. 끈 상태에서도 승패·법적 효력 질문은 외부 호출 없이 ❔로 답하고, 폼 계산·문안(`/api/calculate`, `/api/guide`)은 그대로 동작한다.
4. 키 유출이 의심되면 Google AI Studio에서 키를 폐기하고 새 키를 대시보드에만 넣는다.

### 4.2 하루 호출 카운터

- Gemini로 실제로 보낸 호출만 센다 (재시도·예비 모델 호출도 각각 1회). 규칙 가드레일에 걸린 질문은 세지 않는다.
- 상한에 도달하면 분석은 429 `ANALYZE_DAILY_LIMIT`("오늘 쓸 수 있는 문장 분석 횟수를 모두 사용했습니다. 아래 입력 폼은 계속 사용할 수 있고, 한국시간 자정 이후 다시 분석할 수 있습니다.")를 돌려주고, `/api/config`의 `analyze_enabled`는 `false`가 된다.
- **카운터는 프로세스 메모리에만 있다. 서버가 다시 시작하면(배포, 환경변수 변경, 무료 등급 잠듦 후 깨어남) 0으로 초기화된다.** 프로세스가 여럿이면 따로 센다.
- Render 무료 서비스는 15분 동안 요청이 없으면 잠들고(4.3), 잠들면 카운터가 0이 된다. 그래서 **이 호스트에서 하루 상한은 보조 장치일 뿐이다.** 하루에 여러 번 잠들고 깨어나면 실제 호출 수가 `DAILY_ANALYZE_LIMIT`을 넘을 수 있다. 마지막 방어선은 Gemini 쪽 무료 한도(RPD)와 그 429 처리(재시도 1회 → 예비 모델 1회 → "잠시 후 다시 시도하거나 폼에 직접 입력" 안내)다.

### 4.3 무료 등급이 잠들 때

출처: Render 문서 [Deploy for Free](https://render.com/docs/free) (2026-11-13 확인).

- 무료 웹 서비스는 **15분 동안 요청이 없으면 잠들고**, 다음 요청이 오면 다시 켜진다. **깨어나는 데 약 1분** 걸려 그동안 첫 화면이 늦게 뜬다. 설문 참여자에게 "첫 화면이 1분쯤 늦게 뜰 수 있다"고 미리 알린다.
- 무료 인스턴스 시간은 **월 750시간**이다. 서비스가 깨어 있는 동안만 쓴다.
- 파일 시스템은 **재시작·재배포·잠듦 때 초기화된다.** 이 서비스는 파일에 아무것도 저장하지 않는다 (7절). 프로세스 메모리의 하루 호출 카운터도 이때 0이 된다 (4.2).
- 평가 직전에 배포 주소를 한 번 열어 깨워 둔다.
- `scripts/smoke_deploy.py`는 요청마다 60초까지 기다린다.

### 4.4 로그

- 입력 문장, 폼 입력값, LLM 응답은 로그에 남기지 않는다 (CLAUDE.md 절대 규칙 6). 실패는 종류 이름만 남는다 (예: `LLM 호출 실패: rate_limited`, `LLM 설정 없음`, `처리하지 못한 오류: RuntimeError`).
- 422 응답은 필드 위치·오류 종류만 돌려주고 입력값을 돌려주지 않는다. 500은 고정 문구만 돌려준다.
- uvicorn 접근 로그는 끄고 실행한다 (`--no-access-log`, 요청 경로·IP를 남기지 않음). Render 자체의 요청 로그는 Render가 따로 남길 수 있다 **[확인 필요]**. 요청 본문은 POST 본문으로만 보내므로 경로에는 입력이 없다.

## 5. 배포 확인

```bash
python scripts/smoke_deploy.py https://<배포 주소>
```

- 확인 항목: `/healthz`, `/api/config`, 승인 케이스 계산 3건(✅ C1, ⚠️ N2, 🔍 P1)의 배지·환급액, 같은 3건의 `/api/guide` 문안(승인 금액·고지 한 줄·인용).
- `--analyze`를 붙이면 문장 하나를 `/api/analyze`로 보낸다 (**Gemini 호출 1건**, 사용자가 직접 실행). 200이면 추출 성공, 아니면 안내 코드(`ANALYZE_DISABLED`, `ANALYZE_DAILY_LIMIT`, `rate_limited`)를 출력한다. 키가 없으면 `not_configured`로 실패한다.
- 표준 라이브러리만 쓰므로 저장소의 `backend/.venv` 없이도 Python 3.12로 돌릴 수 있다.
- 시작할 때 출력 인코딩을 UTF-8(`errors="replace"`)로 맞추므로 Windows 콘솔(cp949)에서도 배지 기호(✅·⚠️) 때문에 멈추지 않는다.

## 6. 로컬에서 이미지 확인 (선택)

```bash
docker build -t by-the-book:local .
docker run --rm -e PORT=8080 -e ANALYZE_ENABLED=false -p 18080:8080 by-the-book:local
python scripts/smoke_deploy.py http://127.0.0.1:18080
```

### 6.1 이미지에 `.env`가 없는지 확인

`.dockerignore`가 `**/.env`, `**/.env.*`를 빼고, `Dockerfile`은 `.env`를 복사하지 않는다 (`backend/tests/test_deploy_files.py`가 두 파일을 점검). 빌드한 이미지에서 직접 확인하려면:

```bash
docker run --rm --entrypoint sh by-the-book:local -c \
  'find / -name ".env*" -not -path "/proc/*" 2>/dev/null; echo "검색 끝"'
```

"검색 끝" 앞에 아무 경로도 없으면 이미지에 `.env` 파일이 없다. 키는 컨테이너 환경변수로만 들어온다 (`docker run -e`, Render 대시보드).

```bash
docker history --no-trunc by-the-book:local | grep -i "env" 
```

이 출력에 키 값이 보이면 안 된다. 정상이면 `ENV` 줄은 이 저장소의 `PYTHONDONTWRITEBYTECODE`·`PORT` 등과 기반 이미지(python)의 `PYTHON_VERSION`·`LANG`·`PATH`·`GPG_KEY`(Python 배포 서명용 공개 키 ID, 비밀값 아님)뿐이다 (2026-11-12 로컬 빌드로 확인).

## 7. 배포하지 않는 것

- `backend/.env`, `.venv`, `node_modules`, `.git`, 테스트·평가 산출물, `docs/`, `backend/tests/` (`.dockerignore`).
- 데이터 저장 없음 (사용자 입력을 저장하지 않는다). SQLite 평가 저장은 11/18 이후.
