"""Course catalog picker — api-contract/courses.md 정합.

수강이력(history) 검색·추가 UI 전용 카탈로그 조회. /search(임베딩 의미검색)와 별개로
Course 단위 키워드 매칭 + 대표(최신 학기) Offering에서 학점·이수구분·학과 default 제공.
저장 시 실제 Course.id가 history.course_id로 들어가 추천 Hard Filter가 동작한다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlmodel import Session, select

from sourcealignrec.api._schemas import WireModel
from sourcealignrec.api._security import get_current_user, get_user_dept_code
from sourcealignrec.db.models import Course, Offering, User
from sourcealignrec.db.session import get_session
from sourcealignrec.online import dept_lens

router = APIRouter(tags=["courses"])


# ── Wire schemas ────────────────────────────────────────────────────────────


class CourseHit(WireModel):
    id: str
    name: str
    credits: int                 # 대표 Offering 출처 (없으면 0)
    course_type: str             # 대표 Offering 출처 (없으면 "")
    department: str | None = None  # 대표 Offering dept_name


class CourseSearchResponse(WireModel):
    items: list[CourseHit]


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/courses", response_model=CourseSearchResponse)
def search_courses(
    q: str = Query(..., min_length=1, description="과목명 또는 학수번호 부분일치"),
    limit: int = Query(20, ge=1, le=50),
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    dept_code: str | None = Depends(get_user_dept_code),
):
    kw = q.strip()
    if not kw:
        return CourseSearchResponse(items=[])

    like = f"%{kw}%"
    courses = session.exec(
        select(Course)
        .where(or_(Course.name.ilike(like), Course.id.ilike(like)))
        .order_by(Course.name)
        .limit(limit)
    ).all()
    if not courses:
        return CourseSearchResponse(items=[])

    # 대표 Offering = course별 최신 term. 매칭 course 전체 offering 1 query 후 Python 집계.
    course_ids = [c.id for c in courses]
    offerings = session.exec(
        select(Offering).where(Offering.course_id.in_(course_ids))
    ).all()
    rep: dict[str, Offering] = {}
    for o in offerings:
        cur = rep.get(o.course_id)
        if cur is None or (o.term or "") > (cur.term or ""):
            rep[o.course_id] = o

    # 이수구분 default = 본인 학과 렌즈(history 폼 기본값, 사용자 수정 가능). 렌즈 밖이면 빈값.
    lens = dept_lens.dept_classification_map(session, dept_code, [o.id for o in rep.values()])
    items = [
        CourseHit(
            id=c.id,
            name=c.name,
            credits=(rep[c.id].credits or 0) if c.id in rep and rep[c.id].credits is not None else 0,
            course_type=lens.get(rep[c.id].id, "") if c.id in rep else "",
            department=(rep[c.id].dept_name if c.id in rep else None),
        )
        for c in courses
    ]
    return CourseSearchResponse(items=items)
