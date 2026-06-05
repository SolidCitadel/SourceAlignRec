# SourceAlignRec

강의 소스(과목 설명·강의계획서·강의평)에서 추천 판단 근거를 구조화하고, 근거와 함께 현재 개설 강좌를 추천하는 대화형 수강 추천 시스템. 경희대학교 컴퓨터공학과 졸업프로젝트.

- 서비스: [coursehub.kro.kr](https://coursehub.kro.kr)
- 이 저장소는 최종 평가 제출용 소스코드입니다. 벤치마크 코드·데이터 수집 파이프라인·내부 문서는 제출 범위에서 제외했습니다.

## 구조

```text
backend/    FastAPI + SQLModel + PostgreSQL(pgvector) + openai SDK
frontend/   Vite + React 19 + TypeScript + react-router 7 + TanStack Query + Zustand
```

### backend/src/sourcealignrec/

| 폴더 | 역할 |
|------|------|
| `offline/ingestion/` | 강의평·강의계획서 DB 적재 |
| `offline/classifier/` | ReviewClassifier — BERT 기반 리뷰 타입 분류 학습·추론 |
| `offline/extractor/` | AttributeExtractor — 리뷰 속성 추출 학습·추출 파이프라인 |
| `offline/selector/` | DynamicScore 알고리즘 — 대표 리뷰 선정 + 리뷰 임베딩 |
| `offline/profiler/` | Offering/Professor Profile 생성 + 임베딩 |
| `offline/eval/` | eval split 기반 모델 성능 측정 |
| `online/filter.py` | Hard Filter (속성 조건 + 수강 이력 제외) |
| `online/systems/` | 추천 시스템 — Profile 검색 기반 추천(system_d) + tool grounding 대화(system_e) |
| `online/mcp/` + `api/mcp_server.py` | ChatKHU 연동용 MCP 도구 6종 |
| `api/` | HTTP API 라우터 (추천·검색·인증·위시리스트·시간표 등) |
| `db/models.py` | 전체 DB 스키마 (SQLModel) |

오프라인 파이프라인 실행 순서와 CLI 전체 목록은 `backend/pyproject.toml`의 `[project.scripts]` 참조.

## 로컬 실행

전제: Docker, [uv](https://docs.astral.sh/uv/), Node.js. 환경 변수는 `backend/.env.example` → `backend/.env`로 복사 후 채운다 (LLM API 키 필요).

```bash
# 백엔드: pgvector DB 기동 + reload 서버 (just 설치 시 `just dev`)
docker compose up -d db
cd backend && uv run uvicorn sourcealignrec.api.main:app --reload --port 8000

# 프론트엔드
cd frontend && npm install && npm run dev
```

추천 품질은 DB에 적재·가공된 데이터(강의평·강의계획서·프로필)에 의존하므로, 빈 DB에서는 API 서버와 UI 동작만 확인할 수 있다.

## 배포 구성

프론트(Vercel) → `/api` rewrite proxy → Oracle ARM 인스턴스의 docker-compose(FastAPI + pgvector + Caddy). 배포 명령은 `justfile` 참조.