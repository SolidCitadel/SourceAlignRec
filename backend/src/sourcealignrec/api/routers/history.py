"""History + Graduation requirement router — api-contract/history.md 정합.

per-user 수강이력(CourseHistory) + 졸업요건(GraduationRequirement) CRUD.
- history.course_id: 카탈로그 매칭 시 실제 Course.id, 직접입력(custom)이면 null.
  추천 Hard Filter는 search.py에서 is_custom=False & course_id IS NOT NULL인 row만 사용.
- requirements: default 시드 없음 — 신규 유저는 빈 list. PUT은 (user_id, category) upsert.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlmodel import Session, select

from sourcealignrec.api._schemas import WireModel
from sourcealignrec.api._security import get_current_user
from sourcealignrec.db.models import Course, CourseHistory, GraduationRequirement, User
from sourcealignrec.db.session import get_session

router = APIRouter(tags=["history"])


# ── Wire schemas ────────────────────────────────────────────────────────────


class HistoryEntryOut(WireModel):
    id: str
    course_id: str | None = None
    course_name: str
    credits: int
    course_type: str
    term: str
    grade: str
    custom: bool = False


class HistoryListResponse(WireModel):
    items: list[HistoryEntryOut]


class HistoryAddRequest(WireModel):
    course_id: str | None = None
    course_name: str = Field(min_length=1)
    credits: int = Field(ge=0, le=30)
    course_type: str
    term: str
    grade: str
    custom: bool = False


class HistoryItemResponse(WireModel):
    item: HistoryEntryOut


class RequirementOut(WireModel):
    category: str
    required: int


class RequirementsResponse(WireModel):
    # 졸업 총 이수학점(per-user 스칼라). 영역 최소합과 별개 — 미설정 시 None.
    total_required: int | None = None
    items: list[RequirementOut]


class RequirementPutRequest(WireModel):
    required: int = Field(ge=0, le=300)


class RequirementItemResponse(WireModel):
    item: RequirementOut


class TotalResponse(WireModel):
    total_required: int


def _to_out(row: CourseHistory) -> HistoryEntryOut:
    return HistoryEntryOut(
        id=row.id,
        course_id=row.course_id,
        course_name=row.course_name,
        credits=row.credits,
        course_type=row.course_type,
        term=row.term,
        grade=row.grade,
        custom=row.is_custom,
    )


# ── History endpoints ─────────────────────────────────────────────────────────


@router.get("/history", response_model=HistoryListResponse)
def list_history(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    rows = session.exec(
        select(CourseHistory)
        .where(CourseHistory.user_id == user.id)
        .order_by(CourseHistory.created_at)
    ).all()
    return HistoryListResponse(items=[_to_out(r) for r in rows])


@router.post("/history", response_model=HistoryItemResponse)
def add_history(
    req: HistoryAddRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    # 카탈로그 매칭 entry는 course_id가 실제 Course여야 함 (필터 정합 + FK 무결성).
    if req.course_id is not None and session.get(Course, req.course_id) is None:
        raise HTTPException(status_code=404, detail="과목을 찾을 수 없습니다.")

    row = CourseHistory(
        id=uuid.uuid4().hex,
        user_id=user.id,
        course_id=req.course_id,
        course_name=req.course_name,
        credits=req.credits,
        course_type=req.course_type,
        term=req.term,
        grade=req.grade,
        is_custom=req.custom,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return HistoryItemResponse(item=_to_out(row))


@router.delete("/history/{entry_id}", status_code=204)
def remove_history(
    entry_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = session.exec(
        select(CourseHistory)
        .where(CourseHistory.id == entry_id)
        .where(CourseHistory.user_id == user.id)
    ).first()
    if row is not None:
        session.delete(row)
        session.commit()
    return None


# ── Requirement endpoints ──────────────────────────────────────────────────────


@router.get("/requirements", response_model=RequirementsResponse)
def list_requirements(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    rows = session.exec(
        select(GraduationRequirement)
        .where(GraduationRequirement.user_id == user.id)
        .order_by(GraduationRequirement.category)
    ).all()
    return RequirementsResponse(
        total_required=user.grad_total_required,
        items=[RequirementOut(category=r.category, required=r.required) for r in rows],
    )


# 주의: 경로가 `/requirements/{category}`(아래)에 잡히지 않도록 반드시 그 앞에 선언.
@router.put("/requirements/total", response_model=TotalResponse)
def set_requirements_total(
    req: RequirementPutRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    user.grad_total_required = req.required
    session.add(user)
    session.commit()
    session.refresh(user)
    return TotalResponse(total_required=user.grad_total_required)


@router.put("/requirements/{category}", response_model=RequirementItemResponse)
def upsert_requirement(
    category: str,
    req: RequirementPutRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = session.exec(
        select(GraduationRequirement)
        .where(GraduationRequirement.user_id == user.id)
        .where(GraduationRequirement.category == category)
    ).first()
    if row is None:
        row = GraduationRequirement(
            id=uuid.uuid4().hex,
            user_id=user.id,
            category=category,
            required=req.required,
        )
        session.add(row)
    else:
        row.required = req.required
        session.add(row)
    session.commit()
    session.refresh(row)
    return RequirementItemResponse(item=RequirementOut(category=row.category, required=row.required))


@router.delete("/requirements/{category}", status_code=204)
def remove_requirement(
    category: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = session.exec(
        select(GraduationRequirement)
        .where(GraduationRequirement.user_id == user.id)
        .where(GraduationRequirement.category == category)
    ).first()
    if row is not None:
        session.delete(row)
        session.commit()
    return None
