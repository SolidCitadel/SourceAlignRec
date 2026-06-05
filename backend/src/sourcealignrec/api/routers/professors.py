"""교수 상세 router — api-contract/professors.md (GET /professors/{id}).

소속 + 종합 5필드 프로필 + 교수 대표리뷰 + 개설 강의.
profile은 ProfessorProfile.profile_json에서 파생 — 데이터 없으면 null.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, func, select

from sourcealignrec.api._review_view import types_for_review
from sourcealignrec.api._schemas import WireModel
from sourcealignrec.api._security import get_current_user, get_user_dept_code
from sourcealignrec.online import dept_lens
from sourcealignrec.db.models import (
    Course,
    Offering,
    Professor,
    ProfessorProfile,
    ProfessorRepresentativeReview,
    Review,
    ReviewClassification,
    User,
)
from sourcealignrec.db.session import get_session

router = APIRouter(tags=["professors"])


class ProfRepReviewOut(WireModel):
    id: str
    rank: int
    text: str
    types: list[str]
    term: str


class ProfOfferingOut(WireModel):
    id: str
    course_name: str
    term: str
    type: str


class ProfProfileOut(WireModel):
    """교수 종합 4필드 프로필 (교수 일반화 특성). 과목 주제(topic)는 제외 — 강의 목록 섹션이 담당."""
    format: str
    evaluation: str
    reviews_summary: str
    caveats: str


class ProfessorDetailOut(WireModel):
    id: str
    name: str
    affiliation: str | None = None
    review_count: int
    profile: ProfProfileOut | None = None   # ProfessorProfile 미생성 시 null
    representative_reviews: list[ProfRepReviewOut]
    offerings: list[ProfOfferingOut]


def _parse_profile(profile_json: str | None) -> ProfProfileOut | None:
    """ProfessorProfile.profile_json → 4필드. row 없거나 본문(format) 비면 null emit."""
    if not profile_json:
        return None
    try:
        d = json.loads(profile_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not d.get("format", "").strip():
        return None
    return ProfProfileOut(
        format=d.get("format", ""),
        evaluation=d.get("evaluation", ""),
        reviews_summary=d.get("reviews_summary", ""),
        caveats=d.get("caveats", ""),
    )


@router.get("/professors/{professor_id}", response_model=ProfessorDetailOut)
def get_professor(
    professor_id: str,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    dept_code: str | None = Depends(get_user_dept_code),
):
    professor = session.get(Professor, professor_id)
    if professor is None:
        raise HTTPException(status_code=404, detail="교수를 찾을 수 없습니다.")

    # reviewCount: 전체 Review 수 (noise 포함 — offering reviewCount 관례와 일관).
    review_count = session.exec(
        select(func.count()).select_from(Review).where(Review.professor_id == professor_id)
    ).one()

    rep_rows = session.exec(
        select(Review.id, Review.raw_text, Review.term, ProfessorRepresentativeReview.rank)
        .join(ProfessorRepresentativeReview, ProfessorRepresentativeReview.review_id == Review.id)
        .where(ProfessorRepresentativeReview.professor_id == professor_id)
        .order_by(ProfessorRepresentativeReview.rank)
    ).all()
    rep_cls: dict = {}
    if rep_rows:
        rep_ids = [rid for rid, *_ in rep_rows]
        rep_cls = {
            c.review_id: c
            for c in session.exec(
                select(ReviewClassification).where(ReviewClassification.review_id.in_(rep_ids))
            ).all()
        }
    representative_reviews = [
        ProfRepReviewOut(
            id=rid,
            rank=rank,
            text=text,
            types=types_for_review(rep_cls.get(rid)),
            term=term,
        )
        for rid, text, term, rank in rep_rows
    ]

    off_rows = session.exec(
        select(Offering.id, Course.name, Offering.term)
        .join(Course, Course.id == Offering.course_id)
        .where(Offering.professor_id == professor_id)
        .order_by(Offering.term.desc())
    ).all()
    off_lens = dept_lens.dept_classification_map(session, dept_code, [oid for oid, *_ in off_rows])
    offerings = [
        ProfOfferingOut(id=oid, course_name=cname, term=term, type=off_lens.get(oid, ""))
        for oid, cname, term in off_rows
    ]

    profile_row = session.get(ProfessorProfile, professor_id)
    profile = _parse_profile(profile_row.profile_json if profile_row else None)

    return ProfessorDetailOut(
        id=professor.id,
        name=professor.name,
        affiliation=professor.affiliation,
        review_count=review_count,
        profile=profile,
        representative_reviews=representative_reviews,
        offerings=offerings,
    )
