# syntax=docker/dockerfile:1
# 배포 backend 이미지. 로컬은 amd64로 기능검증, 배포는 buildx --platform linux/arm64 (4단계).
# torch는 컨테이너에 GPU 없으므로 CPU 백엔드 (dev 호스트의 cu124와 무관).
FROM python:3.13-slim

# uv (astral 공식 이미지에서 바이너리 복사)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 런타임 시스템 라이브러리 (psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 의존성 레이어 (코드 변경과 분리해 캐시)
COPY pyproject.toml uv.lock ./
# torch는 컨테이너에 GPU 없으므로 CPU. pyproject의 cu124 index를 cpu로 치환 후 lock 재생성.
# (--no-install-package/UV_TORCH_BACKEND는 transitive·lock 동기화에 막혀 cu124가 복원됨)
RUN sed -i 's/cu124/cpu/g' pyproject.toml \
 && uv lock \
 && uv sync --no-install-project --no-dev

# 임베딩 모델을 이미지에 포함 (첫 기동 시 다운로드 회피 → prod 네트워크 독립).
# 코드와 무관(모델 고정)하므로 COPY src 앞에 둬, 코드 변경 시 이 2.5GB 레이어 캐시를 유지.
ENV HF_HOME=/app/.hf_cache
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('dragonkue/snowflake-arctic-embed-l-v2.0-ko')"

# 앱 코드 — pyproject.toml/uv.lock을 덮지 않도록 명시 COPY (위 cpu 수정본 보존)
COPY src ./src
COPY model-pool.yaml ./
RUN uv sync --no-dev --no-install-package torch

# 배포 코드 커밋 추적 (/version). 매 배포 변경 → 맨 뒤 레이어라 앞(모델·deps·코드) 캐시 유지.
ARG GIT_SHA=unknown
ENV GIT_SHA=$GIT_SHA

EXPOSE 8000
# uvicorn worker 1개 (임베딩 모델 중복 로드 방지 — plan 5단계 메모리 예산)
CMD ["uv", "run", "uvicorn", "sourcealignrec.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
