from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost/sourcealignrec"
    embedding_dim: int = 1024
    shortlist_size: int = 5
    review_per_offering: int = 10  # System A 전용. shortlist offering당 query-유사 리뷰 top-R. B의 K=10 (대표 리뷰)와 일치시켜 selection 방식만 격리.
    ce_loose_n: int = 20  # System CE_* 전용. D loose 조회 후보 수 → cross-encoder rerank 입력 pool. step 3 N sweep용 (CE_LOOSE_N env로 override).
    recommend_model: str = "chat-khu/gpt-oss-120b"
    # API path 전용 — 사용자 응답 대기 시간 직결. 가벼운 모델 default.
    # benchmark는 위 recommend_model 사용 (품질 측정 목적).
    api_recommend_model: str = "google/gemini-3.1-flash-lite"
    # ── API auth (api-contract/_common.md §2) ───────────────────────────────
    sar_jwt_secret: str = "dev-only-secret-change-in-prod"  # 배포 시 env로 강제 override
    sar_jwt_ttl_days: int = 7
    # Vite default 5173. 점유 시 자동 +1 (5174, ...) — dev 편의를 위해 +1, +2까지 허용.
    sar_cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "http://localhost:5175,http://127.0.0.1:5175"
    )


settings = Settings()
