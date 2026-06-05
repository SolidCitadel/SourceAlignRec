"""Admin 대시보드 router — api-contract/admin.md 정합. **읽기 전용.**

operator(role='admin')만 접근. offline 파이프라인 현황을 실제 DB에서 집계해 노출한다.
파이프라인 *실행* 트리거(`sar-*` CLI 비동기 실행 + polling)는 본 라우터 scope 밖 — 별도 plan.

설계 메모:
- counts·classification은 학기(term) 필터 적용. 파이프라인 단계는 corpus 전역 처리 현황이라
  term 무관(전체 기준). spec(frontend.md §Admin)의 "학기 무관한 단계는 전체 카운트 그대로" 정합.
- 파이프라인 5단계: ReviewClassification / AttributeExtraction / Course 대표리뷰 /
  Professor 대표리뷰 / OfferingProfile. spec의 ProfessorProfile은 모델 제거됨(재구축 예정),
  ReviewEmbedding은 ablation 전용이라 둘 다 대시보드 제외.
- recentLogs는 실행 로그 테이블 부재 + 읽기 전용이라 항상 빈 list. 실행 트리거 plan에서 채워짐.
- lastRunAt: 각 산출물 테이블의 timestamp max → 'YYYY-MM-DD', 없으면 '—'.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func
from sqlmodel import Session, select

from sourcealignrec.api._schemas import WireModel
from sourcealignrec.api._security import get_current_admin
from sourcealignrec.offline.candidates import (
    attr_candidate_review_ids,
    course_rep_candidate_pairs,
    professor_rep_candidate_profs,
)
from sourcealignrec.db.models import (
    Course,
    Offering,
    OfferingDeptClassification,
    OfferingProfile,
    ProfessorRepresentativeReview,
    RepresentativeReview,
    Review,
    ReviewAttributeExtraction,
    ReviewClassification,
    User,
)
from sourcealignrec.db.session import get_session

router = APIRouter(tags=["admin"])


# ── Wire schemas ────────────────────────────────────────────────────────────


class AdminCountsOut(WireModel):
    departments: int  # 수집학과 수 — distinct OfferingDeptClassification.dept_code (= 크롤링 범위)
    course: int
    offering: int
    review: int


class AdminClassificationOut(WireModel):
    unprocessed: int
    valid: int
    noise: int


class AdminPipelineStepOut(WireModel):
    name: str
    input: int
    processed: int
    pending: int
    last_run_at: str  # 'YYYY-MM-DD' 또는 '—'
    term_scoped: bool  # False면 학기 무관(전 학기 집계) 단계 — 학기 선택해도 전체 카운트 유지


class AdminLogOut(WireModel):
    timestamp: str
    task: str
    duration: str
    status: str  # ok | fail


class AdminStatsOut(WireModel):
    counts: AdminCountsOut
    classification: AdminClassificationOut
    pipeline: list[AdminPipelineStepOut]
    recent_logs: list[AdminLogOut]
    available_terms: list[str]


# ── helpers ───────────────────────────────────────────────────────────────


def _is_global(term: str | None) -> bool:
    """term이 없거나 '전체' sentinel이면 전역(필터 없음)."""
    return not term or term == "전체"


def _fmt(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d") if dt else "—"


def _count_distinct_pairs(session: Session, col_a, col_b, where=None) -> int:
    """COUNT(DISTINCT (a,b)) — sqlite/pg 양쪽 호환 위해 distinct 서브쿼리로 우회."""
    inner = select(col_a, col_b)
    if where is not None:
        inner = inner.where(where)
    inner = inner.distinct().subquery()
    return session.scalar(select(func.count()).select_from(inner)) or 0


def _counts(session: Session, term: str | None) -> AdminCountsOut:
    # 수집학과 = distinct OfferingDeptClassification.dept_code (= 크롤링한 학과 카탈로그 범위).
    # 개설학과(Offering.dept_name)가 아니라 인정학과 기준 — 그 학과 카탈로그를 수집했다는 정본.
    dept_stmt = select(func.count(distinct(OfferingDeptClassification.dept_code)))
    if _is_global(term):
        course = session.scalar(select(func.count()).select_from(Course)) or 0
        offering = session.scalar(select(func.count()).select_from(Offering)) or 0
        review = session.scalar(select(func.count()).select_from(Review)) or 0
        departments = session.scalar(dept_stmt) or 0
    else:
        course = session.scalar(
            select(func.count(distinct(Offering.course_id))).where(Offering.term == term)
        ) or 0
        offering = session.scalar(
            select(func.count()).select_from(Offering).where(Offering.term == term)
        ) or 0
        review = session.scalar(
            select(func.count()).select_from(Review).where(Review.term == term)
        ) or 0
        departments = session.scalar(
            dept_stmt.select_from(OfferingDeptClassification)
            .join(Offering, OfferingDeptClassification.offering_id == Offering.id)
            .where(Offering.term == term)
        ) or 0
    return AdminCountsOut(
        departments=departments, course=course, offering=offering, review=review
    )


def _review_total(session: Session, term: str | None) -> int:
    if _is_global(term):
        return session.scalar(select(func.count()).select_from(Review)) or 0
    return session.scalar(
        select(func.count()).select_from(Review).where(Review.term == term)
    ) or 0


def _classified_count(session: Session, term: str | None, noise_only: bool = False) -> int:
    """ReviewClassification 행이 있는 distinct 리뷰 수(= classified). noise_only면 is_noise만.

    분류 결과의 정본은 ReviewClassification 테이블(is_noise)이다 — Review.classification
    필드는 파이프라인이 채우지 않는 dead field라 사용하지 않는다.
    """
    stmt = (
        select(func.count(distinct(ReviewClassification.review_id)))
        .select_from(ReviewClassification)
        .join(Review, ReviewClassification.review_id == Review.id)
    )
    if not _is_global(term):
        stmt = stmt.where(Review.term == term)
    if noise_only:
        stmt = stmt.where(ReviewClassification.is_noise == True)  # noqa: E712
    return session.scalar(stmt) or 0


def _classification(session: Session, term: str | None) -> AdminClassificationOut:
    total = _review_total(session, term)
    classified = _classified_count(session, term)
    noise = _classified_count(session, term, noise_only=True)
    return AdminClassificationOut(
        unprocessed=total - classified,
        valid=classified - noise,
        noise=noise,
    )


def _pipeline(session: Session, term: str | None) -> list[AdminPipelineStepOut]:
    """파이프라인 단계별 처리 현황.

    각 게이트 단계의 input = 후보 집합(`offline.candidates`) — extractor·selector가 실제
    처리하는 부분집합과 동일 정의. 미처리 = 후보 − 산출물. 분류 정본은 ReviewClassification.

    term 처리 (spec frontend.md §Admin "학기 무관한 단계는 전체 카운트 그대로"):
    - ReviewClassification·AttributeExtraction(Review.term)·OfferingProfile(Offering.term)은
      학기 필터 적용(term_scoped=True).
    - 대표리뷰 2단계는 (course, professor)/professor 단위 **전 학기 집계**라 term 컬럼이 없고
      후보 임계(valid ≥ N)도 전 학기 합산 → 학기로 쪼개면 정의가 깨짐. 전역 유지(term_scoped=False).
    - last_run_at은 항상 전역: offline job이 코퍼스 전체를 한 번에 돌아 학기별 실행시각이 없음.
    """
    t = None if _is_global(term) else term

    total_reviews = _review_total(session, t)
    classified = _classified_count(session, t)

    # 2. AttributeExtraction — 후보 = valid 리뷰 중 attr 신호 보유. processed = 처리 마커 보유 후보.
    #    마커(ReviewAttributeExtraction)는 결과 0건 후보도 기록 → '처리했으나 결과 없음'을 미처리와 구분.
    #    후보를 term으로 제한하면 전역 marked 집합과의 교집합이 자연히 그 학기 후보로 좁혀짐.
    attr_candidates = attr_candidate_review_ids(session, term=t)
    attr_marked = set(session.exec(select(ReviewAttributeExtraction.review_id)).all())
    attr_input = len(attr_candidates)
    attr_processed = len(attr_candidates & attr_marked)

    # 3. Course 대표리뷰 — 전 학기 집계, term 무관.
    rep_input = len(course_rep_candidate_pairs(session))
    rep_processed = _count_distinct_pairs(
        session, RepresentativeReview.course_id, RepresentativeReview.professor_id
    )

    # 4. Professor 대표리뷰 — 전 학기 집계, term 무관.
    prof_input = len(professor_rep_candidate_profs(session))
    prof_processed = session.scalar(
        select(func.count(distinct(ProfessorRepresentativeReview.professor_id)))
    ) or 0

    # 5. OfferingProfile — offering 단위(Offering.term).
    if t is None:
        offering_total = session.scalar(select(func.count()).select_from(Offering)) or 0
        profile_count = session.scalar(select(func.count()).select_from(OfferingProfile)) or 0
    else:
        offering_total = session.scalar(
            select(func.count()).select_from(Offering).where(Offering.term == t)
        ) or 0
        profile_count = session.scalar(
            select(func.count()).select_from(OfferingProfile)
            .join(Offering, OfferingProfile.offering_id == Offering.id)
            .where(Offering.term == t)
        ) or 0

    return [
        AdminPipelineStepOut(
            name="ReviewClassification", term_scoped=True,
            input=total_reviews, processed=classified, pending=total_reviews - classified,
            last_run_at=_fmt(session.scalar(select(func.max(ReviewClassification.classified_at)))),
        ),
        AdminPipelineStepOut(
            name="AttributeExtraction", term_scoped=True,
            input=attr_input, processed=attr_processed,
            pending=max(attr_input - attr_processed, 0),
            last_run_at=_fmt(session.scalar(select(func.max(ReviewAttributeExtraction.extracted_at)))),
        ),
        AdminPipelineStepOut(
            name="Course+Professor 대표 리뷰", term_scoped=False,
            input=rep_input, processed=rep_processed, pending=max(rep_input - rep_processed, 0),
            last_run_at=_fmt(session.scalar(select(func.max(RepresentativeReview.selected_at)))),
        ),
        AdminPipelineStepOut(
            name="Professor 대표 리뷰", term_scoped=False,
            input=prof_input, processed=prof_processed,
            pending=max(prof_input - prof_processed, 0),
            last_run_at=_fmt(
                session.scalar(select(func.max(ProfessorRepresentativeReview.selected_at)))
            ),
        ),
        AdminPipelineStepOut(
            name="OfferingProfile", term_scoped=True,
            input=offering_total, processed=profile_count,
            pending=max(offering_total - profile_count, 0),
            last_run_at=_fmt(session.scalar(select(func.max(OfferingProfile.profile_updated_at)))),
        ),
    ]


def _available_terms(session: Session) -> list[str]:
    rows = session.exec(
        select(Offering.term).distinct().order_by(Offering.term.desc())
    ).all()
    return [t for t in rows if t]


# ── Endpoint ───────────────────────────────────────────────────────────────


@router.get("/admin/stats", response_model=AdminStatsOut)
def admin_stats(
    term: str | None = Query(default=None),
    session: Session = Depends(get_session),
    _admin: User = Depends(get_current_admin),
):
    return AdminStatsOut(
        counts=_counts(session, term),
        classification=_classification(session, term),
        pipeline=_pipeline(session, term),
        recent_logs=[],  # 실행 로그 테이블 부재 — 별도 plan
        available_terms=_available_terms(session),
    )
