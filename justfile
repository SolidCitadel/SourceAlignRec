# SourceAlignRec 배포 명령 모음 (just <recipe>). just 미설치 시 각 recipe의 명령을 복붙해 사용.
#
# 전제 (초기 1회):
#   - 로컬: docker buildx create --name sarbuilder --driver docker-container --bootstrap --use
#   - 로컬·Oracle: docker login ghcr.io -u SolidCitadel   (PAT, read/write:packages)
#   - Oracle: ~/sar/ 에 docker-compose.yml, backend/.env, backend/model-pool.yaml 배치
#   - 최초 배포 상세 절차: backend/work/deployment/oracle-deploy.md
#
# 아키텍처: 프론트(Vercel, coursehub.kro.kr) → /api rewrites proxy → Oracle ARM backend(:8000)
#           backend = FastAPI(임베딩 in-process) + pgvector, docker-compose 동거

oracle := "oracle"
image  := "ghcr.io/solidcitadel/sourcealignrec-backend:latest"
remote := "~/projects/sar"

set shell := ["bash", "-cu"]

# recipe 목록
default:
    @just --list

# 로컬 개발: DB(pgvector) 기동 + 백엔드 reload 서버 (Ctrl-C로 종료). DB는 백그라운드 유지.
dev:
    docker compose up -d db
    cd backend && uv run uvicorn sourcealignrec.api.main:app --reload --port 8000

# 로컬 DB(현재 임베딩 포함) 덤프 → Oracle 복원. 임베딩 재생성/스키마 변경 후 사용.
# 설계상 로컬이 유일한 정본이고 원격은 그 거울이다 — 원격 DB를 통째로 덮어쓰는(--clean: DROP 포함)
# 것이 이 명령의 의도된 동작이다. 따라서 원격 전용 데이터(라이브 가입 계정·위시리스트·시간표 등)는
# 보존하지 않는다(매 동기화마다 로컬 상태로 리셋). 보존이 필요하면 이 명령을 쓰지 말 것.
# 복원은 --single-transaction(실패 시 전체 롤백 → 원격 무손상) + ON_ERROR_STOP=1(silent 실패 방지).
sync-db:
    docker compose exec -T db pg_dump -U sar -d sourcealignrec --clean --if-exists --no-owner > backend/dumps/dump-latest.sql
    scp backend/dumps/dump-latest.sql {{oracle}}:{{remote}}/dump.sql
    ssh {{oracle}} 'cat {{remote}}/dump.sql | docker compose -f {{remote}}/docker-compose.yml exec -T db psql -U sar -d sourcealignrec --single-transaction -v ON_ERROR_STOP=1'

# 백엔드 코드 변경 적용: arm64 빌드 → GHCR push → Oracle pull + 재기동
deploy-backend:
    docker buildx build --builder sarbuilder --platform linux/arm64 --build-arg GIT_SHA=$(git rev-parse --short HEAD) -t {{image}} --push backend/
    ssh {{oracle}} 'cd {{remote}} && docker compose pull backend && docker compose up -d backend'

# 모델/풀 설정만 변경 (재빌드 없음 — model-pool.yaml은 volume mount). 모델 deprecated 대응 등.
update-model:
    scp backend/model-pool.yaml {{oracle}}:{{remote}}/backend/model-pool.yaml
    ssh {{oracle}} 'cd {{remote}} && docker compose up -d backend'

# .env(CORS/JWT/모델 override) 변경 적용
sync-env:
    scp backend/.env {{oracle}}:{{remote}}/backend/.env
    ssh {{oracle}} 'cd {{remote}} && docker compose up -d backend'

# docker-compose.yml 변경 적용
sync-compose:
    scp docker-compose.yml {{oracle}}:{{remote}}/
    ssh {{oracle}} 'cd {{remote}} && docker compose up -d'

# Caddyfile(라우팅·TLS 도메인) 변경 적용 — :ro 마운트라 원격 파일 갱신 + caddy 재기동 필요.
# compose 자체가 안 바뀌면 sync-compose는 caddy를 재생성 안 하므로 이 recipe로 반영한다.
sync-caddy:
    scp Caddyfile {{oracle}}:{{remote}}/Caddyfile
    ssh {{oracle}} 'cd {{remote}} && docker compose restart caddy'

# 원격 로그 (예: just logs backend / just logs caddy / just logs db)
logs service="backend":
    ssh {{oracle}} 'cd {{remote}} && docker compose logs {{service}} --tail 40'

# 원격 메모리/컨테이너 상태
stats:
    ssh {{oracle}} 'docker stats --no-stream'

ps:
    ssh {{oracle}} 'cd {{remote}} && docker compose ps'

# Caddy TLS 재시도 (kro.kr LE rate limit 풀린 후 — 성공 시 vercel.json을 https로 전환 가능)
retry-tls:
    ssh {{oracle}} 'cd {{remote}} && docker compose restart caddy && sleep 8 && docker compose logs caddy --tail 15'

# 배포 반영 종합 확인 (각 변경 후 just verify)
verify:
    @echo "── /docs (Vercel 프록시 / 백엔드 직접) ──"
    -@curl -s -o /dev/null -w "  proxy  %{http_code}\n" https://coursehub.kro.kr/api/docs
    -@curl -s -o /dev/null -w "  direct %{http_code}\n" http://coursehub-api.kro.kr:8000/docs
    @echo "── 배포 코드 커밋 (deploy-backend) — 로컬 HEAD와 일치하는지 ──"
    -@curl -s http://coursehub-api.kro.kr:8000/version; echo "  (로컬 HEAD: $(git rev-parse --short HEAD))"
    @echo "── 실행 이미지 digest ──"
    ssh {{oracle}} 'cd {{remote}} && docker compose images backend'
    @echo "── 추천 모델 model_name (update-model) ──"
    ssh {{oracle}} 'cd {{remote}} && docker compose exec -T backend sh -c "grep -A6 \"model_id: google/gemini-3.1-flash-lite\" /app/model-pool.yaml | grep model_name"'
    @echo "── CORS env (sync-env) ──"
    ssh {{oracle}} 'cd {{remote}} && docker compose exec -T backend printenv SAR_CORS_ORIGINS'
    @echo "── DB profile 임베딩 수 (sync-db) ──"
    ssh {{oracle}} 'cd {{remote}} && docker compose exec -T db psql -U sar -d sourcealignrec -tc "select count(*) from offering_profile where embedding is not null"'
