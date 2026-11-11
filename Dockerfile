# 기준대로 배포 이미지 (docs/DEPLOY.md). 컨테이너 한 개: FastAPI가 API와 화면(frontend/dist)을 함께 서빙한다.
# 1단계: 화면 빌드 (Node) → 2단계: Python 런타임 (비루트 실행, PORT 환경변수).
# 비밀값은 이미지에 넣지 않는다. 키는 배포 호스트 대시보드의 환경변수로만 넣는다 (.dockerignore).

FROM node:22.14.0-bookworm-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12.10-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000
WORKDIR /app/backend
COPY backend/requirements.lock ./
RUN pip install --no-deps -r requirements.lock && pip check
COPY backend/main.py ./
COPY backend/api ./api
COPY backend/guide ./guide
COPY backend/llm ./llm
COPY backend/rag ./rag
COPY backend/rules ./rules
COPY backend/data ./data
COPY --from=web /app/frontend/dist /app/frontend/dist
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8000'), timeout=4)"
# 접근 로그는 끈다 (요청 경로·IP를 남기지 않음). 오류는 api/errors.py가 종류 이름만 남긴다.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
