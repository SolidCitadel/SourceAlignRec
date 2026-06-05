"""POST /recommend — api-contract/recommend.md 정합.

입력 모집단 = 프론트 검색 결과 (candidateOfferingIds). 백엔드는 추가 hard filter 없이
모집단 안에서 retrieval로 shortlist K 산출 → LLM ranking/explanation.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlmodel import Session, select

from sourcealignrec.api._schemas import ClassMeetingOut, WireModel, parse_meetings_json
from sourcealignrec.api._security import get_current_user, get_user_dept_code
from sourcealignrec.online import dept_lens
from sourcealignrec.core.config import settings
from sourcealignrec.db.models import (
    Course,
    Offering,
    Professor,
    User,
)
from sourcealignrec.db.session import get_session
from sourcealignrec.online.systems import system_e
from sourcealignrec.online.systems._common import (
    ConversationOutput,
    RecommendationOutput,
)

router = APIRouter(prefix="/recommend", tags=["recommend"])


# ── Wire schemas ────────────────────────────────────────────────────────────


class ChatTurn(WireModel):
    role: Literal["user", "assistant"]
    content: str


class RecommendRequest(WireModel):
    mode: Literal["initial", "converse"]
    query: str = Field(min_length=1)
    # initial: 검색 결과 모집단. converse: 사용 안 함(recommended_offering_ids로 grounding).
    candidate_offering_ids: list[str] = Field(default_factory=list)
    # converse: 후속 질문 대상 = 직전에 추천된 과목 K개. tool 조회·grounding 범위의 단일 출처.
    recommended_offering_ids: list[str] = Field(default_factory=list)
    messages: list[ChatTurn] = Field(default_factory=list)


class RecommendItem(WireModel):
    rank: int
    offering_id: str
    course_name: str
    professor_name: str
    credit: int
    type: str
    department: str
    meetings: list[ClassMeetingOut]
    rationale: str


class RecommendResponse(WireModel):
    """recommend 호출: recommendations 채움, explanation None.
    converse 호출: explanation 채움, recommendations None."""
    status: str
    messages: list[ChatTurn]
    recommendations: list[RecommendItem] | None = None
    explanation: str | None = None


# ── Hydrate helpers ─────────────────────────────────────────────────────────


def _hydrate_items(session: Session, items: list, dept_code: str | None = None) -> list[RecommendItem]:
    """offering_id → Offering+Course+Professor 합성. contract §5.3 RecommendItem."""
    if not items:
        return []
    offering_ids = [it.offering_id for it in items]
    offerings = {
        o.id: o
        for o in session.exec(select(Offering).where(Offering.id.in_(offering_ids))).all()
    }
    lens = dept_lens.dept_classification_map(session, dept_code, offering_ids)
    course_ids = {o.course_id for o in offerings.values()}
    prof_ids = {o.professor_id for o in offerings.values()}
    courses = {
        c.id: c for c in session.exec(select(Course).where(Course.id.in_(course_ids))).all()
    }
    professors = {
        p.id: p
        for p in session.exec(select(Professor).where(Professor.id.in_(prof_ids))).all()
    }
    out: list[RecommendItem] = []
    for it in items:
        o = offerings.get(it.offering_id)
        course = courses.get(o.course_id) if o else None
        professor = professors.get(o.professor_id) if o else None
        out.append(
            RecommendItem(
                rank=it.rank,
                offering_id=it.offering_id,
                course_name=course.name if course else "(unknown)",
                professor_name=professor.name if professor else "(unknown)",
                credit=o.credits if o and o.credits is not None else 0,
                type=lens.get(it.offering_id, ""),
                department=o.dept_name if o and o.dept_name else "",
                meetings=parse_meetings_json(o.meetings_json if o else None),
                rationale=it.rationale,
            )
        )
    return out


# ── Endpoint ────────────────────────────────────────────────────────────────


@router.post("", response_model=RecommendResponse)
def recommend(
    req: RecommendRequest,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    dept_code: str | None = Depends(get_user_dept_code),
):
    """본 라우터는 System E 전용(초기 추천은 D에 위임). A/B/C는 ablation용으로 벤치마크 runner가 직접 import."""
    # 추천은 컴공 카탈로그만 지원 — profile corpus가 컴공-강의평 기반이라 비컴공은 편향된 반쪽 추천.
    if not dept_lens.is_recommend_supported(dept_code):
        raise HTTPException(
            status_code=400,
            detail="추천은 현재 컴퓨터공학과 학생만 이용할 수 있습니다 (강의평 데이터 한정). 검색은 수집된 모든 학과에서 가능합니다.",
        )
    model = settings.api_recommend_model

    if req.mode == "initial":
        if not req.candidate_offering_ids:
            raise HTTPException(status_code=400, detail="추천할 후보 강의가 없습니다.")
        parsed, transcript, meta = system_e.recommend_initial_from_candidates(
            session, req.query, req.candidate_offering_ids, model,
        )
        if parsed is None:
            raise HTTPException(
                status_code=502,
                detail=f"recommendation generation failed: status={meta['status']}",
            )
        assert isinstance(parsed, RecommendationOutput)
        return RecommendResponse(
            status=meta["status"],
            messages=[
                ChatTurn(**m) for m in transcript
                if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
            ],
            recommendations=_hydrate_items(session, parsed.recommendations, dept_code),
            explanation=None,
        )

    # converse
    if not req.messages:
        raise HTTPException(
            status_code=400, detail="converse 모드에는 messages가 필요합니다.",
        )
    if not req.recommended_offering_ids:
        raise HTTPException(
            status_code=400, detail="후속 질문 대상 추천 과목이 없습니다.",
        )
    # messages = 완결된 대화(초기 질의·추천 items·후속 누적). 마지막 user 턴이 현재 질문.
    transcript_in = [m.model_dump() for m in req.messages]
    parsed, transcript, meta = system_e.converse(
        session, transcript_in, req.recommended_offering_ids, model,
    )
    if parsed is None:
        raise HTTPException(
            status_code=502,
            detail=f"conversation generation failed: status={meta['status']}",
        )
    assert isinstance(parsed, ConversationOutput)
    return RecommendResponse(
        status=meta["status"],
        messages=[
                ChatTurn(**m) for m in transcript
                if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
            ],
        recommendations=None,
        explanation=parsed.explanation,
    )
