"""OfferingSummary + meetings hydrate helper. wishlist/timetable 응답 공통.

api-contract/wishlist.md, api-contract/timetable.md의 `WishlistItem` / `ScheduledCourse`는
동일 shape (`OfferingSummary + meetings`). 두 router가 동일 helper로 hydrate.
"""
from __future__ import annotations

from sqlmodel import Session, select

from sourcealignrec.api._schemas import ClassMeetingOut, WireModel, parse_meetings_json
from sourcealignrec.db.models import Course, Offering, Professor
from sourcealignrec.online import dept_lens


class OfferingSummaryOut(WireModel):
    id: str
    course_name: str
    professor_id: str
    professor_name: str
    credit: int
    type: str
    meetings: list[ClassMeetingOut]
    is_online: bool


def summaries_by_ids(
    session: Session, offering_ids: list[str], dept_code: str | None = None,
) -> dict[str, OfferingSummaryOut]:
    """offering_id list → {id: OfferingSummaryOut}. 미존재 id는 누락.

    Offering + Course + Professor 1 query JOIN. 응답 정렬은 호출 측 책임.
    type(이수구분)은 dept_code(조회학과) 렌즈 — 그 학과 카탈로그에 없으면 빈 문자열.
    dept_code 미지정 시 빈 문자열(렌즈 정보 없음).
    """
    if not offering_ids:
        return {}
    rows = session.exec(
        select(Offering, Course, Professor)
        .join(Course, Course.id == Offering.course_id)
        .join(Professor, Professor.id == Offering.professor_id)
        .where(Offering.id.in_(offering_ids))
    ).all()
    lens = dept_lens.dept_classification_map(session, dept_code, offering_ids)
    return {
        o.id: OfferingSummaryOut(
            id=o.id,
            course_name=c.name if c else "(unknown)",
            professor_id=o.professor_id,
            professor_name=p.name if p else "(unknown)",
            credit=o.credits or 0,
            type=lens.get(o.id, ""),
            meetings=parse_meetings_json(o.meetings_json),
            is_online=bool(o.is_online),
        )
        for o, c, p in rows
    }


def offering_exists(session: Session, offering_id: str) -> bool:
    return session.get(Offering, offering_id) is not None
