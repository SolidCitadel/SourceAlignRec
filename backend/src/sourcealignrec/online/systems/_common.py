"""시스템 변종 공통 helper.

structured output schema·호출 helper는 `backend/work/e2e-benchmark/system-output-schema.md` 참조.

phase-split (2026-05-18): retrieval/generation 분리를 위해 시스템 변종 공유 추상화 추가.
- RetrievalState: retrieve() 출력 — shortlist + query_embedding을 캡슐화.
- assemble_user_message: dict[oid, str] context + query → final LLM user message string.
- generate_recommendation: 5 시스템 공용 LLM 호출 (시스템별 차이는 retrieve+build_context까지가 전부).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import cast
from sqlmodel import Session, select

from sourcealignrec.core import embedder
from sourcealignrec.core.config import settings
from sourcealignrec.core.model_pool import get_pool
from sourcealignrec.db.models import (
    Course,
    Offering,
    OfferingAttribute,
    OfferingProfile,
    Professor,
)

EMBED_MODEL = embedder.MODEL_NAME  # 벤치마크 메타 기록 호환 — 임베딩 정본은 core.embedder

# 추천 LLM 모델은 settings.recommend_model 사용. 운영·벤치마크 default 단일 (.env로 swap).
# 벤치마크에서 시스템 B만 큰 컨텍스트가 필요해 별도 endpoint로 override — run_e2e 참조.

BASE_SYSTEM_PROMPT = """\
당신은 학생의 수강 과목 선택을 돕는 추천 어시스턴트입니다.
제공된 후보 과목 정보를 바탕으로 학생의 질의에 맞게 과목을 K=3개 추천하세요.

원칙:
- 학생의 질의 의도와 직접 부합하는 과목을 우선 추천하세요. 단순 다양성을 위해 무관한 도메인의 과목을 채우지 마세요.
- 같은 과목의 다른 분반(같은 과목명·다른 교수)이라도 학생 질의 의도에 부합하면 그대로 추천하세요. 분반·도메인 중복 자체를 회피할 이유는 없습니다.
- 부합 후보가 K=3보다 적으면 가장 가까운 차선책으로 채우되, 해당 추천의 rationale 첫 줄에 "(직접 부합 아닌 차선책)"을 표시하세요.
- 제공된 데이터에 기반해 사실만 전달하세요. 데이터 없는 항목은 "미확인"으로 처리하세요.
- 각 추천의 rationale은 과목 특성, 평가 방식, 강의평 내용 등 구체적 근거 2~4문장으로 자연어로 자유롭게 서술하세요.
- 구조화 속성 태그(예: `assignment_load: 적음`, `grading_leniency: 너그러움`, `attendance_strictness: 엄격함` 등)를 응답에 그대로 노출하지 말고, 자연어로 풀어 쓰세요. 예: '과제량이 적습니다', '채점이 너그럽습니다'.

출력 형식:
- 응답은 반드시 RecommendationOutput JSON 스키마를 따르세요.
- recommendations 배열에 K=3개 항목, 각 항목은 {rank, offering_id, rationale}.
- offering_id는 제공된 후보 목록의 id만 사용. 목록에 없는 id 절대 생성 금지.\
"""

# converse(후속 질문/grounding) 전용. 초기 추천(BASE_SYSTEM_PROMPT)과 목적이 다르다:
# 새 추천이 아니라, 이미 추천된 과목에 대한 질문에 데이터 근거로 답한다. D는 이것만, E는 +TOOL_HINT_SUFFIX.
CONVERSE_SYSTEM_PROMPT = """\
당신은 학생이 이미 추천받은 과목에 대한 후속 질문에 답하는 어시스턴트입니다.

역할:
- 아래 [추천된 과목] 정보를 근거로 학생의 질문에 답하세요. 새로 과목을 추천하거나 추천 목록을 바꾸지 마세요.
- 제공된 데이터(추천 과목 정보, 조회한 강의평·강의계획서)에 근거한 사실만 전달하세요. 데이터에 없는 내용은 추측하지 말고 "미확인"으로 답하세요.
- 구조화 속성 태그(예: `assignment_load: 적음`)를 그대로 노출하지 말고 자연어로 풀어 쓰세요. 예: '과제량이 적습니다'.
- 답변은 학생의 질문에 초점을 맞춰 자연어로 간결하게 작성하세요.

출력 형식:
- 응답은 반드시 ConversationOutput JSON 스키마를 따르세요 (explanation 필드 하나).\
"""

# System E follow-up 등 tool 사용 시 CONVERSE_SYSTEM_PROMPT에 덧붙임. grounding 전용.
# 정적 규칙만 담는다. 조회 가능한 offering 목록은 build_converse_grounding_block가 동적 주입.
TOOL_HINT_SUFFIX = """\

후속 질문 응답 가이드 (grounding 전용):

위 [추천된 과목] 목록에 있는 과목에 대해서만 답할 수 있습니다. 목록에 없는 과목·offering_id는 조회하지 마세요.

답에 강의평 원문이나 강의계획서 세부가 필요하면 추천된 과목의 offering_id로 tool을 호출하세요.
- get_reviews: 학생 평가·경험에 기반한 답변이 필요할 때
- get_syllabus: 강의계획서에 명시된 사실(평가 비중, 주차별 주제, 선수과목 등)이 필요할 때

위 추천 과목 프로필은 압축 요약입니다. 평가 비중·강의평 원문 등 구체 세부는 프로필에 의존하지 말고 가능한 한 tool로 원문을 확인해 답하세요.

tool 호출 규칙:
- 궁금한 과목을 한 번에 모아 offering_ids 배열로 호출하세요. 같은 tool을 여러 번 나눠 호출하지 마세요.
- tool 호출 기회는 한 번뿐입니다. 필요한 과목을 이 한 번에 모두 포함하세요.
- 사전 지식으로 추측하거나 지어내지 말고, tool로 받은 데이터에만 근거하세요. 데이터에 없는 항목은 "미확인"으로 답하세요.

tool 결과를 받은 뒤 자연어로 답변하세요. 추가 데이터가 필요 없으면 tool 없이 바로 답해도 됩니다.\
"""

# ── Retrieval phase abstraction (phase-split) ───────────────────────────────

@dataclass
class RetrievalState:
    """시스템별 retrieve() 출력 — LLM 호출 전까지 모든 결정적 단계 산출물.

    shortlist_ids 순서가 pgvector 검색 결과 순서를 의미. build_context는 이 순서대로
    context를 만들고, assemble_user_message가 같은 순서로 final message 조립.

    query_embedding은 RetrievalExecution.query_embedding 저장 + 분석/재현용. A는
    build_context 내부에서 리뷰 재검색에 재사용.

    extras는 시스템별 캐시(예: D의 OfferingProfile 객체) — 기본은 빈 dict. RetrievalState를
    DB row에 직렬화할 때는 shortlist_ids + query_embedding만 기록(extras는 transient).
    """
    shortlist_ids: list[str]
    query_embedding: list[float]
    extras: dict = field(default_factory=dict)


def assemble_user_message(
    query: str,
    context_per_offering: dict[str, str],
    shortlist_ids: list[str],
) -> str:
    """offering별 context dict + shortlist 순서 → final LLM user message string.

    기존 _build_context의 join + initial_content 조립 로직과 byte-level 동치.
    """
    parts = [context_per_offering[oid] for oid in shortlist_ids if oid in context_per_offering]
    offering_context = "\n\n---\n\n".join(parts)
    return f"[후보 과목 목록]\n\n{offering_context}\n\n---\n\n질문: {query}"


# ── Recommendation output schema ────────────────────────────────────────────

class RecommendationItem(BaseModel):
    """단일 추천 항목. extra="forbid" → schema에 additionalProperties: false 자동 포함."""
    model_config = ConfigDict(extra="forbid")
    rank: int = Field(ge=1, le=3)
    offering_id: str
    rationale: str


class RecommendationOutput(BaseModel):
    """초기 추천 결과 — K=3 추천. strict json_schema 모드에서 배열 길이 강제."""
    model_config = ConfigDict(extra="forbid")
    recommendations: list[RecommendationItem] = Field(min_length=3, max_length=3)


class ConversationOutput(BaseModel):
    """대화 turn 응답. 현재 정의: grounding 케이스의 자유 텍스트 답변.

    추천 갱신은 시스템 책임이 아님 (form/query 갱신 → 새 recommend 호출). 따라서 이 스키마에는
    recommendations 필드가 없다.
    """
    model_config = ConfigDict(extra="forbid")
    explanation: str = Field(min_length=1)


# ── Structured output 호출 helper ───────────────────────────────────────────

def build_response_format(response_model: type[BaseModel]) -> dict:
    """Pydantic 모델 → OpenAI-compatible response_format dict (strict json_schema)."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": response_model.__name__,
            "schema": response_model.model_json_schema(),
            "strict": True,
        },
    }


def _extract_offering_ids(parsed: BaseModel) -> set[str] | None:
    """RecommendationOutput에서 offering_id 추출. None이면 검증 대상 아님 (예: ConversationOutput)."""
    if isinstance(parsed, RecommendationOutput):
        return {item.offering_id for item in parsed.recommendations}
    return None


def parse_and_validate(
    raw_content: str,
    response_model: type[BaseModel],
    shortlist_ids: set[str] | None,
) -> tuple[BaseModel | None, str]:
    """raw 응답 → 검증된 모델. status: success | parse_error | invalid_offering_id."""
    if not raw_content:
        return None, "parse_error"
    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError:
        return None, "parse_error"
    try:
        parsed = response_model.model_validate(data)
    except ValidationError:
        return None, "parse_error"
    if shortlist_ids is not None:
        emitted = _extract_offering_ids(parsed)
        if emitted and not emitted.issubset(shortlist_ids):
            return None, "invalid_offering_id"
    return parsed, "success"


def usage_dict(response) -> dict:
    usage = getattr(response, "usage", None)
    if not usage:
        return {"prompt_tokens": None, "completion_tokens": None}
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
    }


def call_with_schema(
    model_id: str,
    messages: list[dict],
    response_model: type[BaseModel],
    shortlist_ids: set[str],
    *,
    extra_kwargs: dict | None = None,
) -> tuple[BaseModel | None, dict, dict]:
    """단일 호출 + strict json_schema → invalid_id retry. tool loop 없음 (system A/B/C 초기 추천용).

    Returns:
        (parsed: RecommendationOutput 또는 None, last_msg: dict for transcript, meta: dict)

    meta 필드:
        status: success | parse_error | invalid_offering_id
        schema_honored: bool — strict 모드가 schema-conforming 응답을 반환했는지
        retry_count: int — invalid_id retry 횟수
        prompt_tokens, completion_tokens: 마지막 호출 기준
    """
    pool = get_pool()
    base_kwargs = dict(extra_kwargs or {})
    base_kwargs["response_format"] = build_response_format(response_model)

    response = pool.chat(model_id, messages, **base_kwargs)
    msg = response.choices[0].message
    raw = strip_think(msg.content or "")
    parsed, status = parse_and_validate(raw, response_model, shortlist_ids)

    schema_honored = status != "parse_error"
    retry_count = 0
    last_msg = {"role": "assistant", "content": msg.content}

    if status == "invalid_offering_id":
        retry_messages = list(messages) + [
            last_msg,
            {
                "role": "user",
                "content": (
                    "위 응답에 후보 목록에 없는 offering_id가 포함되어 있습니다. "
                    f"다음 id 중에서만 선택해 RecommendationOutput JSON으로 다시 응답해주세요: "
                    f"{sorted(shortlist_ids)}"
                ),
            },
        ]
        response = pool.chat(model_id, retry_messages, **base_kwargs)
        msg = response.choices[0].message
        raw = strip_think(msg.content or "")
        parsed, status = parse_and_validate(raw, response_model, shortlist_ids)
        retry_count = 1
        last_msg = {"role": "assistant", "content": msg.content}

    meta = {
        "status": status,
        "schema_honored": schema_honored,
        "retry_count": retry_count,
        **usage_dict(response),
    }
    return parsed, last_msg, meta


def generate_recommendation(
    model: str,
    query: str,
    context_per_offering: dict[str, str],
    shortlist_ids: list[str],
) -> tuple[BaseModel | None, list[dict], dict]:
    """5 시스템 공용 LLM 호출. retrieve + build_context 결과를 받아 final message 조립 + call_with_schema.

    Returns: (parsed | None, transcript, meta) — system-output-schema.md §6.

    meta.shortlist_ids에 list 추가(기존 recommend_initial과 동일 contract).
    """
    initial_content = assemble_user_message(query, context_per_offering, shortlist_ids)
    parsed, last_msg, meta = call_with_schema(
        model,
        [
            {"role": "system", "content": BASE_SYSTEM_PROMPT},
            {"role": "user", "content": initial_content},
        ],
        RecommendationOutput,
        set(shortlist_ids),
        extra_kwargs={"temperature": 0.3},
    )
    meta["shortlist_ids"] = list(shortlist_ids)
    transcript = [
        {"role": "user", "content": initial_content},
        last_msg,
    ]
    return parsed, transcript, meta


def embed(text: str) -> list[float]:
    return embedder.embed(text)


def strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def serialize_syllabus(offering: Offering) -> str:
    """Offering 구조화 필드를 LLM 컨텍스트용 한국어 블록으로 직렬화.

    syllabus_text가 있으면 그대로 사용 (legacy ingestion 경로). 없으면 구조화 필드를 합성.
    """
    if offering.syllabus_text:
        return offering.syllabus_text
    parts: list[str] = []
    if offering.course_overview:
        parts.append(f"[수업 개요]\n{offering.course_overview}")
    if offering.learning_objectives:
        parts.append(f"[학습 목표]\n{offering.learning_objectives}")
    weekly = json.loads(offering.weekly_topics or "[]")
    if weekly:
        parts.append("[주차별 주제] " + " / ".join(str(t) for t in weekly))
    eval_items = json.loads(offering.evaluation_items or "[]")
    if eval_items:
        eval_parts = []
        for e in eval_items:
            if isinstance(e, dict) and "item" in e and "ratio" in e:
                note = f" ({e['note']})" if e.get("note") else ""
                eval_parts.append(f"{e['item']} {e['ratio']}%{note}")
        if eval_parts:
            parts.append("[평가 항목] " + ", ".join(eval_parts))
    instr = json.loads(offering.instruction_type_ratios or "[]")
    if instr:
        instr_parts = []
        for it in instr:
            if isinstance(it, dict) and "type" in it and "ratio_pct" in it:
                instr_parts.append(f"{it['type']} {it['ratio_pct']}%")
        if instr_parts:
            parts.append("[수업 형태] " + ", ".join(instr_parts))
    prereqs = json.loads(offering.prerequisite_courses or "[]")
    if prereqs:
        prereq_parts = []
        for p in prereqs:
            if isinstance(p, dict) and "name" in p:
                label = "필수" if p.get("required") else "권장"
                prereq_parts.append(f"{p['name']}({label})")
        if prereq_parts:
            parts.append("[선수과목] " + ", ".join(prereq_parts))
    return "\n\n".join(parts)


# ── OfferingProfile-based retrieval (System C/D 공유) ────────────────────────

def shortlist_by_profile(
    session: Session,
    query_embedding: list[float],
    candidate_ids: list[str],
    *,
    limit: int | None = None,
) -> list[OfferingProfile]:
    """OfferingProfile.embedding 기반 pgvector shortlist.

    limit=None이면 full ranking 반환 (RRF fuse용). 일반 호출은 settings.shortlist_size 전달.
    """
    if not candidate_ids:
        return []
    query_vec = cast(query_embedding, Vector(settings.embedding_dim))
    stmt = (
        select(OfferingProfile)
        .where(OfferingProfile.offering_id.in_(candidate_ids))
        .where(OfferingProfile.embedding.isnot(None))
        .order_by(OfferingProfile.embedding.op("<=>")(query_vec))
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return session.exec(stmt).all()


# ── Cascading retrieval helper ──────────────────────────────────────────────

def cascading_rrf(
    rankings: list[list[str]],
    *,
    k: int = 60,
    top_k: int,
) -> list[str]:
    """여러 ranking을 Reciprocal Rank Fusion으로 결합해 top_k 반환.

    score(oid) = sum_i 1/(k + rank_i(oid)+1). rank는 0-based, +1로 1-based 변환 (RRF 표준).
    한 ranking에만 등장하는 oid도 동일 공식. cascading 변종(D loose pool 안의 D rank vs A rank)
    측정에 사용.
    """
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for i, oid in enumerate(ranking):
            scores[oid] += 1.0 / (k + (i + 1))
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return [oid for oid, _ in ranked[:top_k]]


def build_profile_context(
    session: Session,
    profiles: list[OfferingProfile],
) -> dict[str, str]:
    """OfferingProfile shortlist → dict[offering_id, str].

    각 entry: header(과목/교수/학기) + Attribute 요약 + profile_text. 호출자가 final
    user message 조립 시 shortlist 순서대로 join (assemble_user_message 사용).

    phase-split 이전 단일 string 반환 → dict 반환으로 변경 (2026-05-18). 단일 string이
    필요한 호출자(run_e2e._build_grounding_starter 등)는 호출 측에서 join.
    """
    if not profiles:
        return {}
    offering_ids = [p.offering_id for p in profiles]
    offerings = {o.id: o for o in session.exec(
        select(Offering).where(Offering.id.in_(offering_ids))
    ).all()}
    course_ids = {o.course_id for o in offerings.values()}
    prof_ids = {o.professor_id for o in offerings.values()}
    courses = {c.id: c for c in session.exec(select(Course).where(Course.id.in_(course_ids))).all()}
    professors = {p.id: p for p in session.exec(select(Professor).where(Professor.id.in_(prof_ids))).all()}

    attr_rows = session.exec(
        select(OfferingAttribute).where(OfferingAttribute.offering_id.in_(offering_ids))
    ).all()
    attrs_by_offering: dict[str, dict[str, str]] = {}
    for a in attr_rows:
        attrs_by_offering.setdefault(a.offering_id, {})[a.attribute_name] = a.attribute_value

    result: dict[str, str] = {}
    for p in profiles:
        o = offerings.get(p.offering_id)
        if not o:
            continue
        course = courses.get(o.course_id)
        professor = professors.get(o.professor_id)
        header = f"[{p.offering_id}] {course.name if course else '?'} — {professor.name if professor else '?'} ({o.term})"
        attrs = attrs_by_offering.get(p.offering_id, {})
        attr_str = " | ".join(f"{k}: {v}" for k, v in attrs.items()) if attrs else "미확인"
        result[p.offering_id] = f"{header}\n속성: {attr_str}\n{p.profile_text}"
    return result


def build_converse_grounding_block(session: Session, offering_ids: list[str]) -> str:
    """converse grounding 컨텍스트 정본 — 조회 가능한(=추천된) 과목 블록.

    offering_ids 순서(추천 rank 순)를 유지한다. D/E 공통: 같은 블록을 주입해 retrieval source를
    동일하게 두고, E만 tool로 raw access를 추가한다(e2e-benchmark §D vs E ablation).

    OfferingProfile 없는 id는 "정보 없음"으로 표기 — 모델이 매핑은 하되 grounding은 못 함을 명시.
    """
    if not offering_ids:
        return "[추천된 과목 없음]"
    profiles = {
        p.offering_id: p
        for p in session.exec(
            select(OfferingProfile).where(OfferingProfile.offering_id.in_(offering_ids))
        ).all()
    }
    ordered = [profiles[oid] for oid in offering_ids if oid in profiles]
    ctx = build_profile_context(session, ordered)
    parts = [ctx[oid] if oid in ctx else f"[{oid}] 정보 없음" for oid in offering_ids]
    body = "\n\n---\n\n".join(parts)
    return f"[추천된 과목 — 후속 질문은 이 과목들에 한정]\n\n{body}"


def merge_profiles_into_first_user(
    messages: list[dict], profiles_block: str
) -> list[dict]:
    """추천 과목 프로필을 첫 user 턴에 결합 — 초기 recommend가 본 user 메시지(프로필+질의)를 replay.

    converse 대화 구조: system + user(프로필 + 초기 질의) + assistant(추천 items) + 후속 누적.
    프로필 텍스트는 백엔드 데이터라 여기서 주입하고, 나머지 대화(추천 items·후속)는 messages가 운반.
    user 턴이 없으면(방어) 프로필을 단독 user 턴으로 선두 삽입.
    """
    out: list[dict] = []
    injected = False
    for m in messages:
        if not injected and m.get("role") == "user":
            out.append({"role": "user", "content": f"{profiles_block}\n\n---\n\n{m.get('content', '')}"})
            injected = True
        else:
            out.append(dict(m))
    if not injected:
        out.insert(0, {"role": "user", "content": profiles_block})
    return out