"""System D — OfferingProfile 검색 + Tool Calling 없음.

e2e-benchmark §비교 시스템:
- 검색: OfferingProfile.embedding (E와 동일)
- LLM 컨텍스트: OfferingProfile (E와 동일)
- Tool: 모든 turn 비활성

검색·컨텍스트 helper는 _common에서 E와 공유. D/E 차이는 conversation turn에서 tool(get_reviews/get_syllabus) 사용 가능 여부.
"""
from __future__ import annotations

from sqlmodel import Session

from sourcealignrec.core.config import settings
from sourcealignrec.online import filter as hard_filter
from sourcealignrec.online.systems._common import (
    CONVERSE_SYSTEM_PROMPT,
    ConversationOutput,
    RecommendationOutput,
    RetrievalState,
    build_converse_grounding_block,
    build_profile_context,
    call_with_schema,
    embed,
    generate_recommendation,
    merge_profiles_into_first_user,
    shortlist_by_profile,
)


def retrieve(
    session: Session,
    query: str,
    filters: dict[str, list[str]],
    taken_courses: list[str],
    *,
    shortlist_size: int | None = None,
) -> RetrievalState:
    """Hard Filter → OfferingProfile.embedding 검색. 벤치마크 runner 진입점.

    extras["profiles"]에 OfferingProfile 객체 list(검색 순서 보존)를 캐싱해 build_context가
    DB 재조회 없이 사용 가능. RetrievalState DB 직렬화 시 extras는 transient (참고: _common).
    """
    candidate_ids = hard_filter.run(session, filters, taken_courses)
    return retrieve_from_candidates(session, query, candidate_ids, shortlist_size=shortlist_size)


def retrieve_from_candidates(
    session: Session,
    query: str,
    candidate_ids: list[str],
    *,
    shortlist_size: int | None = None,
) -> RetrievalState:
    """프론트가 hard filter 적용한 candidate id list 기반 retrieval. API recommend 진입점.

    candidate_ids = api-contract/recommend.md §2 candidateOfferingIds (검색 결과 그대로).
    백엔드는 추가 hard filter를 수행하지 않음 — 모집단 안에서 OfferingProfile.embedding 검색만.
    """
    query_embedding = embed(query)
    limit = shortlist_size if shortlist_size is not None else settings.shortlist_size
    profiles = shortlist_by_profile(session, query_embedding, candidate_ids, limit=limit)
    shortlist_ids = [p.offering_id for p in profiles]
    return RetrievalState(
        shortlist_ids=shortlist_ids,
        query_embedding=query_embedding,
        extras={"profiles": profiles},
    )


def build_context(session: Session, state: RetrievalState) -> dict[str, str]:
    """OfferingProfile shortlist → dict[oid, str]. extras에 profiles 있으면 재조회 회피."""
    profiles = state.extras.get("profiles")
    if profiles is None:
        # extras 없는 경로 (예: RetrievalExecution row hydrate): shortlist_ids로 재조회.
        from sqlmodel import select
        from sourcealignrec.db.models import OfferingProfile
        if not state.shortlist_ids:
            return {}
        profiles_by_oid = {
            p.offering_id: p
            for p in session.exec(
                select(OfferingProfile).where(OfferingProfile.offering_id.in_(state.shortlist_ids))
            ).all()
        }
        profiles = [profiles_by_oid[oid] for oid in state.shortlist_ids if oid in profiles_by_oid]
    return build_profile_context(session, profiles)


def recommend_initial(
    session: Session,
    query: str,
    filters: dict[str, list[str]],
    taken_courses: list[str],
    model: str,
) -> tuple[RecommendationOutput | None, list[dict], dict]:
    """초기 추천 (벤치마크 진입점). retrieve → build_context → generate_recommendation wrapper."""
    state = retrieve(session, query, filters, taken_courses)
    context_per_offering = build_context(session, state)
    return generate_recommendation(model, query, context_per_offering, state.shortlist_ids)


def recommend_initial_from_candidates(
    session: Session,
    query: str,
    candidate_ids: list[str],
    model: str,
) -> tuple[RecommendationOutput | None, list[dict], dict]:
    """초기 추천 (API 진입점). candidate id list 받음 — api-contract/recommend.md 정합."""
    state = retrieve_from_candidates(session, query, candidate_ids)
    context_per_offering = build_context(session, state)
    return generate_recommendation(model, query, context_per_offering, state.shortlist_ids)


def converse(
    session: Session,
    messages: list[dict],
    allowed_offering_ids: list[str],
    model: str,
) -> tuple[ConversationOutput | None, list[dict], dict]:
    """대화 turn 응답 (tool 없음). 추천 과목 프로필로만 grounding 답변.

    E와 동일 구조: 추천 과목 프로필을 첫 user 턴에 결합(merge_profiles_into_first_user)해 retrieval
    source를 맞춘다. D는 tool이 없어 이 프로필 컨텍스트만으로 답한다(E는 추가로 raw access).
    `messages`는 완결된 대화 — 마지막 user 턴이 답할 질문. 추천 갱신은 새 recommend 호출이 처리.
    """
    profiles_block = build_converse_grounding_block(
        session, list(dict.fromkeys(allowed_offering_ids))
    )
    working = merge_profiles_into_first_user(messages, profiles_block)
    msgs = [{"role": "system", "content": CONVERSE_SYSTEM_PROMPT}] + working
    parsed, last_msg, meta = call_with_schema(
        model,
        msgs,
        ConversationOutput,
        shortlist_ids=None,
        extra_kwargs={"temperature": 0.3},
    )
    new_transcript = working + [last_msg]
    return parsed, new_transcript, meta
