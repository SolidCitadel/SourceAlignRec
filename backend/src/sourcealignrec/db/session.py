from sqlalchemy import text
from sqlmodel import create_engine, Session, SQLModel
from sourcealignrec.core.config import settings

engine = create_engine(settings.database_url)


def init_db() -> None:
    # 모든 모델이 metadata에 등록되도록 명시적 import
    import sourcealignrec.db.models  # noqa: F401

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    SQLModel.metadata.create_all(engine)

    # ── 멱등 schema migrations ──────────────────────────────────────────────────
    # SQLModel.create_all은 새 테이블만 추가하고 기존 테이블 ALTER 안 함. 기존
    # benchmark_judgment 컬럼 수정·추가는 여기서 수동 처리. ALTER ... IF [NOT]
    # EXISTS / DROP NOT NULL은 이미 적용된 상태에서 no-op이라 멱등.
    with engine.connect() as conn:
        # 2026-05-18: phase-split — execution_id를 nullable로 풀고 generation_execution_id 추가.
        conn.execute(text(
            "ALTER TABLE benchmark_judgment "
            "ALTER COLUMN execution_id DROP NOT NULL"
        ))
        conn.execute(text(
            "ALTER TABLE benchmark_judgment "
            "ADD COLUMN IF NOT EXISTS generation_execution_id INTEGER "
            "REFERENCES generation_execution(id) ON DELETE CASCADE"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS "
            "ix_benchmark_judgment_generation_execution_id "
            "ON benchmark_judgment(generation_execution_id)"
        ))
        # 2026-05-23: 백엔드 wire-up Phase 1 — Offering.notice + OfferingProfile 메타.
        conn.execute(text("ALTER TABLE offering ADD COLUMN IF NOT EXISTS notice TEXT"))
        conn.execute(text(
            "ALTER TABLE offering_profile ADD COLUMN IF NOT EXISTS review_count INTEGER"
        ))
        conn.execute(text(
            "ALTER TABLE offering_profile ADD COLUMN IF NOT EXISTS profile_updated_at TIMESTAMP"
        ))
        # 2026-05-23: Phase 1 데이터 백필 plan — Offering.meetings_json 구조화.
        conn.execute(text(
            "ALTER TABLE offering ADD COLUMN IF NOT EXISTS meetings_json TEXT DEFAULT '[]'"
        ))
        # 2026-05-23: 온라인 강의 명시 필드.
        conn.execute(text(
            "ALTER TABLE offering ADD COLUMN IF NOT EXISTS is_online BOOLEAN DEFAULT FALSE"
        ))
        # 2026-05-23: filter-ux-and-academic-source plan — 학점 인정 학과 list.
        conn.execute(text(
            "ALTER TABLE offering ADD COLUMN IF NOT EXISTS recognized_depts_json TEXT DEFAULT '[]'"
        ))
        # 2026-05-26: admin wire-up — User.role (operator 권한). 기존 row는 default 'student'.
        conn.execute(text(
            "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS role VARCHAR DEFAULT 'student' NOT NULL"
        ))
        # 2026-05-27: 사용자 이름 — 아바타 메뉴·프로필 표시용. 신규는 signup 필수, 기존 row는 NULL.
        conn.execute(text(
            "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS name VARCHAR"
        ))
        # 2026-05-27: 졸업 총 이수학점 — 영역 최소합과 별개 스칼라. 미설정=NULL.
        conn.execute(text(
            "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS grad_total_required INTEGER"
        ))
        # 2026-05-27: 강의계획서 원문 permalink — raw syllabus_url 적재(backfill_meta로 기존 row 채움).
        conn.execute(text(
            "ALTER TABLE offering ADD COLUMN IF NOT EXISTS syllabus_url TEXT"
        ))
        # 2026-05-27: AttributeExtraction 처리 마커 backfill — 기존 ReviewAttribute 보유 리뷰를
        # 처리됨으로 표기(row 있는 것만, 가정 없이). 멱등(이미 마킹된 review_id는 skip).
        conn.execute(text(
            "INSERT INTO review_attribute_extraction (review_id, extracted_at) "
            "SELECT review_id, MAX(extracted_at) FROM review_attribute GROUP BY review_id "
            "ON CONFLICT (review_id) DO NOTHING"
        ))
        conn.commit()


def get_session():
    with Session(engine) as session:
        yield session
