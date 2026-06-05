"""강의평 router — api-contract/reviews.md.

GET  /offerings/{id}/reviews : offering의 (course_id, professor_id) 전 학기 리뷰. noise 제외.
POST /offerings/{id}/reviews : 사용자 직접 등록(source='user'). 분류 전이라 unprocessed로 표시.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field as PydField
from sqlmodel import Session, select

from sourcealignrec.api._review_view import types_for_review
from sourcealignrec.api._schemas import WireModel
from sourcealignrec.api._security import get_current_user
from sourcealignrec.db.models import Offering, Review, ReviewClassification, User
from sourcealignrec.db.session import get_session

router = APIRouter(tags=["reviews"])

MIN_REVIEW_LEN = 10  # 프론트 ReviewModal canSubmit과 동일


class ReviewItemOut(WireModel):
    id: str
    text: str
    term: str
    status: str            # valid | unprocessed (noise는 응답 제외)
    types: list[str]


class ReviewListOut(WireModel):
    items: list[ReviewItemOut]


class ReviewCreateIn(WireModel):
    term: str = PydField(min_length=1)
    text: str = PydField(min_length=MIN_REVIEW_LEN)


@router.get("/offerings/{offering_id}/reviews", response_model=ReviewListOut)
def list_offering_reviews(
    offering_id: str,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    offering = session.get(Offering, offering_id)
    if offering is None:
        raise HTTPException(status_code=404, detail="강의를 찾을 수 없습니다.")

    # 분류 정본은 ReviewClassification(is_noise)이다 — Review.classification은 dead field라
    # 쓰지 않는다. noise(is_noise=True) 제외, valid + unprocessed(RC 없음)만 노출.
    rows = session.exec(
        select(Review.id, Review.raw_text, Review.term)
        .where(Review.course_id == offering.course_id)
        .where(Review.professor_id == offering.professor_id)
        .order_by(Review.term.desc())
    ).all()
    if not rows:
        return ReviewListOut(items=[])

    review_ids = [rid for rid, *_ in rows]
    classifications = {
        c.review_id: c
        for c in session.exec(
            select(ReviewClassification).where(ReviewClassification.review_id.in_(review_ids))
        ).all()
    }
    items = [
        ReviewItemOut(
            id=rid,
            text=text,
            term=term,
            status=_review_status(classifications.get(rid)),
            types=types_for_review(classifications.get(rid)),
        )
        for rid, text, term in rows
        if not (classifications.get(rid) and classifications[rid].is_noise)
    ]
    return ReviewListOut(items=items)


@router.post("/offerings/{offering_id}/reviews", response_model=ReviewItemOut, status_code=201)
def create_offering_review(
    offering_id: str,
    body: ReviewCreateIn,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """사용자 직접 등록 강의평. (course_id, professor_id)는 offering에서 파생.

    분류·임베딩 등 오프라인 파이프라인은 다음 배치에서 처리 — 등록 직후엔 unprocessed로 표시.
    """
    offering = session.get(Offering, offering_id)
    if offering is None:
        raise HTTPException(status_code=404, detail="강의를 찾을 수 없습니다.")

    text = body.text.strip()
    if len(text) < MIN_REVIEW_LEN:
        raise HTTPException(status_code=422, detail=f"리뷰는 최소 {MIN_REVIEW_LEN}자 이상이어야 합니다.")

    review = Review(
        id=uuid.uuid4().hex,
        course_id=offering.course_id,
        professor_id=offering.professor_id,
        term=body.term,
        raw_text=text,
        source="user",
        author_id=user.id,
        created_at=datetime.utcnow(),
    )
    session.add(review)
    session.commit()

    # 신규 리뷰는 ReviewClassification이 아직 없음 → unprocessed, types 빈 배열.
    return ReviewItemOut(id=review.id, text=text, term=body.term, status="unprocessed", types=[])


def _review_status(rc: ReviewClassification | None) -> str:
    """RC 정본 기준 status. noise는 호출부에서 이미 제외됨."""
    if rc is None:
        return "unprocessed"
    return "noise" if rc.is_noise else "valid"
