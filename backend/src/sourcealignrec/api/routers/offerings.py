"""Offering 상세 router — api-contract/offerings.md 정합 (GET /offerings/{id})."""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from sourcealignrec.api._review_view import types_for_review
from sourcealignrec.api._schemas import ClassMeetingOut, WireModel, parse_meetings_json
from sourcealignrec.api._security import get_current_user, get_user_dept_code
from sourcealignrec.online import dept_lens
from sourcealignrec.db.models import (
    Course,
    Offering,
    OfferingAttribute,
    OfferingProfile,
    Professor,
    RepresentativeReview,
    Review,
    ReviewClassification,
    User,
)
from sourcealignrec.db.session import get_session

router = APIRouter(tags=["offerings"])


# ── Wire schemas ────────────────────────────────────────────────────────────


class OfferingAttributesOut(WireModel):
    """row 없거나 winner가 '없음'이면 null emit."""
    grading: str | None = None
    assignment: str | None = None
    team_project: str | None = None
    exam_weight: str | None = None
    attendance: str | None = None


class OfferingProfileOut(WireModel):
    topic: str
    format: str
    evaluation: str
    reviews_summary: str
    caveats: str


class EvaluationItemOut(WireModel):
    item: str
    weight: int
    note: str | None = None


class WeeklyTopicOut(WireModel):
    week: int
    topic: str


class RepresentativeReviewOut(WireModel):
    id: str
    rank: int
    text: str
    types: list[str]
    term: str | None = None


class LateralOfferingOut(WireModel):
    id: str
    term: str
    professor_name: str
    course_name: str | None = None


class LateralOut(WireModel):
    same_course: list[LateralOfferingOut]
    same_professor: list[LateralOfferingOut]


class OfferingDetailOut(WireModel):
    id: str
    course_name: str
    professor_id: str
    professor_name: str
    credit: int
    type: str
    department: str
    english_only: bool
    is_online: bool
    meetings: list[ClassMeetingOut]
    attributes: OfferingAttributesOut

    profile: OfferingProfileOut
    profile_updated_at: str | None = None
    review_count: int

    notice: str | None = None
    syllabus_url: str | None = None

    evaluation: list[EvaluationItemOut]
    weekly_topics: list[WeeklyTopicOut]
    prerequisites: list[str]

    representative_reviews: list[RepresentativeReviewOut]
    lateral: LateralOut


# ── Helpers ─────────────────────────────────────────────────────────────────


def _safe_json(raw: str | None) -> list:
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _attribute_map(session: Session, offering_id: str) -> dict[str, str]:
    rows = session.exec(
        select(OfferingAttribute.attribute_name, OfferingAttribute.attribute_value)
        .where(OfferingAttribute.offering_id == offering_id)
    ).all()
    return {name: value for name, value in rows}


def _attrs_out(attrs_db: dict[str, str]) -> OfferingAttributesOut:
    """row 없거나 '없음' winner면 None."""
    def emit(v: str | None) -> str | None:
        return None if v is None or v == "없음" else v

    return OfferingAttributesOut(
        grading=emit(attrs_db.get("grading_leniency")),
        assignment=emit(attrs_db.get("assignment_load")),
        team_project=emit(attrs_db.get("team_project")),
        exam_weight=emit(attrs_db.get("exam_weight")),
        attendance=emit(attrs_db.get("attendance_strictness")),
    )


def _parse_profile(profile_json: str | None) -> OfferingProfileOut:
    if not profile_json:
        return OfferingProfileOut(topic="", format="", evaluation="", reviews_summary="", caveats="")
    try:
        d = json.loads(profile_json)
    except (json.JSONDecodeError, TypeError):
        d = {}
    return OfferingProfileOut(
        topic=d.get("topic", ""),
        format=d.get("format", ""),
        evaluation=d.get("evaluation", ""),
        reviews_summary=d.get("reviews_summary", ""),
        caveats=d.get("caveats", ""),
    )


def _representative_reviews(
    session: Session, course_id: str, professor_id: str,
) -> list[RepresentativeReviewOut]:
    rows = session.exec(
        select(Review.id, Review.raw_text, Review.term, RepresentativeReview.rank)
        .join(RepresentativeReview, RepresentativeReview.review_id == Review.id)
        .where(RepresentativeReview.course_id == course_id)
        .where(RepresentativeReview.professor_id == professor_id)
        .order_by(RepresentativeReview.rank)
    ).all()
    if not rows:
        return []
    review_ids = [rid for rid, *_ in rows]
    classifications = {
        c.review_id: c
        for c in session.exec(
            select(ReviewClassification).where(ReviewClassification.review_id.in_(review_ids))
        ).all()
    }
    return [
        RepresentativeReviewOut(
            id=rid,
            rank=rank,
            text=text,
            types=types_for_review(classifications.get(rid)),
            term=term,
        )
        for rid, text, term, rank in rows
    ]


def _lateral(
    session: Session, offering: Offering, professor_name: str,
) -> LateralOut:
    """같은 course/professor의 다른 offering. 본인 제외."""
    same_course_rows = session.exec(
        select(Offering.id, Offering.term, Professor.name)
        .join(Professor, Professor.id == Offering.professor_id)
        .where(Offering.course_id == offering.course_id)
        .where(Offering.id != offering.id)
    ).all()
    same_prof_rows = session.exec(
        select(Offering.id, Offering.term, Course.name)
        .join(Course, Course.id == Offering.course_id)
        .where(Offering.professor_id == offering.professor_id)
        .where(Offering.id != offering.id)
    ).all()
    same_course = [
        LateralOfferingOut(id=oid, term=term, professor_name=pname)
        for oid, term, pname in same_course_rows
    ]
    same_professor = [
        LateralOfferingOut(id=oid, term=term, professor_name=professor_name, course_name=cname)
        for oid, term, cname in same_prof_rows
    ]
    return LateralOut(same_course=same_course, same_professor=same_professor)


# ── Endpoint ────────────────────────────────────────────────────────────────


@router.get("/offerings/{offering_id}", response_model=OfferingDetailOut)
def get_offering(
    offering_id: str,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    dept_code: str | None = Depends(get_user_dept_code),
):
    offering = session.get(Offering, offering_id)
    if offering is None:
        raise HTTPException(status_code=404, detail="강의를 찾을 수 없습니다.")

    course = session.get(Course, offering.course_id)
    professor = session.get(Professor, offering.professor_id)
    profile_row = session.exec(
        select(OfferingProfile).where(OfferingProfile.offering_id == offering_id)
    ).first()
    review_count = session.exec(
        select(Review.id)
        .where(Review.course_id == offering.course_id)
        .where(Review.professor_id == offering.professor_id)
    ).all()

    attrs_db = _attribute_map(session, offering_id)
    attrs_out = _attrs_out(attrs_db)
    profile = _parse_profile(profile_row.profile_json if profile_row else None)
    profile_updated_at = (
        profile_row.profile_updated_at.date().isoformat()
        if profile_row and profile_row.profile_updated_at
        else None
    )

    evaluation_raw = _safe_json(offering.evaluation_items)
    weekly_raw = _safe_json(offering.weekly_topics)
    prereq_raw = _safe_json(offering.prerequisite_courses)

    return OfferingDetailOut(
        id=offering.id,
        course_name=course.name if course else "(unknown)",
        professor_id=offering.professor_id,
        professor_name=professor.name if professor else "(unknown)",
        credit=offering.credits or 0,
        type=dept_lens.dept_classification_map(session, dept_code, [offering_id]).get(offering_id, ""),
        department=offering.dept_name or "",
        english_only=offering.is_english,
        is_online=bool(offering.is_online),
        meetings=parse_meetings_json(offering.meetings_json),
        attributes=attrs_out,
        profile=profile,
        profile_updated_at=profile_updated_at,
        review_count=profile_row.review_count if profile_row and profile_row.review_count is not None else len(review_count),
        notice=offering.notice,
        syllabus_url=offering.syllabus_url,
        evaluation=[
            EvaluationItemOut(
                item=str(e.get("item", "")),
                weight=int(e.get("ratio", e.get("weight", 0)) or 0),
                note=e.get("note"),
            )
            for e in evaluation_raw
            if isinstance(e, dict)
        ],
        weekly_topics=[
            WeeklyTopicOut(week=i + 1, topic=str(t))
            for i, t in enumerate(weekly_raw)
        ],
        prerequisites=[
            p["name"] if isinstance(p, dict) and "name" in p else str(p)
            for p in prereq_raw
        ],
        representative_reviews=_representative_reviews(session, offering.course_id, offering.professor_id),
        lateral=_lateral(session, offering, professor.name if professor else ""),
    )
