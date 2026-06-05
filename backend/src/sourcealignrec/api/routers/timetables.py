"""Timetable router — api-contract/timetable.md 정합 (7 endpoint).

이름 정책: 자동 부여(`시안 N`, N = 본인 timetables 중 미사용 최소 양의 정수).
frontend의 `nextTimetableName` 로직 backend로 이관.
"""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlmodel import Session, select

from sourcealignrec.api._offering_view import (
    OfferingSummaryOut,
    offering_exists,
    summaries_by_ids,
)
from sourcealignrec.api._schemas import WireModel
from sourcealignrec.api._security import get_current_user, get_user_dept_code
from sourcealignrec.db.models import Timetable, TimetableCourse, User
from sourcealignrec.db.session import get_session

router = APIRouter(tags=["timetables"])

DEFAULT_TIMETABLE_NAME = "시안 1"
_SIAN_RE = re.compile(r"^시안 (\d+)$")


# ── Wire schemas ────────────────────────────────────────────────────────────


class TimetableOut(WireModel):
    id: str
    name: str
    courses: list[OfferingSummaryOut]


class TimetablesResponse(WireModel):
    timetables: list[TimetableOut]


class TimetableResponse(WireModel):
    timetable: TimetableOut


class TimetableRenameRequest(WireModel):
    name: str = Field(min_length=1, max_length=50)


class TimetableCourseAddRequest(WireModel):
    offering_id: str


class TimetableCourseResponse(WireModel):
    course: OfferingSummaryOut


# ── Helpers ─────────────────────────────────────────────────────────────────


def _next_timetable_name(session: Session, user_id: str) -> str:
    """`시안 N` 패턴 중 미사용 최소 양의 정수. frontend nextTimetableName 정합."""
    taken: set[int] = set()
    rows = session.exec(
        select(Timetable.name).where(Timetable.user_id == user_id)
    ).all()
    for name in rows:
        m = _SIAN_RE.match(name)
        if m:
            taken.add(int(m.group(1)))
    i = 1
    while i in taken:
        i += 1
    return f"시안 {i}"


def _get_owned_timetable(
    session: Session, timetable_id: str, user_id: str,
) -> Timetable:
    """타 user 소유는 404로 마스킹 (정보 누출 방지)."""
    tt = session.get(Timetable, timetable_id)
    if tt is None or tt.user_id != user_id:
        raise HTTPException(status_code=404, detail="시간표를 찾을 수 없습니다.")
    return tt


def _hydrate_timetable(
    session: Session, tt: Timetable, dept_code: str | None = None,
) -> TimetableOut:
    course_rows = session.exec(
        select(TimetableCourse)
        .where(TimetableCourse.timetable_id == tt.id)
        .order_by(TimetableCourse.created_at)
    ).all()
    by_id = summaries_by_ids(session, [r.offering_id for r in course_rows], dept_code)
    courses = [by_id[r.offering_id] for r in course_rows if r.offering_id in by_id]
    return TimetableOut(id=tt.id, name=tt.name, courses=courses)


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/timetables", response_model=TimetablesResponse)
def list_timetables(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    dept_code: str | None = Depends(get_user_dept_code),
):
    rows = session.exec(
        select(Timetable)
        .where(Timetable.user_id == user.id)
        .order_by(Timetable.created_at)
    ).all()
    return TimetablesResponse(
        timetables=[_hydrate_timetable(session, tt, dept_code) for tt in rows],
    )


@router.post("/timetables", response_model=TimetableResponse, status_code=201)
def create_timetable(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    dept_code: str | None = Depends(get_user_dept_code),
):
    tt = Timetable(
        id=uuid.uuid4().hex,
        user_id=user.id,
        name=_next_timetable_name(session, user.id),
    )
    session.add(tt)
    session.commit()
    session.refresh(tt)
    return TimetableResponse(timetable=_hydrate_timetable(session, tt, dept_code))


@router.patch("/timetables/{timetable_id}", response_model=TimetableResponse)
def rename_timetable(
    timetable_id: str,
    req: TimetableRenameRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    dept_code: str | None = Depends(get_user_dept_code),
):
    tt = _get_owned_timetable(session, timetable_id, user.id)
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="시간표 이름이 비어있습니다.")
    tt.name = name
    session.add(tt)
    session.commit()
    session.refresh(tt)
    return TimetableResponse(timetable=_hydrate_timetable(session, tt, dept_code))


@router.delete("/timetables/{timetable_id}", status_code=204)
def delete_timetable(
    timetable_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    tt = _get_owned_timetable(session, timetable_id, user.id)
    total = session.exec(
        select(Timetable.id).where(Timetable.user_id == user.id)
    ).all()
    if len(total) <= 1:
        raise HTTPException(status_code=409, detail="마지막 시간표는 삭제할 수 없습니다.")

    # FK CASCADE 미설정 — courses 명시 삭제 후 flush로 순서 강제.
    # SQLAlchemy ORM relationship 없는 상태에서 flush 미호출 시 DELETE 순서 비결정.
    course_rows = session.exec(
        select(TimetableCourse).where(TimetableCourse.timetable_id == tt.id)
    ).all()
    for row in course_rows:
        session.delete(row)
    session.flush()
    session.delete(tt)
    session.commit()
    return None


@router.post(
    "/timetables/{timetable_id}/duplicate",
    response_model=TimetableResponse,
    status_code=201,
)
def duplicate_timetable(
    timetable_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    dept_code: str | None = Depends(get_user_dept_code),
):
    src = _get_owned_timetable(session, timetable_id, user.id)
    src_courses = session.exec(
        select(TimetableCourse)
        .where(TimetableCourse.timetable_id == src.id)
        .order_by(TimetableCourse.created_at)
    ).all()

    new_tt = Timetable(
        id=uuid.uuid4().hex,
        user_id=user.id,
        name=_next_timetable_name(session, user.id),
    )
    session.add(new_tt)
    for row in src_courses:
        session.add(
            TimetableCourse(timetable_id=new_tt.id, offering_id=row.offering_id),
        )
    session.commit()
    session.refresh(new_tt)
    return TimetableResponse(timetable=_hydrate_timetable(session, new_tt, dept_code))


@router.post(
    "/timetables/{timetable_id}/courses",
    response_model=TimetableCourseResponse,
    status_code=201,
)
def add_course(
    timetable_id: str,
    req: TimetableCourseAddRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    dept_code: str | None = Depends(get_user_dept_code),
):
    tt = _get_owned_timetable(session, timetable_id, user.id)
    if not offering_exists(session, req.offering_id):
        raise HTTPException(status_code=404, detail="강의를 찾을 수 없습니다.")

    existing = session.exec(
        select(TimetableCourse)
        .where(TimetableCourse.timetable_id == tt.id)
        .where(TimetableCourse.offering_id == req.offering_id)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="이미 시간표에 있는 강의입니다.")

    session.add(TimetableCourse(timetable_id=tt.id, offering_id=req.offering_id))
    session.commit()
    summary = summaries_by_ids(session, [req.offering_id], dept_code)[req.offering_id]
    return TimetableCourseResponse(course=summary)


@router.delete(
    "/timetables/{timetable_id}/courses/{offering_id}",
    status_code=204,
)
def remove_course(
    timetable_id: str,
    offering_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    _get_owned_timetable(session, timetable_id, user.id)
    existing = session.exec(
        select(TimetableCourse)
        .where(TimetableCourse.timetable_id == timetable_id)
        .where(TimetableCourse.offering_id == offering_id)
    ).first()
    if existing is not None:
        session.delete(existing)
        session.commit()
    return None
