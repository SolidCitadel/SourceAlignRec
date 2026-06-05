"""파이프라인 게이트 단계의 '후보 집합' 단일 정의 — 상위 단계 출력에서 파생.

AttributeExtraction·Course/Professor 대표리뷰는 입력 전체를 처리하지 않고, 상위 출력
(ReviewClassification·RepresentativeReview)에서 임계·최소건수로 거른 부분집합만 처리한다.
그 후보 정의가 각 처리 모듈 안에 inline으로 흩어져 있으면 admin 대시보드 집계와 어긋난다
(미처리 수치가 실제 대기열을 과대계상). 본 모듈이 후보 정의·임계 상수의 단일 출처이며,
처리 모듈(extractor·selector)과 admin이 함께 consume한다.

TODO(후속): 후보 + done 상태를 materialize하는 파이프라인 단계로 승격하면,
'추출 시도했으나 결과 없음'(row 0개) 케이스까지 미처리와 정확히 구분 가능.
"""
from __future__ import annotations

from collections import defaultdict

from sqlmodel import Session, select

from sourcealignrec.db.models import RepresentativeReview, Review, ReviewClassification

# ── AttributeExtraction 후보 ──────────────────────────────────────────────────
# 분류기 타입 → 그 타입에서만 추출할 attribute. p-score ≥ ATTR_THRESHOLD인 타입의 attr만 대상.
ATTR_THRESHOLD = 0.5
TYPE_TO_ATTRS: dict[str, list[str]] = {
    "grading":    ["grading_leniency"],
    "assignment": ["assignment_load", "team_project"],
    "attendance": ["attendance_strictness"],
}


def eligible_attrs(rc: ReviewClassification, threshold: float = ATTR_THRESHOLD) -> set[str]:
    """이 리뷰(분류 결과)에서 추출 가능한 attribute 집합."""
    attrs: set[str] = set()
    for type_name, attr_list in TYPE_TO_ATTRS.items():
        if getattr(rc, f"{type_name}_score", 0.0) >= threshold:
            attrs.update(attr_list)
    return attrs


def attr_candidate_review_ids(
    session: Session, threshold: float = ATTR_THRESHOLD, term: str | None = None
) -> set[str]:
    """valid(is_noise=False) 리뷰 중 추출 가능한 attr 신호가 있는 review_id 집합.

    term 지정 시 해당 학기(Review.term) 리뷰로 제한 — admin 대시보드 학기 필터용.
    """
    stmt = select(ReviewClassification).where(ReviewClassification.is_noise == False)  # noqa: E712
    if term:
        stmt = stmt.join(Review, ReviewClassification.review_id == Review.id).where(
            Review.term == term
        )
    rcs = session.exec(stmt).all()
    return {rc.review_id for rc in rcs if eligible_attrs(rc, threshold)}


# ── Course 대표리뷰 후보 ──────────────────────────────────────────────────────
COURSE_MIN_REVIEWS = 10


def course_rep_candidate_pairs(
    session: Session, min_reviews: int = COURSE_MIN_REVIEWS
) -> set[tuple[str, str]]:
    """valid 리뷰가 min_reviews개 이상인 (course_id, professor_id) 집합.

    미만 그룹은 selector가 Professor fallback으로 건너뜀 → 대표리뷰 미선정이 정상.
    """
    rows = session.exec(
        select(Review.course_id, Review.professor_id)
        .join(ReviewClassification, ReviewClassification.review_id == Review.id)
        .where(ReviewClassification.is_noise == False)  # noqa: E712
    ).all()
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for course_id, professor_id in rows:
        counts[(course_id, professor_id)] += 1
    return {pair for pair, n in counts.items() if n >= min_reviews}


# ── Professor 대표리뷰 후보 ───────────────────────────────────────────────────
PROF_LABELS = ["grading", "assignment", "attendance", "teaching", "professor"]
PROF_SCORE_FIELDS = [f"{t}_score" for t in PROF_LABELS]
PROF_TYPE_THRESHOLD = 0.5


def professor_rep_candidate_profs(
    session: Session, threshold: float = PROF_TYPE_THRESHOLD
) -> set[str]:
    """Course 대표리뷰 풀 중 prof-type 신호(any prof score ≥ threshold) 보유 교수 집합."""
    rows = session.exec(
        select(RepresentativeReview.professor_id, ReviewClassification)
        .join(Review, RepresentativeReview.review_id == Review.id)
        .join(ReviewClassification, ReviewClassification.review_id == Review.id)
        .where(ReviewClassification.is_noise == False)  # noqa: E712
    ).all()
    return {
        professor_id
        for professor_id, rc in rows
        if any(getattr(rc, f) >= threshold for f in PROF_SCORE_FIELDS)
    }
